"""silver.derive: a silver table built from other silver tables (ticket 169).

The unit's input names the build (`input.keys.build`):

- `line_items`: `company_line_item` from `company_fact` (`financials.line_items`);
- `line_item_inputs`: `company_line_item_input`, the terms each figure was computed from, from the same query;
- `measures`: `company_measure` from `company_line_item` (`financials.measures`),
  each company's statement format read from its Company master;
- `measure_inputs`: `company_measure_input`, the figures each measure read, from the same query;
- `links`: `relationship` from the records MDM stores (`mastering.links`).

Each build rebuilds its whole table: both tables are snapshots, and the writer
removes any row a delivery lacks, so a delivery of some companies would remove
the rest. The step runs only when the Change Journal names a changed file.
The loader file's data database: its silver schema lands the rows and its MDM schema finds the master ids
(both tables link to the Company masters, so it is required). The output is a receipt naming the table's
rows and a digest of its keys; the check reads the table back and compares.
It does not recompute the query: the builds' own tests prove the arithmetic.
"""
from __future__ import annotations

import hashlib
import json

from edgar_warehouse.workers.silver_land import engines

CHECK = "silver.derived"
# build -> the table it writes; each build runs its query once and lands that one table
BUILDS = {"line_items": "company_line_item", "line_item_inputs": "company_line_item_input",
          "measures": "company_measure", "measure_inputs": "company_measure_input"}
SOURCES = {"line_items": "company_fact", "line_item_inputs": "company_fact",  # build -> what it reads
           "measures": "company_line_item", "measure_inputs": "company_line_item"}


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

    source, table = SOURCES[build], BUILDS[build]
    with silver.connect() as conn:
        read = conn.execute(text(f'select count(*) from silver."{source}"')).scalar()
        strangers = conn.execute(text(  # not exists: `not in` scans the whole source once for every row
            f'select count(distinct t.company_key) from silver."{table}" t where not exists '
            f'(select 1 from silver."{source}" s where s.company_key = t.company_key)')).scalar()
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
            raise ValueError("silver.derive reads each company's master: source the loader file")
        sink = DatabaseSink(silver)
        if build in ("line_items", "line_item_inputs"):
            line_items.build(silver, sink, MdmIds(mdm), table=BUILDS[build])
        else:
            measures.build(silver, sink, MdmIds(mdm), lambda keys: measures.from_company(mdm, keys),
                           table=BUILDS[build])
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
