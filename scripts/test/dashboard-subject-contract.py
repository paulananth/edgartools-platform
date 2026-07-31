#!/usr/bin/env python3
"""Real Snowflake acceptance checks for the deployed dashboard subject contract.

This is intentionally not a fixture or an AppTest.  It executes against the
configured SnowCLI connection and asserts the deployed resolver can find the
known SEC issuer AAPL without using dashboard readiness as a condition.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any


def query(connection: str, statement: str) -> list[dict[str, Any]]:
    completed = subprocess.run(
        ["snow", "sql", "--connection", connection, "--format", "json", "--query", statement],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(detail or f"snow sql exited {completed.returncode}")
    payload = json.loads(completed.stdout)
    # SnowCLI emits a list of result sets when USE ROLE is included.
    if payload and isinstance(payload[0], list):
        return payload[-1]
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--connection", required=True)
    parser.add_argument("--database", default="EDGARTOOLS_PROD")
    args = parser.parse_args()
    db = args.database
    statements = {
        "aapl": f"""
            USE ROLE {db}_DASHBOARD_OWNER;
            SELECT CIK, ENTITY_NAME, TICKERS, RESOLUTION_SOURCE
            FROM {db}.EDGARTOOLS_DECISION.DASHBOARD_SUBJECT_RESOLVER
            WHERE TICKERS ILIKE '%AAPL%'
            ORDER BY CIK
            LIMIT 2;
        """,
        "unknown": f"""
            USE ROLE {db}_DASHBOARD_OWNER;
            SELECT CIK
            FROM {db}.EDGARTOOLS_DECISION.DASHBOARD_SUBJECT_RESOLVER
            WHERE ENTITY_NAME ILIKE '%ZZZZ%' OR TICKERS ILIKE '%ZZZZ%'
            LIMIT 1;
        """,
    }
    aapl = query(args.connection, statements["aapl"])
    unknown = query(args.connection, statements["unknown"])
    if not any(int(row["CIK"]) == 320193 for row in aapl):
        raise AssertionError(f"AAPL must resolve to CIK 320193; got {aapl!r}")
    if unknown:
        raise AssertionError(f"ZZZZ must be a no-match; got {unknown!r}")
    print(json.dumps({"aapl": aapl, "unknown": "no_match"}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, AssertionError, json.JSONDecodeError) as exc:
        print(f"dashboard subject contract failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
