"""The links stored records state, calculated after mastering from current masters.

Links stay out of the merge. Each run calculates all of them, so a link waiting for its other end
appears once that end is mastered and needs no stored queue.
"""

from __future__ import annotations

import json
import tempfile
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from types import SimpleNamespace
from zlib import crc32

from sqlalchemy import text

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.mdm import relationships
from edgar_warehouse.mdm.survivorship import current_claims
from edgar_warehouse.silver_writer.writer import land

# The build's memory is one portion's and the ends' masters, never every record's: records are read, and links calculated, in
# this many parts held on disk.
PORTIONS = 64
TOGETHER = 0  # the portion of the types that read each other's links


class Spool:
    """Named lists of JSON values on disk, written a value at a time and read back in the order written."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.files: dict = {}
        self.counts: Counter = Counter()

    def add(self, name: str, line: str) -> None:
        if name not in self.files:
            self.files[name] = (self.folder / name).open("w", encoding="utf-8")
        self.files[name].write(line + "\n")
        self.counts[name] += 1

    def lines(self, name: str) -> Iterator[str]:
        if name in self.files:
            self.files[name].flush()
            with (self.folder / name).open(encoding="utf-8") as source:
                for line in source:
                    yield line.rstrip("\n")

    def values(self, name: str) -> Iterator:
        return map(json.loads, self.lines(name))

    def drop(self, name: str) -> None:
        if name in self.files:
            self.files.pop(name).close()
            (self.folder / name).unlink()

    def close(self) -> None:
        for handle in self.files.values():
            handle.close()


def _part(text: str) -> int:
    return crc32(text.encode()) % PORTIONS


def _together(types: dict) -> set[str]:
    """The types one calculation must hold whole: a hierarchy is walked over all its links, a succession ends links of other
    types, and an ultimate parent is another type's derived link. Every other rule reads the links of one type and source."""
    whole = {name for name, rules in types.items()
             if any(rules.get(rule) for rule in ("hierarchy", "ends_parent_links", "one_parent", "ultimate_parent"))}
    return whole | {types[name]["ultimate_type"] for name in whole if types[name].get("ultimate_type")}


def portion_of(kind: str | None, source: str, together: set[str]) -> int:
    """The part a link is calculated in: the same for every record that states it and for its stored row. `source` is the
    source's master, or its subject while it has none (the link then only waits)."""
    return TOGETHER if kind in together else 1 + _part(f"{kind} {source}")


def portions(store, policy: dict, as_of: str, last: Iterable[dict], spool: Spool) -> Iterator[tuple[list[dict], Counter]]:
    """Every link in parts, each part's links and how many of its reported links have no result yet, by reason. `last` is the
    rows of the last build, so a link keeps a start its current record no longer shows."""
    for subject, body in store.linked_records():  # a subject's records together: its revisions fold into one
        spool.add(f"records-{_part(subject)}", body.replace("\r", " ").replace("\n", " "))  # outside a text JSON holds either only as space
    ends: set[str] = set()
    for part in range(PORTIONS):
        claims = current_claims("[" + ",".join(spool.lines(f"records-{part}")) + "]", as_of, set())
        spool.drop(f"records-{part}")
        for subject, claim in claims.items():
            meta = claim["source_meta"]
            links = claim["relationships"]
            for link in links:
                ends.add(link.get("source_subject") or subject)
                if link.get("target_subject"):
                    ends.add(link["target_subject"])
            spool.add("claims", json.dumps([subject, {  # what a link reads of its record
                "relationships": links, "assertion_id": claim["assertion_id"],
                "source_meta": {"effective_at": meta["effective_at"]} if "effective_at" in meta else {}}]))
    bound = store.bound(sorted(ends))
    del ends
    masters = store.master_states(sorted(set(bound.values())))
    store.commit()
    types = relationships.types_of(policy)
    together = _together(types)
    for subject, claim in spool.values("claims"):
        split: dict[int, list] = {}
        for link in claim["relationships"]:
            source = link.get("source_subject") or subject
            split.setdefault(portion_of(link.get("type"), bound.get(source, source), together), []).append(link)
        for part, links in split.items():
            spool.add(f"links-{part}", json.dumps([subject, {**claim, "relationships": links}]))
    spool.drop("claims")
    declared: dict = {}
    for row in last:
        _declare(declared, row)
        spool.add(f"last-{portion_of(row['relationship_type'], row['source_master_id'], together)}", json.dumps(row))
    for part in range(PORTIONS + 1):
        claims = dict(spool.values(f"links-{part}"))
        if claims:
            found = {end: bound[end] for subject, claim in claims.items() for link in claim["relationships"]
                     for end in (link.get("source_subject") or subject, link.get("target_subject")) if end in bound}
            entities = set(found.values())
            state = SimpleNamespace(bindings=found, canonical={entity: entity for entity in entities})
            edges, reviews = relationships.project(
                claims, state, {entity: masters[entity] for entity in entities if entity in masters}, as_of, types=types,
                stored=stored_of(spool.values(f"last-{part}"), declared))
            yield edges, Counter(review["reason"] for review in reviews)
        spool.drop(f"links-{part}")
        spool.drop(f"last-{part}")


def calculate(store, policy: dict, as_of: str, last: Iterable[dict]) -> tuple[list[dict], Counter]:
    """Every link, by its id, and how many reported links have no result yet, by reason."""
    edges, waiting = [], Counter()
    with tempfile.TemporaryDirectory(prefix="links-") as folder:
        spool = Spool(Path(folder))
        try:
            for found, reasons in portions(store, policy, as_of, last, spool):
                edges += found
                waiting += reasons
        finally:
            spool.close()
    return sorted(edges, key=lambda edge: edge["relationship_id"]), waiting


TABLES = ("relationship", "relationship_evidence", "relationship_path")


def build(silver, mdm, policy_digest: str, as_of: str) -> dict:
    """The links table, built whole from the stored records as they are now, once a load's merges are done. A link
    keeps the start the last build gave it."""
    from edgar_warehouse.mastering.store import open_store
    from edgar_warehouse.rules import registry
    from edgar_warehouse.silver_writer.relational import DatabaseSink

    rules = registry.engine()
    try:
        with rules.connect() as conn:
            policy = registry.policy(conn, policy_digest)
    finally:
        rules.dispose()
    if policy is None:
        raise ValueError("The merge policy of the rules files is not registered: load or register a source first")
    made, waiting = 0, Counter()
    with tempfile.TemporaryDirectory(prefix="links-") as folder:
        spool = Spool(Path(folder))
        try:
            with silver.connect() as conn:
                held = conn.execute(text('select * from silver."relationship"').execution_options(
                    stream_results=True, yield_per=10_000))
                for row in held.mappings():
                    spool.add("last", json.dumps({name: value for name, value in row.items() if name in KEPT}))
            db = open_store(mdm)
            try:
                for edges, reasons in portions(db, policy, as_of, spool.values("last"), spool):
                    made += len(edges)
                    waiting += reasons
                    for table, found in rows_of(edges).items():
                        for row in found:
                            spool.add(table, json.dumps(row))
            finally:
                db.close()
            sink = DatabaseSink(silver)
            for table in TABLES:
                if spool.counts[table] or spool.counts["last"]:  # a store with no link yet stays empty (as `bind`); one that holds links is never emptied
                    land(sink, table, spool.values(table))
        finally:
            spool.close()
    if silver.dialect.name == "postgresql":
        bound = bind(silver)  # MDM and silver are schemas of one database: the join runs there, no row reaches the client
    else:
        db = open_store(mdm)  # MySQL's two schemas are two databases: the rows go through the writer
        try:
            bindings = [{"source_code": code, "source_key": key, "kind": kind, "master_id": entity}
                        for code, key, kind, entity in db.bindings()]
        finally:
            db.close()
        land(sink, "master_binding", bindings)
        bound = {"bindings": len(bindings)}
    rules = registry.engine()
    try:
        held = set_aside(silver, mdm, adapters_of(rules))
    finally:
        rules.dispose()
    return {"table": "relationship", "links": made, "rows": spool.counts["relationship"],
            "bindings": bound["bindings"], "set_aside": held, "waiting": dict(sorted(waiting.items()))}


def set_aside(silver, mdm, adapter_of) -> int:
    """`silver.set_aside`, a snapshot: each identifier of a record a classification rule held back (CONTEXT.md, Set Aside),
    keyed as a Gold link resolves (namespace, value) with the feed, the reason and the Probable Kind; no field of the record.
    The identifiers are the feed's own contract's (`adapter_of(source code)`, its adapter mapping), formatted as a stored
    record's are."""
    from edgar_warehouse.mastering.store import open_store
    from edgar_warehouse.mdm.adapters import UnsupportedRecord, record_identifiers
    from edgar_warehouse.silver_writer.relational import DatabaseSink

    rows = {}
    db = open_store(mdm)
    try:
        codes = db.held_back_sources()
        paths = sorted({path for code in codes if adapter_of(code) for path in adapter_of(code).get("identifiers", {}).values()})
        for code, reason, body in db.held_back(paths):
            mapping = adapter_of(code)
            if mapping is None:
                continue
            record = json.loads(body)
            identifiers = {}
            for namespace, path in mapping.get("identifiers", {}).items():
                try:
                    identifiers |= record_identifiers(record["raw_record"], {**mapping, "identifiers": {namespace: path}})[0]
                except UnsupportedRecord:
                    continue  # an identifier its format refuses names nothing a link could hold; the record's others still do
            probable = record.get("probable_kind")
            for namespace, values in identifiers.items():
                for one in values if isinstance(values, list) else [values]:
                    key = (namespace, one, code)
                    if key not in rows or (reason, probable or "") < (rows[key]["reason"], rows[key]["probable_kind"] or ""):
                        rows[key] = {"namespace": namespace, "value": one, "source_code": code, "reason": reason,
                                     "probable_kind": probable}  # one row a key, whichever file held it back: the first reason in order
    finally:
        db.close()
    land(DatabaseSink(silver), "set_aside", rows.values())
    return len(rows)


def adapters_of(rules):
    """The adapter mapping of each source code's current reading in the Rules Database, read once a code."""
    from functools import cache

    from edgar_warehouse.mdm.store import current_reading

    @cache
    def adapter_of(code: str):
        with rules.connect() as conn:
            found = current_reading(conn, code)
        return found[1]["adapter"] if found else None
    return adapter_of

WANTED = ("select distinct on (r.source_code, r.source_key) r.source_code, r.source_key, m.kind, r.entity_id as master_id "
          "from mdm.mastering_record r join mdm.mastering_master m on m.entity_id = r.entity_id "
          "order by r.source_code, r.source_key, r.entity_id")


def bind(silver) -> dict:
    """`silver.master_binding` (the golden record of each source record, by the source's own key) built by two statements inside
    the data database, as a snapshot: a record's row is added, a changed one is rewritten, and one whose record is gone is
    removed. A row that is unchanged is compared on the server and not written. `distinct on` keeps one row for a key two
    records share (the lowest master id). An empty result refuses, as an empty snapshot delivery does."""
    from sqlalchemy.exc import ProgrammingError

    from edgar_warehouse.silver_writer.relational import DatabaseSink, lock

    spec = DatabaseSink(silver).spec("master_binding")
    try:
        with silver.begin() as conn:
            lock(conn, spec)
            if not conn.scalar(text("select exists (select 1 from mdm.mastering_record r join mdm.mastering_master m "
                                    "on m.entity_id = r.entity_id)")):
                if conn.scalar(text("select exists (select 1 from silver.master_binding)")):
                    raise Blocked("silver.master_binding is a snapshot: an empty delivery would empty it; refused")
                return {"inserted": 0, "changed": 0, "deleted": 0, "bindings": 0}  # a store with no master yet binds nothing
            # One pass: the wanted rows (sorted once), those that are new or differ found by a join against the stored table (a bulk
            # comparison, never a key probe a row), and only those written. The wanted count comes from the same pass.
            figures = conn.execute(text(
                f"with wanted as materialized ({WANTED}), todo as (select w.* from wanted w left join silver.master_binding b "
                "on b.source_code = w.source_code and b.source_key = w.source_key where b.source_code is null or "
                "(b.kind, b.master_id) is distinct from (w.kind, w.master_id)), written as (insert into silver.master_binding "
                "(source_code, source_key, kind, master_id, loaded_at) select source_code, source_key, kind, master_id, now() "
                "from todo on conflict (source_code, source_key) do update set kind = excluded.kind, master_id = excluded.master_id, "
                "loaded_at = excluded.loaded_at where (silver.master_binding.kind, silver.master_binding.master_id) is distinct from "
                "(excluded.kind, excluded.master_id) returning (xmax = 0) as is_new) select "
                "(select count(*) from written where is_new), (select count(*) from written where not is_new), "
                "(select count(*) from wanted)")).one()
            added, changed, wanted = figures
            total = conn.scalar(text("select count(*) from silver.master_binding"))
            deleted = 0
            if total > wanted:  # a stored row has no record now: find and remove it (skipped when every stored row is wanted)
                deleted = conn.execute(text(
                    "delete from silver.master_binding b where not exists (select 1 from mdm.mastering_record r join mdm.mastering_master m "
                    "on m.entity_id = r.entity_id where r.source_code = b.source_code and r.source_key = b.source_key)")).rowcount
                total -= deleted

    except ProgrammingError as error:
        if getattr(error.orig, "pgcode", None) != "42501":
            raise
        raise Blocked("the finish login needs select on mdm.mastering_record and mdm.mastering_master, and insert, update and "
                      "delete on silver.master_binding") from None
    return {"inserted": added, "changed": changed, "deleted": deleted, "bindings": total}

PROPERTIES = ("source_event_type", "source_event_status", "source_entity_status", "source_relationship_status",
              "source_registration_status", "source_start_date_basis", "source_start_date_is_provisional")

def rows_of(edges: list[dict]) -> dict[str, list[dict]]:
    """The silver rows of the links: one row for each period of each link, the stored records that state each
    link once, and each calculated period's chain one step a row."""
    links, evidence, path = [], {}, []
    for edge in edges:
        for assertion in sorted(item["assertion_id"] for item in edge["evidence"]):
            evidence[(edge["relationship_id"], assertion)] = {
                "relationship_type": edge["type"], "relationship_id": edge["relationship_id"], "assertion_id": assertion}
        for period in edge["periods"]:
            declared = period.get("properties") or {}
            if set(declared) - set(PROPERTIES):
                raise ValueError(f"a relationship property no silver column holds: {sorted(set(declared) - set(PROPERTIES))}")
            links.append({"relationship_id": edge["relationship_id"], "relationship_type": edge["type"],
                          "scope": edge["scope"], "source_master_id": edge["source_id"],
                          "target_master_id": edge["target_id"], "valid_from": period["valid_from"],
                          "valid_from_basis": period["valid_from_basis"], "valid_to": period.get("valid_to"),
                          "valid_to_basis": period.get("valid_to_basis"), "capacity": edge.get("capacity"),
                          "derived": bool(edge.get("derived")), "last_seen": edge.get("last_seen"),
                          "ended_by": period.get("ended_by")}
                         | {name: declared.get(name) for name in PROPERTIES})
            for position, step in enumerate(period.get("path") or [], 1):
                path.append({"relationship_type": edge["type"], "relationship_id": edge["relationship_id"],
                             "valid_from": period["valid_from"], "position": position, "step_relationship_id": step})
    return {"relationship": links, "relationship_evidence": list(evidence.values()), "relationship_path": path}

def around(silver, ids: list[str], relationship_type: str = "") -> list[dict]:
    """The links touching these masters, each with all its periods."""
    names = {f"id{number}": entity for number, entity in enumerate(ids)}
    marks = ",".join(f":{name}" for name in names)
    wanted = f"(source_master_id in ({marks}) or target_master_id in ({marks}))"
    if relationship_type:
        wanted += " and relationship_type=:relationship_type"
        names["relationship_type"] = relationship_type
    links: dict = {}
    periods: dict = {}
    for row in silver.execute(text(f"select * from silver.relationship where {wanted}"), names).mappings():
        link = links.setdefault(row["relationship_id"], {
            "relationship_id": row["relationship_id"], "type": row["relationship_type"], "scope": row["scope"],
            "source_id": row["source_master_id"], "target_id": row["target_master_id"], "capacity": row["capacity"],
            "derived": row["derived"], "last_seen": row["last_seen"], "evidence": [], "periods": []})
        period = {key: row[key] for key in ("valid_from", "valid_from_basis", "valid_to", "ended_by")} | {"path": None}
        link["periods"].append(period)
        periods[(row["relationship_id"], row["valid_from"])] = period
    if links:
        found = {f"link{number}": key for number, key in enumerate(links)}
        marks = ",".join(f":{name}" for name in found)
        for row in silver.execute(text("select relationship_id, assertion_id from silver.relationship_evidence "
                                       f"where relationship_id in ({marks}) order by relationship_id, assertion_id"),
                                  found).mappings():
            links[row["relationship_id"]]["evidence"].append(row["assertion_id"])
        for row in silver.execute(text("select relationship_id, valid_from, step_relationship_id "
                                       f"from silver.relationship_path where relationship_id in ({marks}) "
                                       "order by relationship_id, valid_from, position"), found).mappings():
            period = periods.get((row["relationship_id"], row["valid_from"]))
            if period is not None:  # a chain whose period the table no longer holds is not read
                period["path"] = [*(period["path"] or []), row["step_relationship_id"]]
    return [links[key] for key in sorted(links)]

# What the next build reads of a stored row.
KEPT = {"relationship_id", "relationship_type", "scope", "source_master_id", "valid_from", "valid_from_basis", "valid_to",
        "valid_to_basis", *PROPERTIES}


def _declare(declared: dict, row: dict) -> None:
    declared.setdefault((row["relationship_type"], row["scope"]), set()).update(
        name for name in PROPERTIES if row[name] is not None)


def stored_of(rows: Iterable[dict], declared: dict) -> dict:
    """The links of the last build, in the form the calculation takes. A source rule declares the same properties for
    every period of its scope, an empty one as null: `declared` holds, by type and scope, the names some period fills."""
    found = {}
    for row in rows:
        names = declared[(row["relationship_type"], row["scope"])]
        period = {"valid_from": row["valid_from"], "valid_from_basis": row["valid_from_basis"],
                  "valid_to": row["valid_to"], "valid_to_basis": row["valid_to_basis"],
                  "properties": {name: row[name] for name in PROPERTIES if name in names}}
        if period["valid_to_basis"] is None:
            del period["valid_to_basis"]
        found.setdefault(row["relationship_id"], {"periods": []})["periods"].append(period)
    return found
