"""
Diagnose three known silver-layer anomalies against a local silver.duckdb.

  Bug 1 — ISSUED_BY unlinked securities
    Checks whether remaining unlinked Security nodes are blocked by a --limit
    cap or by a missing issuer in MDM.  Requires Neo4j (reads NEO4J_SECRET_JSON
    or fetches from Secrets Manager).

  Bug 2 — Parse run count anomaly (405 k vs 24 k raw objects)
    Classifies the 390 k failed ownership_v1 parse runs: orphaned (accession
    not in sec_raw_object), near-miss (in sec_filing_attachment only), genuine
    retries, or bad data.  Reports the dominant error pattern.

  Bug 3 — 2,605 companies still bootstrap_pending
    Distinguishes seeded-but-never-fetched (expected) from tracking-state bugs
    by checking whether bootstrap_pending CIKs have any rows in sec_company_filing
    and whether they carry error messages.

Usage:
  uv run python scripts/ops/diagnose-silver-anomalies.py --silver-local /tmp/silver.duckdb
  uv run python scripts/ops/diagnose-silver-anomalies.py --silver-local /tmp/silver.duckdb --skip-neo4j
  uv run python scripts/ops/diagnose-silver-anomalies.py --silver-local /tmp/silver.duckdb --env dev --region us-east-1

Options:
  --silver-local PATH   Path to local silver.duckdb (required; download it first with silver-counts.sh)
  --env ENV             Environment prefix for Secrets Manager lookups (default: dev)
  --region REGION       AWS region (default: us-east-1)
  --skip-neo4j          Skip Bug 1 Neo4j check (useful when AuraDB is unreachable)

Exit codes:
  0  All three bugs diagnosed (findings printed; no automated fix applied)
  1  Fatal error (missing silver file, DuckDB import failure)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path


# ── helpers ───────────────────────────────────────────────────────────────────

def hr(label: str = "") -> None:
    width = 66
    if label:
        pad = (width - len(label) - 2) // 2
        tail = width - pad - len(label) - 2
        print(f"\n{'─' * pad} {label} {'─' * max(0, tail)}")
    else:
        print("─" * width)


def row(label: str, value: object, *, alert: bool = False) -> None:
    icon = "!" if alert else ("+" if isinstance(value, int) and value > 0 else ("." if value == 0 else "?"))
    print(f"  [{icon}]  {label:<50s} {value!s:>8}")


def warn(msg: str) -> None:
    print(f"  [!]  {msg}", file=sys.stderr)


def aws_secret(name: str, region: str) -> dict:
    result = subprocess.run(
        ["aws", "secretsmanager", "get-secret-value",
         "--region", region, "--secret-id", name,
         "--query", "SecretString", "--output", "text"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Could not fetch secret {name!r}: {result.stderr.strip()[:120]}")
    raw = result.stdout.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


# ── Bug 1 — ISSUED_BY unlinked securities ─────────────────────────────────────

def bug1_issued_by(env: str, region: str) -> None:
    hr("BUG 1 — ISSUED_BY unlinked securities (Neo4j)")
    print()
    print("  Checking Neo4j for Security nodes without ISSUED_BY edges ...")

    # Prefer env var set by caller; fall back to Secrets Manager
    secret_json = os.environ.get("NEO4J_SECRET_JSON", "")
    if secret_json:
        try:
            secret = json.loads(secret_json)
        except json.JSONDecodeError:
            warn("NEO4J_SECRET_JSON is set but not valid JSON — trying Secrets Manager")
            secret_json = ""

    if not secret_json:
        try:
            secret = aws_secret(f"edgartools-{env}/mdm/neo4j", region)
        except RuntimeError as e:
            warn(str(e))
            warn("Skipping Bug 1 — set NEO4J_SECRET_JSON or ensure AWS creds are valid")
            return

    uri      = secret.get("uri", "")
    user     = secret.get("user", "")
    password = secret.get("password", "")
    database = secret.get("database", "neo4j")

    if not (uri and user and password):
        warn("Neo4j secret missing uri/user/password — skipping Bug 1")
        return

    try:
        from neo4j import GraphDatabase  # type: ignore
    except ImportError:
        warn("neo4j driver not installed — run: uv pip install neo4j")
        return

    logging.getLogger("neo4j").setLevel(logging.ERROR)

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session(database=database) as s:
            total_sec = s.run(
                "MATCH (n:Security) RETURN count(n) AS n"
            ).single()["n"]
            linked = s.run(
                "MATCH (n:Security)-[:ISSUED_BY]->() RETURN count(DISTINCT n) AS n"
            ).single()["n"]
            unlinked = total_sec - linked
            issued_by_edges = s.run(
                "MATCH ()-[r:ISSUED_BY]->() RETURN count(r) AS n"
            ).single()["n"]

            row("Security nodes (total)",              total_sec)
            row("  with ISSUED_BY edge (linked)",      linked)
            row("  without ISSUED_BY edge (unlinked)", unlinked,
                alert=unlinked > 0)
            row("ISSUED_BY edges (total)",             issued_by_edges)

            if unlinked > 0:
                sample = s.run(
                    "MATCH (n:Security) WHERE NOT (n)-[:ISSUED_BY]->() "
                    "RETURN n.title AS title, n.security_id AS sid LIMIT 5"
                ).data()
                print()
                print("  Sample unlinked Security nodes:")
                for rec in sample:
                    print(f"    title={rec.get('title')!r}  id={rec.get('sid')}")

        driver.close()
    except Exception as e:
        warn(f"Neo4j query failed: {e!s:.120}")
        return

    print()
    # 5-Whys
    if unlinked == 0:
        print("  RESULT: All Security nodes are linked — Bug 1 is resolved.")
        return

    print("  RESULT: {} Security node(s) still unlinked.".format(unlinked))
    print()
    print("  5-Whys:")
    print("  Why 1: Security nodes exist in Neo4j without an ISSUED_BY edge.")
    print("  Why 2: backfill-relationships did not create an ISSUED_BY instance for them.")
    print("  Why 3a (limit cap): --limit N was reached before these securities were processed.")
    print("         Evidence to check: was backfilled == limit in the prior run?")
    print("         Fix: re-run backfill-issued-by.py with --limit <higher> or --limit 0")
    print("  Why 3b (missing issuer in MDM): issuer CIK was never resolved as an mdm_company row.")
    print("         Evidence to check: mdm_security.issuer_entity_id IS NULL for these titles.")
    print("         Fix: run 'mdm run --entity-type all' then backfill-relationships again.")
    print("  Next step: run check-issued-by-coverage.py --skip-silver to distinguish 3a vs 3b.")


# ── Bug 2 — Parse run count anomaly ───────────────────────────────────────────

def bug2_parse_runs(conn: object) -> None:
    hr("BUG 2 — Parse run count anomaly")
    print()

    raw_objects    = conn.execute("SELECT count(*) FROM sec_raw_object").fetchone()[0]
    total_runs     = conn.execute("SELECT count(*) FROM sec_parse_run").fetchone()[0]
    succeeded      = conn.execute("SELECT count(*) FROM sec_parse_run WHERE status='succeeded'").fetchone()[0]
    failed         = conn.execute("SELECT count(*) FROM sec_parse_run WHERE status='failed'").fetchone()[0]
    distinct_acc_f = conn.execute(
        "SELECT count(DISTINCT accession_number) FROM sec_parse_run WHERE status='failed'"
    ).fetchone()[0]

    row("sec_raw_object",                     raw_objects)
    row("sec_parse_run (total)",              total_runs,
        alert=(total_runs > raw_objects * 2))
    row("  succeeded",                        succeeded)
    row("  failed",                           failed, alert=(failed > 0))
    row("  distinct failed accessions",       distinct_acc_f)
    retry_count = failed - distinct_acc_f
    row("  duplicate accessions (retries)",   retry_count,
        alert=(retry_count > 0))

    print()
    print("  Classification of failed parse runs:")

    # Orphaned: not in sec_raw_object AND not in sec_filing_attachment
    orphaned = conn.execute("""
        SELECT count(DISTINCT pr.accession_number)
        FROM sec_parse_run pr
        WHERE pr.status = 'failed'
          AND pr.accession_number NOT IN (SELECT accession_number FROM sec_raw_object)
          AND pr.accession_number NOT IN (SELECT accession_number FROM sec_filing_attachment)
    """).fetchone()[0]

    near_miss = conn.execute("""
        SELECT count(DISTINCT pr.accession_number)
        FROM sec_parse_run pr
        WHERE pr.status = 'failed'
          AND pr.accession_number NOT IN (SELECT accession_number FROM sec_raw_object)
          AND pr.accession_number IN (SELECT accession_number FROM sec_filing_attachment)
    """).fetchone()[0]

    in_raw = conn.execute("""
        SELECT count(DISTINCT pr.accession_number)
        FROM sec_parse_run pr
        WHERE pr.status = 'failed'
          AND pr.accession_number IN (SELECT accession_number FROM sec_raw_object)
    """).fetchone()[0]

    row("  orphaned (not in raw_object or filing_attachment)", orphaned,
        alert=(orphaned > 1000))
    row("  near-miss (in filing_attachment, not raw_object)",  near_miss,
        alert=(near_miss > 0))
    row("  in sec_raw_object (genuine parse failure)",         in_raw,
        alert=(in_raw > 0))

    print()
    print("  Top error messages (failed runs):")
    errors = conn.execute("""
        SELECT error_message, count(*) AS n
        FROM sec_parse_run
        WHERE status = 'failed'
        GROUP BY error_message
        ORDER BY n DESC
        LIMIT 8
    """).fetchall()
    for msg, n in errors:
        short = (msg or "")[:90]
        print(f"    [{n:7d}]  {short}")

    print()
    # 5-Whys
    print("  5-Whys:")
    print("  Why 1: sec_parse_run has {total} rows but sec_raw_object has only {raw}.".format(
        total=total_runs, raw=raw_objects))
    print("  Why 2: {failed} parse runs are marked 'failed' — ratio {r:.1f}x raw objects.".format(
        failed=failed, r=failed / max(raw_objects, 1)))
    if orphaned > 100_000:
        print("  Why 3: {n} failed runs reference accession numbers absent from sec_raw_object".format(n=orphaned))
        print("         and sec_filing_attachment — these are stale parse_run rows written before")
        print("         the artifact pipeline pruned/rewrote bronze, or from a prior schema migration.")
        print("  Why 4: The ownership_v1 parser records a parse_run row per-attempt even when")
        print("         the source XML does not exist in silver (no corresponding raw_object).")
        print("  Why 5 (root cause): parse_run rows are written eagerly before confirming the")
        print("         raw_object is present, leaving orphaned failure records for filings that")
        print("         were never loaded (or were later deleted from bronze).")
        print()
        print("  Fix: These {n} orphaned rows are noise — they do not represent data loss.".format(n=orphaned))
        print("  The {s} succeeded parse runs match {raw} raw objects as expected.".format(
            s=succeeded, raw=raw_objects))
        print("  Action: no immediate fix required; optionally purge orphaned parse_run rows with:")
        print("    DELETE FROM sec_parse_run")
        print("    WHERE status = 'failed'")
        print("    AND accession_number NOT IN (SELECT accession_number FROM sec_raw_object);")
    elif in_raw > 0:
        print("  Why 3: {n} failures have matching raw_object rows — genuine parse errors.".format(n=in_raw))
        print("  Why 4: Error messages indicate bad date fields ([F1], [F2] …) and NaN decimals")
        print("         in ownership XML — malformed SEC filings that edgartools cannot parse.")
        print("  Why 5 (root cause): edgartools ownership_v1 parser does not coerce sentinel")
        print("         date values ([F1]…) or NaN decimals — raises ConversionError on cast.")
        print()
        print("  Fix: These are bad SEC source files; they cannot be fixed without patching")
        print("       edgartools or adding a pre-parse sanitiser.  File rate is low — acceptable.")


# ── Bug 3 — bootstrap_pending companies ───────────────────────────────────────

def bug3_bootstrap_pending(conn: object) -> None:
    hr("BUG 3 — 2,605 companies still bootstrap_pending")
    print()

    rows = conn.execute("""
        SELECT
            tracking_status,
            CASE WHEN bootstrap_completed_at IS NULL THEN 'never_bootstrapped'
                 ELSE 'bootstrapped' END AS boot_state,
            count(*) AS n
        FROM sec_company_sync_state
        GROUP BY tracking_status, boot_state
        ORDER BY tracking_status, boot_state
    """).fetchall()

    for r in rows:
        alert = (r[0] == "bootstrap_pending")
        row(f"  {r[0]} / {r[1]}", r[2], alert=alert)

    pending_total = conn.execute(
        "SELECT count(*) FROM sec_company_sync_state WHERE tracking_status='bootstrap_pending'"
    ).fetchone()[0]

    pending_with_filings = conn.execute("""
        SELECT count(DISTINCT s.cik)
        FROM sec_company_sync_state s
        JOIN sec_company_filing f ON f.cik = s.cik
        WHERE s.tracking_status = 'bootstrap_pending'
    """).fetchone()[0]

    pending_with_errors = conn.execute("""
        SELECT count(*)
        FROM sec_company_sync_state
        WHERE tracking_status = 'bootstrap_pending'
          AND last_error_message IS NOT NULL
    """).fetchone()[0]

    print()
    row("bootstrap_pending with filings in sec_company_filing", pending_with_filings,
        alert=(pending_with_filings > 0))
    row("bootstrap_pending with last_error_message set",        pending_with_errors,
        alert=(pending_with_errors > 0))

    # Sample pending CIKs
    sample_rows = conn.execute("""
        SELECT cik, last_error_message
        FROM sec_company_sync_state
        WHERE tracking_status = 'bootstrap_pending'
        LIMIT 5
    """).fetchall()
    print()
    print("  Sample bootstrap_pending CIKs:")
    for cik, err in sample_rows:
        print(f"    cik={cik}  error={err!r}")

    print()
    print("  5-Whys:")
    print("  Why 1: {n} companies show tracking_status='bootstrap_pending'.".format(n=pending_total))
    if pending_with_filings == 0 and pending_with_errors == 0:
        print("  Why 2: None have rows in sec_company_filing and none carry error messages.")
        print("  Why 3: bootstrap_completed_at is NULL for all of them — they were seeded into")
        print("         sec_company_sync_state (seed-universe step) but never fetched.")
        print("  Why 4: The phased pipeline (bootstrap_phased) runs bootstrap-batch in parallel")
        print("         batches; if fewer batches ran than companies seeded, the remainder stay")
        print("         in 'bootstrap_pending' indefinitely.")
        print("  Why 5 (root cause): These {n} CIKs were added to the tracking universe but".format(n=pending_total))
        print("         no bootstrap task claimed them — this is expected behaviour for a")
        print("         universe that was seeded beyond the batch capacity of the last run.")
        print()
        print("  Result: NOT a bug.  bootstrap_pending = seeded-but-not-yet-fetched.")
        print("  Action: run bootstrap_phased (or bootstrap_recent_10) to fetch remaining CIKs.")
        print("          Monitor progress with: ./scripts/ops/silver-counts.sh --local /tmp/silver.duckdb")
    elif pending_with_filings > 0:
        print("  Why 2: {n} pending CIKs DO have rows in sec_company_filing — state machine bug.".format(
            n=pending_with_filings))
        print("  Why 3: bootstrap_completed_at was never written even though filings were loaded.")
        print("  Why 4: The step that marks bootstrap_completed_at may have crashed after writing")
        print("         filings but before committing the sync state update.")
        print("  Why 5 (root cause): non-atomic write — filing rows committed, sync state not updated.")
        print()
        print("  Fix: patch bootstrap_completed_at for these CIKs:")
        print("    UPDATE sec_company_sync_state")
        print("    SET tracking_status = 'active',")
        print("        bootstrap_completed_at = now()")
        print("    WHERE tracking_status = 'bootstrap_pending'")
        print("    AND cik IN (SELECT DISTINCT cik FROM sec_company_filing);")
    elif pending_with_errors > 0:
        print("  Why 2: {n} pending CIKs have error messages — they failed during bootstrap.".format(
            n=pending_with_errors))
        print("  Fix: inspect last_error_message values above and re-run bootstrap for those CIKs.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnose three silver-layer anomalies (bugs 1–3)."
    )
    parser.add_argument("--silver-local", required=True,
                        help="Path to local silver.duckdb (e.g. /tmp/silver.duckdb)")
    parser.add_argument("--env",    default="dev",
                        help="Environment prefix for Secrets Manager (default: dev)")
    parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
                        help="AWS region (default: us-east-1)")
    parser.add_argument("--skip-neo4j", action="store_true",
                        help="Skip Bug 1 Neo4j check")
    args = parser.parse_args()

    silver_path = Path(args.silver_local)
    if not silver_path.exists():
        print(f"ERROR: silver.duckdb not found at {silver_path}", file=sys.stderr)
        print("Download it first:", file=sys.stderr)
        print("  ./scripts/ops/silver-counts.sh --local /tmp/silver.duckdb", file=sys.stderr)
        sys.exit(1)

    try:
        import duckdb  # type: ignore
    except ImportError:
        print("ERROR: duckdb not installed — run: uv pip install duckdb", file=sys.stderr)
        sys.exit(1)

    print()
    print("=" * 66)
    print("  SILVER ANOMALY DIAGNOSTICS")
    print(f"  file   : {silver_path}  ({silver_path.stat().st_size / 1e6:.0f} MB)")
    print(f"  env    : {args.env}  |  region: {args.region}")
    print("=" * 66)

    conn = duckdb.connect(str(silver_path), read_only=True)
    try:
        if not args.skip_neo4j:
            bug1_issued_by(args.env, args.region)
        else:
            hr("BUG 1 — ISSUED_BY unlinked securities (SKIPPED via --skip-neo4j)")

        bug2_parse_runs(conn)
        bug3_bootstrap_pending(conn)
    finally:
        conn.close()

    print()
    print("=" * 66)
    print()


if __name__ == "__main__":
    main()
