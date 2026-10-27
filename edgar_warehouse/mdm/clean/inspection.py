"""Counts and an unchanged-record digest over governed storage, without source values."""

from collections import Counter, defaultdict
import hashlib

from sqlalchemy import func, select

from .evidence import validate_deferred
from .record_reads import RecordReader, for_connection
from .store import Conflict, canonical, identifier_values

HASH_CONTRACT = "governed-record-bytes-v1"


def _pages(api, conn, kind, *, immutable=False, lookup=False):
    """Visit one exact type through bounded primary-key pages on the same snapshot."""
    after = ""
    while True:
        keys = api.record_keys(kind, after=after, limit=500, connection=conn,
                               immutable=immutable, lookup=lookup)
        if not keys:
            return
        found = api.read([(kind, key) for key in keys], connection=conn,
                         immutable=immutable, lookup=lookup)
        if len(found) != len(keys):
            raise Conflict("Inspection lost a retained record on its snapshot")
        yield [(key, found[kind, key]) for key in keys]
        after = keys[-1]


def counts(engine):
    """Report a full store's counts; only counts and a byte digest leave this read."""
    result = {name: Counter() for name in ("masters", "stage_records", "waiting",
              "open_reviews", "set_aside", "decisions", "changes", "identifiers_on_two_masters")}
    checksum = hashlib.md5((HASH_CONTRACT + "\n").encode())
    holders = defaultdict(set)
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        reader = for_connection(conn)
        api = reader.adapter
        for kind, part, field in (("identity", "masters", "kind"),
                                  ("decision", "decisions", "operation"),
                                  ("deferred-record", "set_aside", "reason")):
            for page in _pages(api, conn, kind, immutable=True):
                for key, row in page:
                    if kind == "deferred-record":
                        body = RecordReader._body(row)
                        validate_deferred(body)
                        if body["deferred_id"] != key:
                            raise Conflict("Inspection deferred identity differs from its stored key")
                    else:
                        body = RecordReader.input_body(kind, key, row)
                    result[part][body.get(field) or "(none)"] += 1
        for page in _pages(api, conn, "source-record", lookup=True):
            pointers = reader.current([key for key, _ in page])
            reader._readings(pointers)
            result["stage_records"].update(body["source_code"] for body in pointers.values())
        for kind in ("entity", "relationship", "review"):
            for page in _pages(api, conn, kind):
                deferred = api.read([("deferred-record", key) for key, _ in page],
                                    immutable=True, connection=conn) if kind == "review" else {}
                for key, row in page:
                    body = RecordReader._body(row)
                    # Hash original publication bytes, preserving exact numbers and Unicode.
                    checksum.update(canonical([kind, key]).encode() + b":" + bytes(row["body"]) + b"\n")
                    if kind == "entity" and body.get("status") != "alias":
                        for namespace, values in body.get("identifiers", {}).items():
                            for value in identifier_values(values):
                                holders[namespace, value].add(key)
                    if kind == "review" and body.get("open"):
                        reason = body.get("reason") or "(none)"
                        result["open_reviews"][reason] += 1
                        if ("deferred-record", key) in deferred and not body.get("retired"):
                            result["waiting"][reason] += 1
        for part, table in (("batch_change", "history"), ("outbox", "outbox")):
            count = conn.scalar(select(func.count()).select_from(api.tables[table]))
            if count:
                result["changes"][part] = count
    result["identifiers_on_two_masters"].update(namespace for (namespace, _), owners in holders.items() if len(owners) > 1)
    return {**{name: dict(sorted(values.items())) for name, values in result.items()},
            "current_records_md5": checksum.hexdigest(), "records_hash_contract": HASH_CONTRACT}
