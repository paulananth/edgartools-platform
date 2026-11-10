"""Restart one source from empty: its source records go, and the golden records only it made go with them.

A golden record a rule merged keeps the older id and leaves an alias, so the aliases of the merges that touch the
golden records go too. If a golden record also holds another source's records, nothing is cleared: a replay would be
needed, and a half-clear would leave that source's identifiers on a golden record that no longer exists.
`clear` runs every delete in one transaction; without `confirm` it reports the counts and rolls back."""

from __future__ import annotations

from .store import blocks, marks

DEPENDENTS = (
    # (table, column the rows are found by, the set of values: "subjects", "masters", "source" or "all")
    ("mastering_decision", "left_id", "subjects"),
    ("mastering_decision", "left_id", "masters"),
    ("mastering_decision", "right_id", "masters"),
    ("mastering_identifier", "entity_id", "masters"),
    ("mastering_lookup", "entity_id", "masters"),
    ("mastering_name_key", "subject", "subjects"),
    ("mastering_review", "subject", "subjects"),
    ("mastering_withheld", "subject", "subjects"),
)


def _delete(store, table: str, column: str, values) -> int:
    removed = 0
    for block in blocks(values):
        store.cursor.execute(f"delete from {table} where {column} in ({marks(block)})", block)
        removed += store.cursor.rowcount
    return removed


def clear(store, source: str, *, confirm: bool = False) -> dict:
    """Preview or write the clearing of one source's footprint in the mastering tables."""
    try:
        store.take_lock()
        subjects = [r[0] for r in store.rows("select subject from mastering_record where source_code=%s", [source])]
        entities = sorted({r[0] for r in store.rows(
            "select distinct entity_id from mastering_record where source_code=%s and entity_id is not null", [source])})
        shared = 0
        for block in blocks(entities):
            shared += store.rows(f"select count(*) from mastering_record where source_code<>%s and entity_id in ({marks(block)})",
                                 [source, *block])[0][0]
        if shared:
            raise ValueError(f"{shared} records of other sources sit on golden records {source} made or joined: "
                             "nothing is cleared (they would need a replay)")
        masters = set(entities)
        for block in blocks(entities):  # the aliases of merges that touched them
            for left, right in store.rows("select left_id,right_id from mastering_decision where operation='merge' and "
                                          f"(left_id in ({marks(block)}) or right_id in ({marks(block)}))", [*block, *block]):
                masters.update((left, right))
        masters = sorted(masters)
        removed = {}
        for table, column, which in DEPENDENTS:
            removed[f"{table}.{column}"] = removed.get(f"{table}.{column}", 0) + _delete(
                store, table, column, subjects if which == "subjects" else masters)
        removed["mastering_lookup_progress"] = _count_and_clear(store, "mastering_lookup_progress")
        removed["mastering_deferred"] = _run(store, "delete from mastering_deferred where source_code=%s", [source])
        removed["mastering_file"] = _run(
            store, "delete from mastering_file where file_key in (select file_key from mastering_delivery where source_code=%s) "
            "and file_key not in (select file_key from mastering_delivery where source_code<>%s)", [source, source])
        removed["mastering_delivery"] = _run(store, "delete from mastering_delivery where source_code=%s", [source])
        removed["mastering_record"] = _run(store, "delete from mastering_record where source_code=%s", [source])
        removed["mastering_master"] = _delete(store, "mastering_master", "entity_id", masters)
        if confirm:
            store.commit()
        else:
            store.rollback()
    except BaseException:
        store.rollback()
        raise
    return {"source": source, "written": bool(confirm), "source_records": removed["mastering_record"],
            "golden_records": removed["mastering_master"], "removed": {k: v for k, v in removed.items() if v}}


def _run(store, sql: str, values) -> int:
    store.cursor.execute(sql, values)
    return store.cursor.rowcount


def _count_and_clear(store, table: str) -> int:
    """The lookups are rebuilt from the golden records that remain, so their progress starts again."""
    return _run(store, f"delete from {table}", [])
