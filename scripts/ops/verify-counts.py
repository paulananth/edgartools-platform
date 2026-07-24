"""
Verify record counts across all four data layers:
  Silver DuckDB  →  MDM Postgres  →  Neo4j  →  Snowflake (gold CloudWatch)

Usage:
  python3 scripts/ops/verify-counts.py [--env dev] [--region us-east-1] [--skip-silver] [--skip-mdm] [--skip-neo4j] [--skip-gold]

Requires:
  AWS credentials  — for Secrets Manager + S3 + CloudWatch
  uv               — for duckdb + psycopg2 + neo4j dependencies
  Local packages   — edgar_warehouse.mdm (for Neo4j via verify-graph)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def hr(label: str = "") -> None:
    width = 60
    if label:
        pad = (width - len(label) - 2) // 2
        print(f"\n{'─' * pad} {label} {'─' * (width - pad - len(label) - 2)}")
    else:
        print("─" * width)


def ok(label: str, value: object) -> None:
    icon = "✓" if isinstance(value, int) and value > 0 else ("·" if value == 0 else "?")
    print(f"  {icon}  {label:<42s} {value!s:>10}")


def warn(msg: str) -> None:
    print(f"  ⚠  {msg}")


def aws_secret(name: str, region: str) -> dict | str:
    result = subprocess.run(
        ["aws", "secretsmanager", "get-secret-value",
         "--region", region,
         "--secret-id", name,
         "--query", "SecretString",
         "--output", "text"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Could not fetch secret {name}: {result.stderr.strip()}")
    raw = result.stdout.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw  # plain string secret (e.g. postgres DSN)


# ── Silver DuckDB ─────────────────────────────────────────────────────────────
def verify_silver(env: str, region: str, local_path: str | None) -> None:
    hr("SILVER DUCKDB")
    try:
        import duckdb
    except ImportError:
        warn("duckdb not installed — run: uv pip install duckdb")
        return

    if not local_path:
        # Resolve bucket from manifest
        manifest = Path(f"infra/aws-{env}-application.json")
        bucket = ""
        if manifest.exists():
            m = json.loads(manifest.read_text())
            bucket = m.get("warehouse_bucket_name", "")
        if not bucket:
            account = subprocess.run(
                ["aws", "--region", region, "sts", "get-caller-identity", "--query", "Account", "--output", "text"],
                capture_output=True, text=True,
            ).stdout.strip()
            bucket = f"edgartools-{env}-warehouse-{account}"

        s3_uri = f"s3://{bucket}/warehouse/silver/sec/silver.duckdb"
        local_path = f"/tmp/silver-verify-{env}.duckdb"
        print(f"  Downloading {s3_uri} ...")
        r = subprocess.run(
            ["aws", "s3", "cp", "--region", region, s3_uri, local_path],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            warn(f"Download failed: {r.stderr.strip()[:100]}")
            return
        size_mb = Path(local_path).stat().st_size / 1e6
        print(f"  {local_path} ({size_mb:.0f} MB)")

    conn = duckdb.connect(local_path, read_only=True)
    try:
        def count(table: str) -> int | str:
            try:
                return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            except Exception as e:
                return f"ERR: {str(e)[:40]}"

        print()
        print("  ARTIFACT PIPELINE (expect > 0 after bootstrap with ownership data)")
        ok("sec_raw_object",                  count("sec_raw_object"))
        ok("sec_filing_attachment",           count("sec_filing_attachment"))
        ok("sec_parse_run",                   count("sec_parse_run"))

        print()
        print("  OWNERSHIP DATA")
        ok("sec_ownership_reporting_owner",   count("sec_ownership_reporting_owner"))
        ok("sec_ownership_non_derivative_txn",count("sec_ownership_non_derivative_txn"))
        ok("sec_ownership_derivative_txn",    count("sec_ownership_derivative_txn"))

        print()
        print("  COMPANY / FILING")
        ok("sec_company",                     count("sec_company"))
        ok("sec_company_filing",              count("sec_company_filing"))

        print()
        print("  TRACKING STATUS")
        rows = conn.execute(
            "SELECT tracking_status, count(*) FROM sec_company_sync_state GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
        for status, n in rows:
            ok(f"  {status}", n)

        print()
        print("  SYNC RUN HISTORY (last 5)")
        rows = conn.execute(
            "SELECT sync_mode, status, count(*) FROM sec_sync_run GROUP BY 1,2 ORDER BY 3 DESC LIMIT 10"
        ).fetchall()
        for cmd, status, n in rows:
            ok(f"  {cmd} [{status}]", n)
    finally:
        conn.close()


# ── MDM Postgres ──────────────────────────────────────────────────────────────
def verify_mdm(env: str, region: str) -> None:
    hr("MDM POSTGRES")
    try:
        secret = aws_secret(f"edgartools-{env}/mdm/postgres_dsn", region)
    except RuntimeError as e:
        warn(str(e))
        return

    dsn = secret if isinstance(secret, str) else secret.get("dsn", secret.get("url", ""))
    if not dsn:
        warn("postgres_dsn secret has no 'dsn' or 'url' key")
        return

    # Normalise SQLAlchemy-style URL for psycopg2
    psycopg2_dsn = dsn.replace("postgresql+psycopg2://", "postgresql://")

    try:
        import psycopg2  # type: ignore
    except ImportError:
        warn("psycopg2 not installed — run: uv pip install psycopg2-binary")
        return

    try:
        conn = psycopg2.connect(psycopg2_dsn, connect_timeout=5)
    except Exception as e:
        warn(f"Connection failed (MDM Postgres runs on Snowflake's native Postgres service): {str(e)[:60]}")
        return

    cursor = conn.cursor()

    def count(table: str) -> int | str:
        try:
            cursor.execute(f"SELECT count(*) FROM {table}")
            return cursor.fetchone()[0]
        except Exception as e:
            conn.rollback()
            return f"ERR: {str(e)[:40]}"

    print()
    print("  ENTITIES (expect > 0 after mdm_run)")
    ok("mdm_company",             count("mdm_company"))
    ok("mdm_adviser",             count("mdm_adviser"))
    ok("mdm_person",              count("mdm_person"))
    ok("mdm_security",            count("mdm_security"))
    ok("mdm_fund",                count("mdm_fund"))

    print()
    print("  RELATIONSHIPS")
    ok("mdm_relationship_instance (total)",     count("mdm_relationship_instance"))
    try:
        cursor.execute(
            "SELECT rt.name, count(*) FROM mdm_relationship_instance ri "
            "JOIN mdm_relationship_type rt ON rt.type_id = ri.rel_type_id "
            "GROUP BY rt.name ORDER BY count(*) DESC"
        )
        rows = cursor.fetchall()
        for name, n in rows:
            ok(f"  {name}", n)
    except Exception as e:
        conn.rollback()
        warn(f"Relationship breakdown: {str(e)[:60]}")

    print()
    print("  SYNC STATE")
    try:
        cursor.execute(
            "SELECT count(*) FILTER (WHERE graph_synced_at IS NOT NULL), "
            "count(*) FILTER (WHERE graph_synced_at IS NULL), count(*) "
            "FROM mdm_relationship_instance"
        )
        synced, pending, total = cursor.fetchone()
        ok("synced to Neo4j",  synced)
        ok("pending sync",     pending)
        ok("total",            total)
    except Exception as e:
        conn.rollback()
        warn(f"Sync state: {str(e)[:60]}")

    cursor.close()
    conn.close()


# ── Neo4j ─────────────────────────────────────────────────────────────────────
def verify_neo4j(env: str, region: str) -> None:
    hr("NEO4J GRAPH")
    try:
        secret = aws_secret(f"edgartools-{env}/mdm/neo4j", region)
    except RuntimeError as e:
        warn(str(e))
        return

    uri      = secret.get("uri", "")
    user     = secret.get("user", "")
    password = secret.get("password", "")
    database = secret.get("database", "neo4j")

    if not (uri and user and password):
        warn("neo4j secret missing uri/user/password")
        return

    try:
        from neo4j import GraphDatabase  # type: ignore
    except ImportError:
        warn("neo4j driver not installed — run: uv pip install neo4j")
        return

    import logging
    logging.getLogger("neo4j").setLevel(logging.ERROR)
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session(database=database) as s:
            print()
            node_count = s.run("MATCH (n) RETURN count(n) AS n").single()["n"]
            ok("nodes (total)",  node_count)

            print()
            print("  EDGES BY RELATIONSHIP TYPE (expect IS_INSIDER > 0)")
            for rel in ["IS_INSIDER", "HOLDS", "COMPANY_HOLDS", "MANAGES_FUND", "ISSUED_BY", "IS_ENTITY_OF", "IS_PERSON_OF"]:
                n = s.run(f"MATCH ()-[r:{rel}]->() RETURN count(r) AS n").single()["n"]
                ok(f"  {rel}", n)

        driver.close()
    except Exception as e:
        warn(f"Neo4j query failed: {str(e)[:100]}")


# ── Gold / Snowflake (via CloudWatch) ─────────────────────────────────────────
def verify_gold(env: str, region: str) -> None:
    hr("GOLD / SNOWFLAKE EXPORT (latest gold_publish_completed)")

    import time
    start_ms = int((time.time() - 86400) * 1000)  # last 24 hours

    result = subprocess.run(
        ["aws", "logs", "filter-log-events",
         "--region", region,
         "--log-group-name", f"/aws/ecs/edgartools-{env}-warehouse",
         "--filter-pattern", '"gold_publish_completed"',
         "--start-time", str(start_ms),
         "--output", "json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        warn(f"CloudWatch query failed: {result.stderr.strip()[:80]}")
        return

    try:
        evts = json.loads(result.stdout).get("events", [])
    except Exception:
        warn("Could not parse CloudWatch response")
        return

    if not evts:
        warn("No gold_publish_completed events in last 24 hours")
        return

    latest = max(evts, key=lambda e: e["timestamp"])
    try:
        d = json.loads(latest["message"])
    except Exception:
        warn("Could not parse event message")
        return

    import datetime
    ts = datetime.datetime.fromtimestamp(
        latest["timestamp"] / 1000, tz=datetime.timezone.utc
    ).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n  Completed: {ts}  ({d.get('duration_seconds', 0):.1f}s)")

    print()
    print("  GOLD TABLES (internal)")
    for k, v in sorted(d.get("gold_row_counts", {}).items()):
        ok(f"  {k}", v)

    print()
    print("  SNOWFLAKE EXPORT COUNTS")
    for k, v in sorted(d.get("snowflake_export_counts", {}).items()):
        ok(f"  {k}", v)


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Verify record counts across all pipeline layers.")
    parser.add_argument("--env",          default="dev",       help="Environment (dev/prod)")
    parser.add_argument("--region",       default=os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")))
    parser.add_argument("--silver-local", default="",          help="Use local silver.duckdb instead of downloading")
    parser.add_argument("--skip-silver",  action="store_true")
    parser.add_argument("--skip-mdm",     action="store_true")
    parser.add_argument("--skip-neo4j",   action="store_true")
    parser.add_argument("--skip-gold",    action="store_true")
    args = parser.parse_args()

    print(f"\n{'═' * 60}")
    print(f"  PIPELINE VERIFICATION  ·  {args.env}  ·  {args.region}")
    print(f"{'═' * 60}")

    if not args.skip_silver:
        verify_silver(args.env, args.region, args.silver_local or None)
    if not args.skip_mdm:
        verify_mdm(args.env, args.region)
    if not args.skip_neo4j:
        verify_neo4j(args.env, args.region)
    if not args.skip_gold:
        verify_gold(args.env, args.region)

    print(f"\n{'═' * 60}\n")


if __name__ == "__main__":
    main()
