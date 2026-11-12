"""silver.derive: a silver table built from other silver tables (ticket 169).

The unit's input names the build (`input.keys.build`):

- `line_items`: `company_line_item` from `company_fact` (`financials.line_items`);
- `measures`: `company_measure` from `company_line_item` (`financials.measures`),
  each company's statement format read from its Company master;
- `links`: `relationship` from the records MDM stores (`mastering.links`).

Each build rebuilds its whole table: both tables are snapshots, and the writer
removes any row a delivery lacks, so a delivery of some companies would remove
the rest. The step runs only when the Change Journal names a changed file.
SILVER_DATABASE_URL is the silver login; MDM_DATABASE_URL finds the master ids
(both tables link to the Company masters, so it is required). The output is a receipt naming the table's
rows and a digest of its keys; the check reads the table back and compares.
It does not recompute the query: the builds' own tests prove the arithmetic.
"""
from __future__ import annotations

import hashlib
import json

from edgar_warehouse.workers.silver_land import engines

CHECK = "silver.derived"
BUILDS = {"line_items": "company_line_item", "measures": "company_measure", "links": "relationship"}  # build -> the table it writes
SOURCES = {"line_items": "company_fact", "measures": "company_line_item", "links": "mastering_record"}  # build -> what it reads


def _build(envelope: dict) -> str:
    """The build the unit names; its keys also name the tables it writes (`silver`) and reads (`reads`),
    which its leases hold, so they must be this build's own."""
    keys = envelope["keys"]
    build = keys.get("build")
    if build not in BUILDS:
        raise ValueError(f"silver.derive builds one of {sorted(BUILDS)}")
    if (keys.get("silver"), keys.get("reads")) != (BUILDS[build], SOURCES[build]):
        raise ValueError(f"silver.derive {build} writes {BUILDS[build]} and reads {SOURCES[build]}")
    return build


def _floor(silver, build: str, rows: int) -> None:
    """A build over a source that holds rows gives rows, and only for companies the source holds."""
    from sqlalchemy import text

    if build == "links":  # its input is in MDM, and having no link is a real answer
        return
    source, table = SOURCES[build], BUILDS[build]
    with silver.connect() as conn:
        read = conn.execute(text(f'select count(*) from silver."{source}"')).scalar()
        strangers = conn.execute(text(f'select count(distinct company_key) from silver."{table}" where company_key '
                                      f'not in (select company_key from silver."{source}")')).scalar()
    if read and not rows:
        raise ValueError(f"silver.{table} is empty although silver.{source} holds {read} rows")
    if strangers:
        raise ValueError(f"silver.{table} holds {strangers} companies that silver.{source} does not")


def _receipt(silver, sink, build: str) -> bytes:
    """The table as it stands: its rows and a digest of its keys."""
    from sqlalchemy import text

    spec = sink.spec(BUILDS[build])
    columns = ", ".join(f'"{name}"::text' for name in spec["key"])
    with silver.connect() as conn:
        keys = sorted(tuple(row) for row in conn.execute(text(f'select {columns} from silver."{spec["table"]}"')))
    digest = hashlib.sha256(json.dumps(keys, separators=(",", ":")).encode()).hexdigest()
    return json.dumps({"version": 1, "build": build, "table": spec["table"], "rows": len(keys),
                       "keys_sha256": digest}, sort_keys=True, separators=(",", ":")).encode()


def _links(silver, mdm, sink, envelope: dict, artifacts) -> None:
    from sqlalchemy import text

    from edgar_warehouse.database_connections import storage_adapter
    from edgar_warehouse.mastering import links
    from edgar_warehouse.mastering.store import open_store
    from edgar_warehouse.silver_writer.writer import land

    shape = json.loads(artifacts.verified(envelope["input"], max_bytes=64 * 1024))
    with mdm.connect() as conn:
        policy = storage_adapter().registered_policy(conn, shape["policy"])
    if policy is None:
        raise ValueError("The run's policy is not registered")
    with silver.connect() as conn:
        last = [dict(row._mapping) for row in conn.execute(text('select * from silver."relationship"'))]
    db = open_store(mdm)
    try:
        edges, _ = links.calculate(db, policy, shape["as_of"], links.stored_of(last))
    finally:
        db.close()
    land(sink, "relationship", links.rows_of(edges))


def execute(envelope: dict, artifacts) -> dict:
    from edgar_warehouse.financials import line_items, measures
    from edgar_warehouse.silver_writer.relational import DatabaseSink
    from edgar_warehouse.silver_writer.writer import MdmIds

    if set(envelope["checks"]) != {CHECK}:
        raise ValueError(f"silver.derive verifies {CHECK} only")
    build = _build(envelope)
    silver, mdm = engines()
    try:
        if mdm is None:  # both tables link to the Company masters
            raise ValueError("silver.derive reads each company's master: set MDM_DATABASE_URL")
        sink = DatabaseSink(silver)
        if build == "links":
            _links(silver, mdm, sink, envelope, artifacts)
        elif build == "line_items":
            line_items.build(silver, sink, MdmIds(mdm))
        else:
            measures.build(silver, sink, MdmIds(mdm), lambda keys: measures.from_company(mdm, keys))
        receipt = _receipt(silver, sink, build)
        _floor(silver, build, json.loads(receipt)["rows"])
        return artifacts.put_bytes(envelope["output"], receipt)
    finally:
        silver.dispose()
        if mdm is not None:
            mdm.dispose()


def check(envelope: dict, artifacts) -> tuple[dict, list]:
    from edgar_warehouse.silver_writer.relational import DatabaseSink

    if envelope["candidate"]["uri"] != envelope["output"]:
        raise ValueError("Candidate URI differs from the intended output")
    build = _build(envelope)
    silver, _ = engines()
    try:
        held = _receipt(silver, DatabaseSink(silver), build)
        if artifacts.verified(envelope["candidate"]) != held:
            raise ValueError("The receipt differs from the table silver holds")
        _floor(silver, build, json.loads(held)["rows"])
    finally:
        silver.dispose()
    return {CHECK: True}, []
