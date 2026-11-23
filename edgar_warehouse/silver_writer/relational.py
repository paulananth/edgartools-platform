"""One atomic delivery implementation over typed selected-database storage."""
from datetime import UTC, datetime

from sqlalchemy import and_, delete, exists, func, insert, or_, select, text, update
from sqlalchemy.exc import DBAPIError, StatementError

from edgar_warehouse.control_contract import Blocked
from . import spec as specs
from .storage import registered_spec
from .tables import bound_row, data_table, staging_name

BATCH = 1000



def refusal(exc: Exception) -> str:
    """What the database refused, never a value: its SQLSTATE and the constraint, column or table it names."""
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    parts = [f"{label} {value}" for label, value in (
        ("SQLSTATE", getattr(orig, "pgcode", None)), ("constraint", getattr(diag, "constraint_name", None)),
        ("column", getattr(diag, "column_name", None)), ("table", getattr(diag, "table_name", None))) if value]
    return f" ({', '.join(parts)})" if parts else f" ({type(orig or exc).__name__})"

def delivery_refusal(table: str, exc: Exception) -> str:
    """Why a delivery failed in the database: another delivery's rows at once (retry), or a value or constraint."""
    orig = getattr(exc, "orig", None)
    if getattr(orig, "pgcode", None) in ("40P01", "40001"):
        return f"silver.{table}: another delivery changed the same rows at once; deliver again"
    detail = f": {orig}" if isinstance(orig, Blocked) else refusal(exc)
    return f"silver.{table}: a value is not its column's type or a storage constraint refused the delivery{detail}"


def lock(conn, spec):
    """One delivery at a time merges into a table: its checks and its writes see no other delivery's rows arrive."""
    if conn.dialect.name == "postgresql":
        name = conn.dialect.identifier_preparer.format_table(data_table(spec, conn.dialect.name))
        conn.exec_driver_sql(f"LOCK TABLE {name} IN SHARE ROW EXCLUSIVE MODE")
    elif conn.dialect.name == "mysql":
        modes = set(conn.scalar(text("SELECT @@session.sql_mode")).split(","))
        if not modes.intersection({"STRICT_ALL_TABLES", "STRICT_TRANS_TABLES"}):
            raise Blocked("Silver requires strict MySQL value conversion")
        conn.execute(text("CALL lock_silver_table(:t)"), {"t": spec["table"]}).close()
    else:
        raise Blocked("Silver currently supports PostgreSQL and MySQL")


class DatabaseSink:
    """The normal sink: PostgreSQL lands each batch straight into its table; MySQL stages in a permanent table."""
    def __init__(self, engine): self.engine = engine

    def spec(self, table): return registered_spec(self.engine, table)

    def write(self, spec, rows):
        # Refuse a supplied spec that differs from the registered authority.
        if spec != self.spec(spec["table"]):
            raise Blocked("Silver delivery spec differs from its registration")
        if self.engine.dialect.name == "postgresql":
            return self._write_postgres(spec, rows)
        if self.engine.dialect.name != "mysql":
            raise Blocked("Silver currently supports PostgreSQL and MySQL")
        return self._write_mysql(spec, rows)

    def _write_mysql(self, spec, rows):
        """MySQL stages a delivery in the table's permanent staging table, made at registration (no DDL at run time).
        The staging table is shared, so the table's lock comes first."""
        from sqlalchemy import LargeBinary, cast, literal
        target = data_table(spec, "mysql")
        stage = data_table(spec, "mysql", temporary=staging_name(spec))
        source = [c["name"] for c in spec["columns"]]
        groups = {"mdm_ids_updated": specs.mdm_id_columns(spec), "quality_updated": specs.quality_columns(spec)}
        staged = source + groups["mdm_ids_updated"] + groups["quality_updated"]
        key_types = {c["name"]: specs.postgres_type(c["type"]) for c in spec["columns"]}
        key_values = [func.hex(stage.c[k]) if key_types[k] == "bytea" else
                      func.nullif(stage.c[k], 0) if key_types[k] == "double precision" else stage.c[k] for k in spec["key"]]
        silver_key = func.sha2(cast(func.json_array(*key_values), LargeBinary), 256)
        match = and_(target.c._silver_key == silver_key, *(target.c[k] == stage.c[k] for k in spec["key"]))
        differs = lambda fields: or_(*(target.c[c].is_distinct_from(stage.c[c]) for c in fields))
        try:
            with self.engine.begin() as conn:
                lock(conn, spec)
                conn.execute(delete(stage))
                try:
                    count, batch = 0, []
                    for row in rows:
                        prepared = bound_row(spec, row)
                        batch.append({c: prepared.get(c) for c in staged})
                        count += 1
                        if len(batch) == BATCH:
                            conn.execute(insert(stage), batch); batch = []
                    if batch: conn.execute(insert(stage), batch)
                    if not count and spec["load_mode"] == "snapshot" and not spec.get("may_be_empty"):
                        raise Blocked(f"silver.{spec['table']} is a snapshot: an empty delivery would empty it; refused")
                    duplicates = select(func.count()).select_from(stage).group_by(silver_key).having(func.count() > 1)
                    if conn.execute(duplicates.limit(1)).first():
                        raise Blocked(f"silver.{spec['table']}: the delivery holds a key more than once")
                    now = datetime.now(UTC)
                    values = [stage.c[c] for c in staged] + [literal(now, type_=target.c[c].type) for c in specs.added_time(spec)]
                    incoming = select(*values).select_from(stage).where(~exists(select(1).select_from(target).where(match)))
                    changed = conn.scalar(select(func.count()).select_from(stage.join(target, match)).where(differs(source)))
                    if changed and spec["load_mode"] == "append":
                        raise Blocked(f"silver.{spec['table']} is append only: delivered rows change rows already landed under the same key")
                    inserted = conn.execute(insert(target).from_select(staged + specs.added_time(spec), incoming)).rowcount
                    updates = {"mdm_ids_updated": 0}
                    for name, columns in groups.items():
                        if columns:
                            updates[name] = conn.execute(update(target).where(match, differs(columns)).values(
                                {c: stage.c[c] for c in columns})).rowcount
                    if changed:
                        conn.execute(update(target).where(match, differs(source)).values(
                            {**{c: stage.c[c] for c in staged}, **{c: now for c in specs.added_time(spec)}}))
                    deleted = 0
                    if spec["load_mode"] == "snapshot":
                        deleted = conn.execute(delete(target).where(~exists(select(1).select_from(stage).where(match)))).rowcount
                finally:
                    conn.execute(delete(stage))
        except (DBAPIError, StatementError) as exc:
            raise Blocked(delivery_refusal(spec["table"], exc)) from None
        return {"table": spec["table"], "rows": count, "inserted": inserted, "changed": changed,
                "deleted": deleted, **updates}

    def _write_postgres(self, spec, rows):
        """Each batch straight into silver.<table>, with no staging table: the missing keys are inserted (a key another
        delivery inserted first is left to it), then one query finds the rows that differ, and only those are
        updated. An append table refuses a changed row, and the whole delivery rolls back. A snapshot locks its table,
        and once every row is in, the rows whose key it did not deliver are removed: both key sets are written as text
        by PostgreSQL and compared on disk in sorted runs, so neither is held whole in memory. A key repeated in one
        delivery is source processing's to refuse (a declared key, CONTEXT.md Silver Landing)."""
        from sqlalchemy import Text, bindparam, cast, column, literal, values
        from sqlalchemy.dialects.postgresql import ARRAY, insert as pg_insert
        from .keyset import KeySet

        target = data_table(spec, "postgresql")
        keys, source = list(spec["key"]), [c["name"] for c in spec["columns"]]
        groups = {"mdm_ids_updated": specs.mdm_id_columns(spec), "quality_updated": specs.quality_columns(spec)}
        written = source + groups["mdm_ids_updated"] + groups["quality_updated"]
        added, snapshot, append = specs.added_time(spec), spec["load_mode"] == "snapshot", spec["load_mode"] == "append"
        counts = {"rows": 0, "inserted": 0, "changed": 0, "deleted": 0,
                  **{name: 0 for name, columns in groups.items() if columns or name == "mdm_ids_updated"}}
        now = datetime.now(UTC)
        differs = lambda incoming, fields: or_(*(target.c[c].is_distinct_from(incoming.c[c]) for c in fields))

        # A batch travels as one typed array per column, unnested into rows: each statement below is compiled once per
        # delivery and run per batch with new arrays, never re-rendered with the rows written into its text.
        arrays = [cast(bindparam(f"c{i}", type_=ARRAY(target.c[c].type, dimensions=1)),
                       ARRAY(target.c[c].type, dimensions=1))
                  for i, c in enumerate(written)]
        incoming = func.unnest(*arrays).table_valued(
            *(column(c, target.c[c].type) for c in written), name="incoming").render_derived()
        match = and_(*(target.c[k] == incoming.c[k] for k in keys))
        missing = select(*(incoming.c[c] for c in written), *(literal(now, type_=target.c[c].type) for c in added)) \
            .where(~exists(select(1).select_from(target).where(match))).order_by(*(incoming.c[k] for k in keys))
        insert_missing = pg_insert(target).from_select(written + added, missing) \
            .on_conflict_do_nothing(index_elements=[target.c[k] for k in keys])
        find_differing = select(differs(incoming, source).label("source")).select_from(
            incoming.join(target, match)).where(differs(incoming, written))
        update_groups = {name: update(target).where(match, differs(incoming, columns)).values(
            {c: incoming.c[c] for c in columns}) for name, columns in groups.items() if columns}
        update_changed = update(target).where(match, differs(incoming, source)).values(
            {**{c: incoming.c[c] for c in written}, **{c: now for c in added}})
        delivered_keys = select(*(cast(incoming.c[k], Text) for k in keys))

        def merge(conn, batch, delivered):
            batch = {f"c{i}": [row[i] for row in batch] for i in range(len(written))}
            counts["inserted"] += conn.execute(insert_missing, batch).rowcount
            found = conn.execute(find_differing, batch).scalars().all()
            changed = sum(1 for flag in found if flag)
            if changed and append:
                raise Blocked(f"silver.{spec['table']} is append only: delivered rows change rows already landed under the same key")
            if found:
                for name, statement in update_groups.items():
                    counts[name] += conn.execute(statement, batch).rowcount
                if changed:
                    conn.execute(update_changed, batch)
                counts["changed"] += changed
            if delivered is not None:
                delivered.add(tuple(r) for r in conn.execute(delivered_keys, batch))

        def remove_absent(conn, delivered):
            removed = 0
            with KeySet() as held:
                held.add(tuple(r) for r in conn.execute(  # streamed: this statement only, never the deletes after it
                    select(*(cast(target.c[k], Text) for k in keys)).execution_options(stream_results=True, yield_per=10_000)))
                absent, wanted = [], iter(delivered.sorted())
                ahead = next(wanted, None)
                for key in held.sorted():
                    while ahead is not None and ahead < key:
                        ahead = next(wanted, None)
                    if ahead != key:
                        absent.append(key)
                    if len(absent) == BATCH:
                        removed += delete_keys(conn, absent); absent = []
                if absent:
                    removed += delete_keys(conn, absent)
            return removed

        def delete_keys(conn, absent):
            gone = values(*(column(k, Text) for k in keys), name="gone").data(absent)
            return conn.execute(delete(target).where(exists(select(1).select_from(gone).where(
                and_(*(target.c[k] == cast(gone.c[k], target.c[k].type) for k in keys)))))).rowcount

        try:
            with self.engine.begin() as conn, KeySet() as delivered:
                if snapshot:
                    lock(conn, spec)
                batch = []
                for row in rows:
                    prepared = bound_row(spec, row)
                    batch.append(tuple(prepared.get(c) for c in written))
                    counts["rows"] += 1
                    if len(batch) == BATCH:
                        merge(conn, batch, delivered if snapshot else None); batch = []
                if batch:
                    merge(conn, batch, delivered if snapshot else None)
                if snapshot:
                    if not counts["rows"] and not spec.get("may_be_empty"):
                        raise Blocked(f"silver.{spec['table']} is a snapshot: an empty delivery would empty it; refused")
                    counts["deleted"] = remove_absent(conn, delivered)
        except (DBAPIError, StatementError) as exc:
            raise Blocked(delivery_refusal(spec["table"], exc)) from None
        return {"table": spec["table"], **counts}

    def link_keys(self, spec, link):
        from sqlalchemy import cast, Text
        table = data_table(spec, self.engine.dialect.name)
        column = table.c[link["source_key"]]
        empty = table.c[link["mdm_id_column"]].is_(None)  # a row that has an id is never read again
        with self.engine.connect() as conn:
            return {str(value) for value in conn.scalars(select(cast(column, Text)).where(column.is_not(None), empty))}

    def set_ids(self, spec, link, found):
        # Refresh is coordinated with deliveries and commits as one operation.
        from sqlalchemy import case, cast, Text
        table = data_table(spec, self.engine.dialect.name)
        key, column = cast(table.c[link["source_key"]], Text), table.c[link["mdm_id_column"]]
        if self.engine.dialect.name == "mysql": key = key.collate("utf8mb4_0900_bin")
        changed = 0
        pairs = [(k, v) for k, v in found.items() if v is not None]
        with self.engine.begin() as conn:
            lock(conn, spec)
            for start in range(0, len(pairs), BATCH):
                batch = dict(pairs[start:start+BATCH])
                value = case(batch, value=key, else_=column)
                changed += conn.execute(update(table).where(key.in_(batch), column.is_(None)).values(
                    {column.name: value})).rowcount
        return changed
