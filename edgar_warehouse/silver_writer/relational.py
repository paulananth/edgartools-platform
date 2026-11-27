"""One atomic delivery implementation over typed selected-database storage."""
from datetime import UTC, datetime

from sqlalchemy import and_, delete, exists, func, insert, or_, select, text, update
from sqlalchemy.exc import DBAPIError, StatementError

from edgar_warehouse.control_contract import Blocked
from . import spec as specs
from .storage import registered_spec
from .tables import bound_row, data_table, staging_name

BATCH = 1000
POSTGRES_BATCH = 5000  # a landing batch is one round trip (about 70 ms on a hosted store) whatever its size, so a batch carries more rows



def refusal(exc: Exception) -> str:
    """What the database refused, never a value: its SQLSTATE and the constraint, column or table it names."""
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    parts = [f"{label} {value}" for label, value in (
        ("SQLSTATE", getattr(orig, "pgcode", None)), ("constraint", getattr(diag, "constraint_name", None)),
        ("column", getattr(diag, "column_name", None)), ("table", getattr(diag, "table_name", None))) if value]
    return f" ({', '.join(parts)})" if parts else f" ({type(orig or exc).__name__})"

# What a refusal's SQLSTATE class says (its first two characters): only a value (22) or a constraint (23) is the delivery's own.
REFUSAL_CLASSES = {
    "08": "the connection to the database was lost; deliver again",
    "22": "a value is not its column's type",
    "23": "a storage constraint refused the delivery",
    "53": "the database server ran short of a resource (53200: memory, 53100: disk, 53300: connections); deliver again once it has room",
    "57": "the database stopped the statement (a timeout, a cancel or a shutdown)",
}


def delivery_refusal(table: str, exc: Exception) -> str:
    """Why a delivery failed in the database, by its SQLSTATE class; a refusal of another class says only its code."""
    orig = getattr(exc, "orig", None)
    if isinstance(orig, Blocked):
        return f"silver.{table}: a value is not its column's type or a storage constraint refused the delivery: {orig}"
    code = str(getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None) or "")
    if code in ("40P01", "40001"):  # a deadlock or a serialization failure
        return f"silver.{table}: another delivery changed the same rows at once; deliver again"
    return f"silver.{table}: {REFUSAL_CLASSES.get(code[:2], 'the database refused the delivery')}{refusal(exc)}"


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
        groups = {"quality_updated": specs.quality_columns(spec)}
        staged = source + groups["quality_updated"]
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
                    updates = {}
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
        from sqlalchemy import BigInteger, Integer, String, Text, bindparam, cast, column, literal, true, values
        from sqlalchemy.dialects.postgresql import ARRAY, insert as pg_insert
        from .keyset import KeySet

        target = data_table(spec, "postgresql")
        keys, source = list(spec["key"]), [c["name"] for c in spec["columns"]]
        groups = {"quality_updated": specs.quality_columns(spec)}
        written = source + groups["quality_updated"]
        added, snapshot, append = specs.added_time(spec), spec["load_mode"] == "snapshot", spec["load_mode"] == "append"
        counts = {"rows": 0, "inserted": 0, "changed": 0, "deleted": 0,
                  **{name: 0 for name, columns in groups.items() if columns}}
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
        differing = select(differs(incoming, source).label("source")).select_from(
            incoming.join(target, match)).where(differs(incoming, written)).subquery("differing")
        # One round trip a batch: the missing rows are inserted and the rows that differ found in one statement. The finding reads
        # the table as it was before the insert, which is right: a row just inserted equals its incoming row and never differs.
        inserted_rows = insert_missing.returning(literal(1)).cte("inserted_rows")
        absent = select(func.count()).select_from(incoming).where(~exists(select(1).select_from(target).where(match)))
        insert_and_find = select(select(func.count()).select_from(inserted_rows).scalar_subquery().label("inserted"),
                                 absent.scalar_subquery().label("absent"), differing.c.source).select_from(
            select(literal(1).label("one")).subquery("one").outerjoin(differing, true()))
        # Another delivery that inserted one of these keys first and committed while this statement waited on it is not in the
        # snapshot the finding read: fewer rows inserted than were absent says so, and the finding is read again (an append must
        # still refuse a different value under that key).
        find_differing = select(differs(incoming, source).label("source")).select_from(
            incoming.join(target, match)).where(differs(incoming, written))
        update_groups = {name: update(target).where(match, differs(incoming, columns)).values(
            {c: incoming.c[c] for c in columns}) for name, columns in groups.items() if columns}
        update_changed = update(target).where(match, differs(incoming, source)).values(
            {**{c: incoming.c[c] for c in written}, **{c: now for c in added}})
        delivered_keys = select(*(cast(incoming.c[k], Text) for k in keys))
        # A key whose text is the same in Python and in PostgreSQL (text and whole numbers) is read from the batch; any other
        # (a timestamp, a decimal, bytes) is read back from the server as PostgreSQL writes it.
        key_at = [written.index(k) for k in keys]
        local_keys = all(isinstance(target.c[k].type, (String, Text, Integer, BigInteger)) for k in keys)

        def merge(conn, batch, delivered):
            rows_in = batch
            batch = {f"c{i}": [row[i] for row in batch] for i in range(len(written))}
            result = conn.execute(insert_and_find, batch).all()
            counts["inserted"] += result[0].inserted
            found = [r.source for r in result if r.source is not None]
            if result[0].inserted < result[0].absent:
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
                delivered.add((tuple(str(row[i]) for i in key_at) for row in rows_in) if local_keys
                              else (tuple(r) for r in conn.execute(delivered_keys, batch)))

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
                    if len(batch) == POSTGRES_BATCH:
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
