"""One atomic delivery implementation over typed selected-database storage."""
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, delete, exists, func, insert, or_, select, text, update
from sqlalchemy.exc import DBAPIError, StatementError

from edgar_warehouse.control_contract import Blocked
from . import spec as specs
from .storage import registered_spec
from .tables import bound_row, data_table, staging_name

BATCH = 1000


@contextmanager
def locked(engine, spec):
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            target = data_table(spec, conn.dialect.name)
            name = conn.dialect.identifier_preparer.format_table(target)
            conn.exec_driver_sql(f"LOCK TABLE {name} IN SHARE ROW EXCLUSIVE MODE")
        elif conn.dialect.name == "mysql":
            modes = set(conn.scalar(text("SELECT @@session.sql_mode")).split(","))
            if not modes.intersection({"STRICT_ALL_TABLES", "STRICT_TRANS_TABLES"}):
                raise Blocked("Silver requires strict MySQL value conversion")
            conn.execute(text("CALL lock_silver_table(:t)"), {"t": spec["table"]}).close()
        else:
            raise Blocked("Silver currently supports PostgreSQL and MySQL")
        yield conn


class DatabaseSink:
    """The normal sink, with one delivery algorithm for PostgreSQL and MySQL."""
    def __init__(self, engine): self.engine = engine

    def spec(self, table): return registered_spec(self.engine, table)

    def write(self, spec, rows):
        # Refuse a supplied spec that differs from the registered authority.
        if spec != self.spec(spec["table"]):
            raise Blocked("Silver delivery spec differs from its registration")
        target = data_table(spec, self.engine.dialect.name)
        stage = data_table(spec, self.engine.dialect.name, temporary=staging_name(spec) if self.engine.dialect.name == "mysql" else "silver_in_" + uuid4().hex)
        source = [c["name"] for c in spec["columns"]]
        groups = {"mdm_ids_updated": specs.mdm_id_columns(spec), "quality_updated": specs.quality_columns(spec)}
        staged = source + groups["mdm_ids_updated"] + groups["quality_updated"]
        match = and_(*(target.c[k] == stage.c[k] for k in spec["key"]))
        if self.engine.dialect.name == "mysql":
            from sqlalchemy import LargeBinary, cast
            key_types = {c["name"]: specs.postgres_type(c["type"]) for c in spec["columns"]}
            key_values = [func.hex(stage.c[k]) if key_types[k] == "bytea" else
                          func.nullif(stage.c[k], 0) if key_types[k] == "double precision" else stage.c[k] for k in spec["key"]]
            match = and_(target.c._silver_key == func.sha2(cast(func.json_array(*key_values), LargeBinary), 256), match)
        differs = lambda fields: or_(*(target.c[c].is_distinct_from(stage.c[c]) for c in fields))
        try:
            with locked(self.engine, spec) as conn:
                if conn.dialect.name == "postgresql": stage.create(conn)
                else: conn.execute(delete(stage))
                try:
                    count, batch = 0, []
                    for row in rows:
                        prepared = bound_row(spec, row)
                        batch.append({c: prepared.get(c) for c in staged})
                        count += 1
                        if len(batch) == BATCH:
                            conn.execute(insert(stage), batch); batch = []
                    if batch: conn.execute(insert(stage), batch)
                    if not count and spec["load_mode"] == "snapshot":
                        raise Blocked(f"silver.{spec['table']} is a snapshot: an empty delivery would empty it; refused")
                    group_keys = [stage.c[k] for k in spec["key"]]
                    if conn.dialect.name == "mysql":
                        from sqlalchemy import cast, LargeBinary
                        group_keys = [func.sha2(cast(func.json_array(*key_values), LargeBinary), 256)]
                    duplicates = select(func.count()).select_from(stage).group_by(*group_keys).having(func.count() > 1)
                    if conn.execute(duplicates.limit(1)).first():
                        raise Blocked(f"silver.{spec['table']}: the delivery holds a key more than once")
                    changed = conn.scalar(select(func.count()).select_from(stage.join(target, match)).where(differs(source)))
                    if changed and spec["load_mode"] == "append":
                        raise Blocked(f"silver.{spec['table']} is append only: delivered rows change rows already landed under the same key")
                    now = datetime.now(UTC)
                    from sqlalchemy import literal
                    values = [stage.c[c] for c in staged] + [literal(now, type_=target.c[c].type) for c in specs.added_time(spec)]
                    incoming = select(*values).select_from(stage).where(~exists(select(1).select_from(target).where(match)))
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
                    if conn.dialect.name == "postgresql": stage.drop(conn)
                    else: conn.execute(delete(stage))
        except (DBAPIError, StatementError):
            raise Blocked(f"silver.{spec['table']}: a value is not its column's type or a storage constraint refused the delivery") from None
        return {"table": spec["table"], "rows": count, "inserted": inserted, "changed": changed,
                "deleted": deleted, **updates}

    def link_keys(self, spec, link):
        from sqlalchemy import cast, Text
        table = data_table(spec, self.engine.dialect.name)
        column = table.c[link["source_key"]]
        with self.engine.connect() as conn:
            return {str(value) for value in conn.scalars(select(cast(column, Text)).where(column.is_not(None)))}

    def set_ids(self, spec, link, found):
        # Refresh is coordinated with deliveries and commits as one operation.
        from sqlalchemy import case, cast, Text
        table = data_table(spec, self.engine.dialect.name)
        key, column = cast(table.c[link["source_key"]], Text), table.c[link["mdm_id_column"]]
        if self.engine.dialect.name == "mysql": key = key.collate("utf8mb4_0900_bin")
        changed = 0
        pairs = list(found.items())
        with locked(self.engine, spec) as conn:
            for start in range(0, len(pairs), BATCH):
                batch = dict(pairs[start:start+BATCH])
                value = case(batch, value=key, else_=column)
                changed += conn.execute(update(table).where(key.in_(batch), column.is_distinct_from(value)).values(
                    {column.name: value})).rowcount
        return changed
