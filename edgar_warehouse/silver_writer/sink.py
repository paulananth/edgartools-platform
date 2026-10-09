"""Where silver rows land: one small interface, so a warehouse sink can follow the
PostgreSQL one (plan decision 36) without the writer changing."""

from __future__ import annotations

import datetime
import decimal
import io
import json
import math
from typing import Iterable, Protocol

from sqlalchemy import text

from edgar_warehouse.control_contract import Blocked

from . import spec as specs

CHUNK = 50_000  # rows per COPY


class Sink(Protocol):
    def spec(self, table: str) -> dict:
        """The registered spec of a table; a table with no registered spec is refused."""

    def write(self, spec: dict, rows: Iterable[dict]) -> dict:
        """Write one delivery of rows (the spec's columns and each link's MDM id) as the
        spec's load mode says, all or nothing, and count what changed."""


class PostgresSink:
    """The silver schema on PostgreSQL 16. Rows are copied as text into a staging
    table and cast there to each column's type, so a value that is not its type
    refuses the whole delivery."""

    def __init__(self, engine):
        self.engine = engine

    def spec(self, table: str) -> dict:
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT spec, sha256 FROM silver.table_spec WHERE table_name=:t"),
                               {"t": table}).first()
        if not row:
            raise Blocked(f"silver.{table} is not registered: the schema owner registers its spec first")
        if specs.sha256(row.spec) != row.sha256:
            raise Blocked(f"silver.{table}: the registered spec does not match its sha256")
        return specs.check(row.spec)

    def write(self, spec: dict, rows: Iterable[dict]) -> dict:
        from psycopg2 import DataError

        source = [c["name"] for c in spec["columns"]]
        types = {c["name"]: specs.postgres_type(c["type"]) for c in spec["columns"]}
        ids = specs.mdm_id_columns(spec)
        stamped = specs.added_time(spec)
        key = spec["key"]
        with self.engine.begin() as conn:
            q = conn.dialect.identifier_preparer.quote_identifier
            table = f"silver.{q(spec['table'])}"
            staged = source + ids
            with conn.connection.driver_connection.cursor() as cur:
                cur.execute(f"LOCK TABLE {table} IN SHARE ROW EXCLUSIVE MODE")
                cur.execute("CREATE TEMP TABLE silver_in (" + ", ".join(f"{q(c)} text" for c in staged)
                            + ") ON COMMIT DROP")
                count = 0
                for chunk in _chunks(rows, staged, types):
                    cur.copy_expert("COPY silver_in FROM STDIN", chunk[0])
                    count += chunk[1]
                if not count and spec["load_mode"] == "snapshot":
                    raise Blocked(f"silver.{spec['table']} is a snapshot: an empty delivery would empty it; refused")
                try:
                    cur.execute("CREATE TEMP TABLE silver_rows ON COMMIT DROP AS SELECT "
                                + ", ".join([f"CAST({q(c)} AS {types[c]}) AS {q(c)}" for c in source]
                                            + [q(c) for c in ids]) + " FROM silver_in")
                except DataError as exc:  # the database names the value it could not read
                    raise Blocked(f"silver.{spec['table']}: a value is not its column's type: "
                                  f"{str(exc).splitlines()[0]}") from exc
                for c in spec["columns"]:
                    if not c["nullable"]:
                        cur.execute(f"SELECT count(*) FROM silver_rows WHERE {q(c['name'])} IS NULL")
                        if cur.fetchone()[0]:
                            raise Blocked(f"silver.{spec['table']}: column {c['name']} is empty in some rows")
                keys = ", ".join(q(k) for k in key)
                cur.execute(f"SELECT count(*) FROM (SELECT 1 FROM silver_rows GROUP BY {keys} HAVING count(*) > 1) d")
                if cur.fetchone()[0]:
                    raise Blocked(f"silver.{spec['table']}: the delivery holds a key more than once")
                match = " AND ".join(f"t.{q(k)} = s.{q(k)}" for k in key)
                differs = (f"ROW({', '.join('t.' + q(c) for c in source)}) IS DISTINCT FROM "
                           f"ROW({', '.join('s.' + q(c) for c in source)})")
                cur.execute(f"SELECT count(*) FROM silver_rows s JOIN {table} t ON {match} WHERE {differs}")
                changed = cur.fetchone()[0]
                if changed and spec["load_mode"] == "append":
                    raise Blocked(f"silver.{spec['table']} is append only: {changed} delivered rows change rows "
                                  "already landed under the same key")
                written = staged + stamped
                values = [f"s.{q(c)}" for c in staged] + ["now()" for _ in stamped]
                cur.execute(f"INSERT INTO {table} ({', '.join(q(c) for c in written)}) "
                            f"SELECT {', '.join(values)} FROM silver_rows s ON CONFLICT ({keys}) DO NOTHING")
                inserted = cur.rowcount
                if changed:
                    sets = [f"{q(c)} = s.{q(c)}" for c in staged] + [f"{q(c)} = now()" for c in stamped]
                    cur.execute(f"UPDATE {table} t SET {', '.join(sets)} FROM silver_rows s WHERE {match} AND {differs}")
                ids_updated = 0
                if ids:
                    cur.execute(f"UPDATE {table} t SET {', '.join(f'{q(c)} = s.{q(c)}' for c in ids)} "
                                f"FROM silver_rows s WHERE {match} AND ROW({', '.join('t.' + q(c) for c in ids)}) "
                                f"IS DISTINCT FROM ROW({', '.join('s.' + q(c) for c in ids)})")
                    ids_updated = cur.rowcount
                deleted = 0
                if spec["load_mode"] == "snapshot":
                    cur.execute(f"DELETE FROM {table} t WHERE NOT EXISTS (SELECT 1 FROM silver_rows s WHERE {match})")
                    deleted = cur.rowcount
        return {"table": spec["table"], "rows": count, "inserted": inserted, "changed": changed,
                "deleted": deleted, "mdm_ids_updated": ids_updated}


def _chunks(rows: Iterable[dict], columns: list[str], types: dict) -> Iterable[tuple[io.StringIO, int]]:
    buffer, count = io.StringIO(), 0
    for row in rows:
        buffer.write("\t".join(_copy_text(row.get(c), types.get(c, "text"), c) for c in columns) + "\n")
        count += 1
        if count % CHUNK == 0:
            buffer.seek(0)
            yield buffer, CHUNK
            buffer = io.StringIO()
    if count % CHUNK or not count:
        buffer.seek(0)
        yield buffer, count % CHUNK


def _copy_text(value, pg_type: str, column: str) -> str:
    """One value in COPY's text format: \\N for empty, the database casts the rest."""
    if value is None:
        return r"\N"
    if pg_type == "jsonb":
        value = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, allow_nan=False)
    elif isinstance(value, (dict, list)):
        raise Blocked(f"Column {column} is {pg_type}, not a nested value")
    elif isinstance(value, bool):
        value = "true" if value else "false"
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise Blocked(f"Column {column}: {value} is not a finite number")
        value = repr(value)
    elif isinstance(value, bytes):
        value = "\\x" + value.hex()
    elif isinstance(value, (datetime.date, datetime.time)):
        value = value.isoformat()
    elif isinstance(value, decimal.Decimal):
        value = format(value, "f")
    else:
        value = str(value)
    return value.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")
