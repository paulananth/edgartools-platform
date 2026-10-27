"""Land one delivery of a part into its registered silver table.

Each row keeps the source's own key for every link, and the master's MDM id
beside it: read from MDM by the link's Dataset Contract, kind and record key
(compared as text). A record MDM has not mastered keeps an empty id; a later
landing of the row, or `refresh_ids` for rows already landed, fills it.

A spec's data quality checks run on the delivery first (`checks.py`): a
flagged row lands with the ids of the checks it failed in its `quality`
column, and a row an exception refuses does not land.

A delivery is held in memory while its keys are looked up (the sink copies it
in bounded chunks); a part too large for that is landed in several deliveries.
"""

from __future__ import annotations

from typing import Iterable


from edgar_warehouse.control_contract import Blocked

from . import checks
from .sink import Sink


class MdmIds:
    """Record key to MDM id, read from the MDM database."""

    def __init__(self, engine):
        self.engine = engine

    def __call__(
        self, source_code: str, kind: str, keys: set[str]
    ) -> dict[str, str | None]:
        if not keys:
            return {}
        # Pointer, immutable reading and master must come from one snapshot.
        with self.engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as conn:
            from edgar_warehouse.mdm.clean.record_reads import for_connection

            return for_connection(conn).master_ids(source_code, kind, keys)


def land(sink: Sink, table: str, records: Iterable[dict], ids=None) -> dict:
    """Write records into a registered table: fields are the spec's columns (a
    field the spec does not name is refused), and each link's MDM id is looked up.
    `mdm_keys_found` counts the distinct source keys MDM knows, over all links."""
    spec = sink.spec(table)
    names = {c["name"] for c in spec["columns"]}
    rows = []
    for number, record in enumerate(records, 1):
        unknown = set(record) - names
        if unknown:
            raise Blocked(f"Record {number} holds fields silver.{table} does not name: {sorted(unknown)}")
        rows.append(record)
    rows, quality = checks.run(spec, rows)
    links = spec["links"] or []
    if links and ids is None:
        raise Blocked(f"silver.{table} links to masters: MDM ids need the MDM database (MDM_DATABASE_URL)")
    known = 0
    for link in links:
        column = link["source_key"]
        keys = {_key(r.get(column)) for r in rows} - {None}
        found = ids(link["source_code"], link["kind"], keys) if keys else {}
        for row in rows:
            row[link["mdm_id_column"]] = found.get(_key(row.get(column)))
        known += sum(1 for v in found.values() if v)
    result = sink.write(spec, rows)
    return {**result, "mdm_keys_found": known, **({"quality": quality} if quality else {})}


def refresh_ids(sink: Sink, table: str, ids) -> dict:
    """Fill (or correct) every link's MDM id on rows already landed, from MDM as it
    is now: a record mastered after its rows landed gets its id without its rows
    being delivered again; an id whose entity was merged moves to the survivor."""
    spec = sink.spec(table)
    links = spec["links"] or []
    if not links:
        return {"table": table, "rows_updated": 0}
    if ids is None:
        raise Blocked(f"silver.{table} links to masters: MDM ids need the MDM database (MDM_DATABASE_URL)")
    updated = {}
    for link in links:
        keys = sink.link_keys(spec, link)
        found = ids(link["source_code"], link["kind"], keys) if keys else {}
        updated[link["mdm_id_column"]] = sink.set_ids(spec, link, {k: found.get(k) for k in keys})
    return {"table": table, "rows_updated": updated}


def _key(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)
