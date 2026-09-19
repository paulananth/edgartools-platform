"""Load silver-landing Parquet into a local PostgreSQL silver database.

Used when Snowflake is unavailable. MDM mastering then reads
SILVER_DATABASE_URL instead of EDGARTOOLS_SILVER.

Usage:
    uv run python infra/scripts/load_local_silver_landing.py \
        --landing-root /tmp/edgartools-local-fewco/silver-landing \
        --database-url postgresql://postgres:test@127.0.0.1:5432/silver
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import create_engine, text


def pg_type(field: pa.Field) -> str:
    t = field.type
    if pa.types.is_dictionary(t):
        t = t.value_type
    if pa.types.is_int64(t) or pa.types.is_int32(t) or pa.types.is_int16(t):
        return "BIGINT"
    if pa.types.is_boolean(t):
        return "BOOLEAN"
    if pa.types.is_timestamp(t):
        return "TIMESTAMPTZ"
    if pa.types.is_date(t):
        return "DATE"
    if pa.types.is_floating(t):
        return "DOUBLE PRECISION"
    return "TEXT"


def python_value(value):
    if value is None:
        return None
    if hasattr(value, "as_py"):
        value = value.as_py()
    return value


def load_parquet(engine, path: Path, table_name: str) -> int:
    table = pq.read_table(path)
    columns = list(table.schema.names)
    col_sql = ", ".join(f"{name} {pg_type(table.schema.field(name))}" for name in columns)
    placeholders = ", ".join(f":{name}" for name in columns)
    insert_sql = text(
        f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
    )
    with engine.begin() as conn:
        conn.execute(text(f"CREATE TABLE IF NOT EXISTS {table_name} ({col_sql})"))
        conn.execute(text(f"TRUNCATE {table_name}"))
        rows = table.to_pylist()
        for row in rows:
            conn.execute(insert_sql, {k: python_value(row.get(k)) for k in columns})
    return table.num_rows


def ensure_ticker_table(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS sec_company_ticker (
                    cik BIGINT,
                    ticker TEXT,
                    exchange TEXT,
                    source_name TEXT,
                    source_rank INTEGER,
                    last_sync_run_id TEXT,
                    last_synced_at TIMESTAMPTZ
                )
                """
            )
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--landing-root", required=True)
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args(argv)
    root = Path(args.landing_root)
    engine = create_engine(args.database_url, pool_pre_ping=True)
    loaded = {}
    for parquet in sorted(root.rglob("*.parquet")):
        relative = parquet.relative_to(root)
        table_name = relative.parts[0]
        if table_name in {"manifests"} or parquet.name.startswith("."):
            continue
        loaded[table_name] = load_parquet(engine, parquet, table_name)
    ensure_ticker_table(engine)
    for name, n in sorted(loaded.items()):
        sys.stderr.write(f"{name}: {n} rows\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
