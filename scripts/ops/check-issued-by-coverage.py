"""
Diagnose the Company→Security ISSUED_BY relationship pipeline end-to-end.

Traces five stages and reports where counts drop to zero:

  Stage 1  Silver DuckDB  — distinct (security_title, issuer_cik) pairs from
                            ownership transactions joined to company filings.
  Stage 2  MDM security   — mdm_security rows with issuer_entity_id populated
                            vs NULL; sample of unlinked titles.
  Stage 3  MDM instances  — mdm_relationship_instance rows for ISSUED_BY,
                            split by synced / pending.
  Stage 4  Neo4j          — ISSUED_BY edges in the graph.
  Stage 5  Diagnosis      — identifies the first stage where the count reaches
                            zero and names the likely fix.

Usage:
  uv run python scripts/ops/check-issued-by-coverage.py
  uv run python scripts/ops/check-issued-by-coverage.py --env dev --region us-east-1
  uv run python scripts/ops/check-issued-by-coverage.py --silver-local /tmp/silver.duckdb

Requires:
  AWS credentials  — for Secrets Manager + S3
  uv               — duckdb / psycopg2-binary / neo4j installed in project venv
  MDM Postgres     — VPC-private; stage 2-3 will skip gracefully if unreachable
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


# ── shared helpers ────────────────────────────────────────────────────────────

def hr(label: str = "") -> None:
    width = 62
    if label:
        pad = (width - len(label) - 2) // 2
        print(f"\n{'─' * pad} {label} {'─' * max(0, width - pad - len(label) - 2)}")
    else:
        print("─" * width)


def row(label: str, value: object, *, alert: bool = False) -> None:
    icon = "⚠ " if alert else ("✓ " if isinstance(value, int) and value > 0 else ("· " if value == 0 else "? "))
    print(f"  {icon} {label:<44s} {value!s:>8}")


def warn(msg: str) -> None:
    print(f"  ⚠  {msg}")


def aws_secret(name: str, region: str) -> dict | str:
    result = subprocess.run(
        ["aws", "secretsmanager", "get-secret-value",
         "--region", region, "--secret-id", name,
         "--query", "SecretString", "--output", "text"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Could not fetch secret {name!r}: {result.stderr.strip()}")
    raw = result.stdout.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def resolve_silver_local(env: str, region: str, silver_local: str) -> str | None:
    """Return a local DuckDB path, downloading from S3 if needed."""
    if silver_local:
        if not Path(silver_local).exists():
            warn(f"--silver-local path not found: {silver_local}")
            return None
        return silver_local

    result = subprocess.run(
        ["aws", "sts", "get-caller-identity", "--region", region,
         "--query", "Account", "--output", "text"],
        capture_output=True, text=True,
    )
    account = result.stdout.strip()
    bucket = f"edgartools-{env}-warehouse-{account}"
    s3_uri = f"s3://{bucket}/warehouse/silver/sec/silver.duckdb"
    local = f"/tmp/silver-{env}.duckdb"

    print(f"  Downloading {s3_uri} ...")
    r = subprocess.run(
        ["aws", "s3", "cp", "--region", region, s3_uri, local],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        warn(f"Download failed: {r.stderr.strip()[:120]}")
        return None
    mb = Path(local).stat().st_size / 1e6
    print(f"  Saved to {local} ({mb:.0f} MB)")
    return local


# ── Stage 1: Silver DuckDB ────────────────────────────────────────────────────

SILVER_PAIRS_SQL = """
    SELECT DISTINCT t.security_title, f.cik AS issuer_cik
    FROM   sec_ownership_non_derivative_txn t
    JOIN   sec_company_filing f ON f.accession_number = t.accession_number
    WHERE  t.security_title IS NOT NULL
"""

SILVER_ORPHAN_SQL = """
    SELECT count(*) AS n
    FROM   sec_ownership_non_derivative_txn t
    LEFT JOIN sec_company_filing f ON f.accession_number = t.accession_number
    WHERE  t.security_title IS NOT NULL AND f.cik IS NULL
"""

SILVER_SAMPLE_SQL = """
    SELECT t.security_title, f.cik AS issuer_cik
    FROM   sec_ownership_non_derivative_txn t
    JOIN   sec_company_filing f ON f.accession_number = t.accession_number
    WHERE  t.security_title IS NOT NULL
    LIMIT  5
"""


def check_silver(local_path: str) -> dict[str, Any]:
    import duckdb  # noqa: PLC0415
    conn = duckdb.connect(local_path, read_only=True)
    try:
        pairs      = conn.execute(f"SELECT count(*) FROM ({SILVER_PAIRS_SQL})").fetchone()[0]
        issuers    = conn.execute(f"SELECT count(DISTINCT issuer_cik) FROM ({SILVER_PAIRS_SQL})").fetchone()[0]
        orphans    = conn.execute(SILVER_ORPHAN_SQL).fetchone()[0]
        sample     = conn.execute(SILVER_SAMPLE_SQL).fetchall()
    finally:
        conn.close()
    return {"pairs": pairs, "issuers": issuers, "orphans": orphans, "sample": sample}


def stage_silver(env: str, region: str, silver_local: str) -> dict[str, Any]:
    hr("STAGE 1 — SILVER DUCKDB")
    try:
        import duckdb  # noqa: F401, PLC0415
    except ImportError:
        warn("duckdb not installed — run: uv pip install duckdb")
        return {}

    local = resolve_silver_local(env, region, silver_local)
    if not local:
        return {}

    r = check_silver(local)
    print()
    row("distinct (security_title, issuer_cik) pairs", r["pairs"])
    row("distinct issuer CIKs",                        r["issuers"])
    row("txn rows with no matching company filing",    r["orphans"], alert=r["orphans"] > 0)

    if r["sample"]:
        print()
        print("  Sample (security_title, issuer_cik):")
        for title, cik in r["sample"]:
            print(f"    {title!r:<40s}  cik={cik}")

    return r


# ── Stage 2 + 3: MDM Postgres ─────────────────────────────────────────────────

MDM_SECURITY_SQL = """
    SELECT
        count(*)                                          AS total,
        count(issuer_entity_id)                           AS with_issuer,
        count(*) FILTER (WHERE issuer_entity_id IS NULL)  AS without_issuer
    FROM mdm_security
"""

MDM_UNLINKED_SAMPLE_SQL = """
    SELECT canonical_title, security_type
    FROM   mdm_security
    WHERE  issuer_entity_id IS NULL
    LIMIT  5
"""

MDM_ISSUED_BY_SQL = """
    SELECT
        count(*)                                                    AS total,
        count(*) FILTER (WHERE ri.graph_synced_at IS NOT NULL)      AS synced,
        count(*) FILTER (WHERE ri.graph_synced_at IS NULL)          AS pending
    FROM   mdm_relationship_instance ri
    JOIN   mdm_relationship_type rt ON rt.rel_type_id = ri.rel_type_id
    WHERE  rt.rel_type_name = 'ISSUED_BY'
"""


def stage_mdm(env: str, region: str) -> dict[str, Any]:
    hr("STAGE 2 — MDM SECURITY ROWS")
    result: dict[str, Any] = {}

    try:
        secret = aws_secret(f"edgartools-{env}/mdm/postgres_dsn", region)
    except RuntimeError as e:
        warn(str(e))
        return result

    dsn = (secret if isinstance(secret, str) else secret.get("dsn", secret.get("url", "")))
    psycopg2_dsn = dsn.replace("postgresql+psycopg2://", "postgresql://")

    try:
        import psycopg2  # noqa: PLC0415
    except ImportError:
        warn("psycopg2 not installed — run: uv pip install psycopg2-binary")
        return result

    try:
        conn = psycopg2.connect(psycopg2_dsn, connect_timeout=5)
    except Exception as e:
        warn(f"Postgres unreachable (VPC-private — run from bastion/ECS): {str(e)[:80]}")
        return result

    def fetch_one(sql: str) -> tuple | None:
        with conn.cursor() as cur:
            try:
                cur.execute(sql)
                return cur.fetchone()
            except Exception as exc:
                conn.rollback()
                warn(f"Query failed: {exc!s:.80}")
                return None

    def fetch_all(sql: str) -> list[tuple]:
        with conn.cursor() as cur:
            try:
                cur.execute(sql)
                return cur.fetchall()
            except Exception as exc:
                conn.rollback()
                warn(f"Query failed: {exc!s:.80}")
                return []

    # Security rows
    sec = fetch_one(MDM_SECURITY_SQL)
    if sec:
        total, with_issuer, without_issuer = sec
        result["sec_total"] = total
        result["sec_with_issuer"] = with_issuer
        result["sec_without_issuer"] = without_issuer
        print()
        row("mdm_security total",                  total)
        row("  with issuer_entity_id (linked)",    with_issuer)
        row("  without issuer_entity_id (gap)",    without_issuer, alert=without_issuer > 0)

    unlinked = fetch_all(MDM_UNLINKED_SAMPLE_SQL)
    if unlinked:
        print()
        print("  Sample unlinked securities (issuer_entity_id IS NULL):")
        for title, sec_type in unlinked:
            print(f"    {title!r:<40s}  type={sec_type}")

    # Relationship instances
    hr("STAGE 3 — MDM RELATIONSHIP INSTANCES")
    inst = fetch_one(MDM_ISSUED_BY_SQL)
    if inst:
        total, synced, pending = inst
        result["inst_total"] = total
        result["inst_synced"] = synced
        result["inst_pending"] = pending
        print()
        row("ISSUED_BY instances total",    total)
        row("  synced to Neo4j",            synced)
        row("  pending sync",               pending, alert=pending > 0)

    conn.close()
    return result


# ── Stage 4: Neo4j ────────────────────────────────────────────────────────────

def stage_neo4j(env: str, region: str) -> dict[str, Any]:
    hr("STAGE 4 — NEO4J GRAPH")
    result: dict[str, Any] = {}

    try:
        secret = aws_secret(f"edgartools-{env}/mdm/neo4j", region)
    except RuntimeError as e:
        warn(str(e))
        return result

    uri      = secret.get("uri", "")
    user     = secret.get("user", "")
    password = secret.get("password", "")
    database = secret.get("database", "neo4j")

    if not (uri and user and password):
        warn("neo4j secret missing uri/user/password keys")
        return result

    try:
        from neo4j import GraphDatabase  # noqa: PLC0415
    except ImportError:
        warn("neo4j driver not installed — run: uv pip install neo4j")
        return result

    logging.getLogger("neo4j").setLevel(logging.ERROR)
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session(database=database) as s:
            n = s.run("MATCH ()-[r:ISSUED_BY]->() RETURN count(r) AS n").single()["n"]
            result["neo4j_issued_by"] = n
            print()
            row("ISSUED_BY edges in Neo4j", n, alert=n == 0)

            # Also show all rel types for context
            rels = s.run(
                "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType"
            ).data()
            print()
            print(f"  Relationship types present: {[r['relationshipType'] for r in rels]}")
        driver.close()
    except Exception as e:
        warn(f"Neo4j query failed: {str(e)[:100]}")

    return result


# ── Stage 5: Diagnosis ────────────────────────────────────────────────────────

def diagnose(silver: dict, mdm: dict, neo4j: dict) -> None:
    hr("STAGE 5 — DIAGNOSIS")
    print()

    silver_pairs = silver.get("pairs", None)
    sec_with     = mdm.get("sec_with_issuer", None)
    sec_without  = mdm.get("sec_without_issuer", None)
    inst_total   = mdm.get("inst_total", None)
    inst_pending = mdm.get("inst_pending", None)
    graph_edges  = neo4j.get("neo4j_issued_by", None)

    checks = [
        ("Silver has (security_title, issuer_cik) pairs",  silver_pairs),
        ("MDM securities with issuer_entity_id set",        sec_with),
        ("ISSUED_BY instances in mdm_relationship_instance",inst_total),
        ("ISSUED_BY edges in Neo4j",                        graph_edges),
    ]

    first_zero = None
    for label, value in checks:
        if value is None:
            icon = "─"  # skipped (layer unreachable)
        elif value == 0:
            icon = "✗"
            if first_zero is None:
                first_zero = label
        else:
            icon = "✓"
        v = "skipped" if value is None else str(value)
        print(f"  {icon}  {label:<50s} {v:>6}")

    print()
    skipped_stages = [label for label, value in checks if value is None]
    if skipped_stages:
        print(f"  Note: {len(skipped_stages)} stage(s) skipped (layer unreachable or --skip-* flag set).")
        print(f"        Skipped: {', '.join(skipped_stages)}")
        print()

    if first_zero is None and graph_edges:
        print("  ✓ Pipeline complete — ISSUED_BY is flowing end-to-end.")
        return

    if first_zero == "ISSUED_BY edges in Neo4j" and skipped_stages:
        print("  Cannot pinpoint root cause — intermediate stage(s) were skipped.")
        print("  Re-run without --skip-mdm (from a bastion or via Step Functions) for full diagnosis.")
        return

    FIXES = {
        "Silver has (security_title, issuer_cik) pairs": (
            "No ownership non-derivative transactions in silver. "
            "Run: bootstrap (or parse-ownership-bronze) to load Form 3/4/5 data."
        ),
        "MDM securities with issuer_entity_id set": (
            "Securities exist in silver but mdm_security.issuer_entity_id is NULL.\n"
            "  Why: run_securities() called _company_entity_id(issuer_cik) before the company\n"
            "  was resolved in MDM, OR issuer_cik in sec_company_filing does not match any\n"
            "  mdm_company.cik row.\n"
            "  Fix: run 'mdm run --entity-type all' again (companies must be resolved first),\n"
            "  then 'mdm backfill-relationships' to create ISSUED_BY instances."
        ),
        "ISSUED_BY instances in mdm_relationship_instance": (
            "Securities have issuer_entity_id set but no ISSUED_BY instances were created.\n"
            "  Fix: run 'mdm backfill-relationships' (via Step Functions edgartools-dev-mdm-backfill-relationships)."
        ),
        "ISSUED_BY edges in Neo4j": (
            f"ISSUED_BY instances exist in MDM (pending={inst_pending}) but are not in Neo4j.\n"
            "  Fix: run 'mdm sync-graph --limit <n>' to push pending instances."
            if inst_pending
            else "ISSUED_BY instances exist and are synced but graph shows 0 edges — check Neo4j AuraDB connectivity."
        ),
    }

    if first_zero and first_zero in FIXES:
        print(f"  Root cause at: {first_zero}")
        print()
        print(f"  Fix: {FIXES[first_zero]}")
    elif sec_without and sec_without > 0 and sec_with == 0:
        # Special case: all securities unlinked
        print("  Root cause: ALL mdm_security rows have issuer_entity_id = NULL.")
        print("  This means run_securities() never found a matching mdm_company row for any issuer_cik.")
        print()
        print("  5-Whys:")
        print("  Why 1: No ISSUED_BY edges in Neo4j")
        print("  Why 2: backfill_relationship_instances found 0 mdm_security rows with issuer_entity_id IS NOT NULL")
        print("  Why 3: mdm_security.issuer_entity_id is NULL for all rows")
        print("  Why 4: run_securities() called _company_entity_id(issuer_cik) which returned None")
        print("  Why 5: issuer_cik from sec_company_filing did not match any mdm_company.cik at run time")
        print()
        print("  Fix: run 'mdm run --entity-type all' (ensures companies exist before securities),")
        print("       then 'mdm backfill-relationships', then 'mdm sync-graph'.")
        print("       Via Step Functions: trigger bootstrap (runs all three in order).")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnose the Company→Security ISSUED_BY pipeline end-to-end."
    )
    parser.add_argument("--env",          default="dev",
                        help="Environment prefix (default: dev)")
    parser.add_argument("--region",       default=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
                        help="AWS region (default: us-east-1)")
    parser.add_argument("--silver-local", default="",
                        help="Local silver.duckdb path (skips S3 download)")
    parser.add_argument("--skip-silver",  action="store_true")
    parser.add_argument("--skip-mdm",     action="store_true",
                        help="Skip MDM Postgres stages (stages 2 & 3)")
    parser.add_argument("--skip-neo4j",   action="store_true")
    args = parser.parse_args()

    print(f"\n{'═' * 62}")
    print(f"  ISSUED_BY COVERAGE CHECK  ·  {args.env}  ·  {args.region}")
    print(f"{'═' * 62}")

    silver = stage_silver(args.env, args.region, args.silver_local) if not args.skip_silver else {}
    mdm    = stage_mdm(args.env, args.region)                       if not args.skip_mdm    else {}
    neo4j  = stage_neo4j(args.env, args.region)                     if not args.skip_neo4j  else {}

    diagnose(silver, mdm, neo4j)

    print(f"\n{'═' * 62}\n")


if __name__ == "__main__":
    main()
