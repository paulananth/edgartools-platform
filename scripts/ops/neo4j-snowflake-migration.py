#!/usr/bin/env python3
"""Generate or apply Snowflake-hosted Neo4j Graph Analytics SQL."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from edgar_warehouse.mdm.snowflake_graph import (
    DEFAULT_MDM_SCHEMA,
    DEFAULT_TARGET_SCHEMA,
    SnowflakeGraphMigrationConfig,
    generate_snowflake_graph_migration,
    run_hosted_neo4j_e2e,
    run_snowflake_graph_sql,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build Snowflake-hosted Neo4j Graph Analytics tables from Snowflake MDM "
            "mirror tables. This flow does not use external Neo4j, Aura, Bolt, or NEO4J_* credentials."
        )
    )
    parser.add_argument("--env", choices=["dev", "prod"], required=True)
    parser.add_argument("--snow-connection", required=True, help="Snowflake CLI connection name")
    parser.add_argument("--silver-path", default=None, help="Optional silver DuckDB path recorded in the generated runbook")
    parser.add_argument("--output-dir", required=True, help="Directory for generated SQL files")
    parser.add_argument("--target-database", default=None, help="Snowflake target database. Defaults to EDGARTOOLS_<ENV>.")
    parser.add_argument("--target-schema", default=DEFAULT_TARGET_SCHEMA)
    parser.add_argument("--mdm-database", default=None, help="Snowflake database containing MDM mirror tables. Defaults to target database.")
    parser.add_argument("--mdm-schema", default=DEFAULT_MDM_SCHEMA)
    parser.add_argument("--apply", action="store_true", help="Run generated SQL using `snow sql -c <connection> -f ...`")
    parser.add_argument(
        "--hosted-e2e",
        action="store_true",
        help="Run only read-only e2e validation against existing Snowflake-hosted Neo4j Graph Analytics tables",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    files = generate_snowflake_graph_migration(
        SnowflakeGraphMigrationConfig(
            env=args.env,
            output_dir=Path(args.output_dir),
            target_database=args.target_database,
            target_schema=args.target_schema,
            mdm_database=args.mdm_database,
            mdm_schema=args.mdm_schema,
            silver_path=Path(args.silver_path) if args.silver_path else None,
        )
    )
    payload: dict[str, object] = {
        "output_dir": args.output_dir,
        "files": sorted(files),
        "snow_connection": args.snow_connection,
        "applied": [],
        "external_neo4j": False,
        "note": "Neo4j Graph Analytics is Snowflake-hosted; no Aura/Bolt/NEO4J_* runtime is used.",
    }
    if args.hosted_e2e:
        payload["applied"] = run_hosted_neo4j_e2e(files, snow_connection=args.snow_connection)
    elif args.apply:
        payload["applied"] = run_snowflake_graph_sql(files, snow_connection=args.snow_connection)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
