"""Replay every stored record into the mastering tables, then compare them with the old masters.

Files are keyed by their records, so a stopped replay runs again and skips what is done. Both steps
read the old tables, so they leave with them.
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from itertools import batched

from .merge import WAITING, merge_file

FILE = 1000


def stored(engine, kind: str):
    """Every stored body of one kind, in key order on one snapshot."""
    from edgar_warehouse.mdm.inspection import _pages
    from edgar_warehouse.mdm.record_reads import RecordReader, for_connection

    immutable = kind in ("source-reading", "deferred-record")
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        for page in _pages(for_connection(conn).adapter, conn, kind, immutable=immutable):
            yield from (RecordReader._body(row) for _, row in page)


def files_of(records, size: int = FILE):
    """One source at a time within a kind, so a file holds what one source delivers."""
    waiting = defaultdict(list)
    for record in records:
        key = record["kind"], record["source_code"]
        waiting[key].append(record)
        if len(waiting[key]) == size:
            yield key, waiting.pop(key)
    for key, rest in sorted(waiting.items()):
        yield key, rest


def replay(store, settings_of, records, deferred=(), quiet_of=lambda chunk: {}) -> dict:
    report, spent = Counter(), Counter()
    for (kind, source), chunk in files_of(records):
        began = time.perf_counter()
        done = merge_file(store, settings_of(kind), chunk)
        spent[source] += time.perf_counter() - began
        report["skipped" if done["skipped"] else "merged"] += 1
        report[source] += len(chunk)
        if (report["merged"] + report["skipped"]) % 100 == 0:
            print(json.dumps({"files": report["merged"] + report["skipped"], "seconds": round(spent.total())}), flush=True)
    for chunk in batched(deferred, FILE):
        chunk = list(chunk)
        report["skipped" if merge_file(store, settings_of(""), [], deferred=chunk, quiet=quiet_of(chunk))["skipped"]
               else "merged"] += 1
        report["set_aside"] += len(chunk)
    return {**report, "seconds": {source: round(seconds, 1) for source, seconds in spent.items()}}


def _conflicts(field: dict) -> list[str]:
    return sorted(json.dumps(item, sort_keys=True) for item in field.get("conflicts") or ())


def differences(old: dict, new: dict) -> list[str]:
    """What differs between two masters of the same records, named without a value."""
    if set(old["subjects"]) != set(new["subjects"]):
        return ["members"]
    found = ["identifiers"] if old["identifiers"] != new["identifiers"] else []
    for name in set(old["fields"]) | set(new["fields"]):
        left, right = old["fields"].get(name), new["fields"].get(name)
        if not left or not right:
            found.append(f"absent:{name}")
        elif left["value"] != right["value"]:
            found.append(f"value:{name}")
        elif [left["winner"].get(k) for k in ("source_code", "assertion_id")] != [
                right["winner"].get(k) for k in ("source_code", "assertion_id")]:
            found.append(f"winner:{name}")
        elif _conflicts(left) != _conflicts(right):
            found.append(f"conflicts:{name}")
    return found


def compare(engine, store) -> dict:
    """Counts only: every old master against the new one holding its first record."""
    held, differing = Counter(), Counter()
    matched = set()
    for chunk in batched((body for body in stored(engine, "entity")
                          if body.get("status") != "alias" and body.get("subjects")), FILE):
        ids = store.bound([body["subjects"][0] for body in chunk])
        bodies = store.master_bodies(sorted(set(ids.values())))
        for body in chunk:
            entity = ids.get(body["subjects"][0])
            held[body["kind"]] += 1
            if entity is None:
                differing["no master"] += 1
                continue
            matched.add(entity)
            found = differences(body, bodies[entity])
            held["same"] += not found
            differing.update(found)
    waiting = sum(1 for body in stored(engine, "review")
                  if body.get("open") and not body.get("retired") and body.get("reason") == WAITING)
    set_aside = sum(1 for _ in stored(engine, "deferred-record"))
    now = store.totals()
    return {"masters": dict(held), "differences": dict(differing.most_common()), "only_new": now["masters"] - len(matched),
            "waiting": {"old": waiting, "new": now["waiting"]}, "set_aside": {"old": set_aside, "new": now["set_aside"]}}
