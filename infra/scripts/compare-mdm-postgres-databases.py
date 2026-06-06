#!/usr/bin/env python3
"""Compare source and target MDM Postgres databases after restore."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Iterable

try:
    import psycopg2
    from psycopg2 import sql
except ImportError as exc:  # pragma: no cover - exercised by operator environment.
    raise SystemExit("Install psycopg2, for example: uv run --extra mdm-runtime python infra/scripts/compare-mdm-postgres-databases.py ...") from exc


@dataclass(frozen=True)
class TableCheck:
    table: str
    source_count: int
    target_count: int
    source_checksum: str | None
    target_checksum: str | None

    @property
    def passed(self) -> bool:
        return self.source_count == self.target_count and self.source_checksum == self.target_checksum


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dsn", required=True, help="AWS RDS/source Postgres DSN.")
    parser.add_argument("--target-dsn", required=True, help="Snowflake Postgres target DSN.")
    parser.add_argument("--schema", default="public")
    parser.add_argument("--table", action="append", dest="tables", help="Specific table to compare. Repeatable.")
    parser.add_argument("--skip-checksum", action="store_true")
    parser.add_argument("--analyze-target", action="store_true")
    return parser.parse_args(argv)


def table_names(conn, schema: str, explicit: list[str] | None) -> list[str]:
    if explicit:
        return sorted(explicit)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            (schema,),
        )
        return [row[0] for row in cur.fetchall()]


def count_table(conn, schema: str, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SELECT count(*) FROM {}.{}").format(sql.Identifier(schema), sql.Identifier(table)))
        return int(cur.fetchone()[0])


def checksum_table(conn, schema: str, table: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                """
                SELECT COALESCE(md5(string_agg(row_hash, '' ORDER BY row_hash)), md5(''))
                FROM (
                  SELECT md5(row_to_json(t)::text) AS row_hash
                  FROM {}.{} AS t
                ) AS hashed
                """
            ).format(sql.Identifier(schema), sql.Identifier(table))
        )
        return str(cur.fetchone()[0])


def check_sequences(conn, schema: str) -> list[str]:
    failures: list[str] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT seq_ns.nspname, seq.relname, tbl_ns.nspname, tbl.relname, col.attname
            FROM pg_class AS seq
            JOIN pg_namespace AS seq_ns ON seq_ns.oid = seq.relnamespace
            JOIN pg_depend AS dep ON dep.objid = seq.oid AND dep.deptype = 'a'
            JOIN pg_class AS tbl ON tbl.oid = dep.refobjid
            JOIN pg_namespace AS tbl_ns ON tbl_ns.oid = tbl.relnamespace
            JOIN pg_attribute AS col ON col.attrelid = tbl.oid AND col.attnum = dep.refobjsubid
            WHERE seq.relkind = 'S'
              AND tbl_ns.nspname = %s
            ORDER BY seq_ns.nspname, seq.relname
            """,
            (schema,),
        )
        sequences = cur.fetchall()
    for seq_schema, seq_name, table_schema, table_name, column_name in sequences:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT last_value FROM {}.{}").format(sql.Identifier(seq_schema), sql.Identifier(seq_name)))
            last_value = int(cur.fetchone()[0])
            cur.execute(
                sql.SQL("SELECT COALESCE(max({}), 0) FROM {}.{}").format(
                    sql.Identifier(column_name),
                    sql.Identifier(table_schema),
                    sql.Identifier(table_name),
                )
            )
            max_value = int(cur.fetchone()[0])
        if last_value < max_value:
            failures.append(f"{seq_schema}.{seq_name} last_value={last_value} < {table_schema}.{table_name}.{column_name} max={max_value}")
    return failures


def compare_tables(source, target, schema: str, tables: Iterable[str], skip_checksum: bool) -> list[TableCheck]:
    checks: list[TableCheck] = []
    for table in tables:
        source_count = count_table(source, schema, table)
        target_count = count_table(target, schema, table)
        source_checksum = None if skip_checksum else checksum_table(source, schema, table)
        target_checksum = None if skip_checksum else checksum_table(target, schema, table)
        checks.append(TableCheck(table, source_count, target_count, source_checksum, target_checksum))
    return checks


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    with psycopg2.connect(args.source_dsn) as source, psycopg2.connect(args.target_dsn) as target:
        if args.analyze_target:
            target.autocommit = True
            with target.cursor() as cur:
                cur.execute(sql.SQL("ANALYZE"))
        tables = table_names(source, args.schema, args.tables)
        checks = compare_tables(source, target, args.schema, tables, args.skip_checksum)
        sequence_failures = check_sequences(target, args.schema)

    failures = [check for check in checks if not check.passed]
    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        print(
            f"{status} {check.table}: rows {check.source_count}->{check.target_count}"
            + ("" if args.skip_checksum else f", checksum {check.source_checksum}->{check.target_checksum}")
        )
    for failure in sequence_failures:
        print(f"FAIL sequence: {failure}")
    return 1 if failures or sequence_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
