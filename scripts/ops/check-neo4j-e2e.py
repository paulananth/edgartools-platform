"""
Neo4j IS_INSIDER E2E path checker.

Walks every stage of the chain and reports counts + first-failure point:

  1. Silver DuckDB  — sec_company_filing (Form 4 rows), sec_raw_object,
                      sec_filing_attachment, sec_parse_run,
                      sec_ownership_reporting_owner
  2. MDM Postgres   — mdm_person, mdm_relationship_instance (IS_INSIDER)
  3. Neo4j          — nodes, IS_INSIDER edges

Also runs a live probe: picks the first Form 4 accession that has a
primary_document in silver, fetches the document from SEC, parses it
with edgar.ownership.Ownership.from_xml(), and reports what it would
produce — confirming the parse path works end-to-end before the full
pipeline runs.

Usage:
  python3 scripts/ops/check-neo4j-e2e.py [--env dev] [--probe] [--fix-path]
  ./scripts/ops/verify-counts.sh --skip-gold   # shortcut using wrapper
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def aws_secret(name: str, region: str) -> dict | str:
    result = subprocess.run(
        ["aws", "secretsmanager", "get-secret-value", "--region", region,
         "--secret-id", name, "--query", "SecretString", "--output", "text"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Cannot fetch secret {name}: {result.stderr.strip()[:80]}")
    raw = result.stdout.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def hr(label: str = "") -> None:
    w = 62
    if label:
        pad = (w - len(label) - 2) // 2
        print(f"\n{'─'*pad} {label} {'─'*(w-pad-len(label)-2)}")
    else:
        print("─" * w)


def ok(label: str, value: object, required: bool = False) -> bool:
    icon = "✓" if (isinstance(value, int) and value > 0) else "·"
    if required and (not isinstance(value, int) or value == 0):
        icon = "✗"
    print(f"  {icon}  {label:<44s} {value!s:>8}")
    return icon == "✓"


# ── 1. Silver DuckDB ──────────────────────────────────────────────────────────
def check_silver(env: str, region: str, local_path: str | None) -> dict:
    hr("SILVER DUCKDB")
    try:
        import duckdb
    except ImportError:
        print("  ⚠  duckdb not installed"); return {}

    if not local_path:
        manifest = Path(f"infra/aws-{env}-application.json")
        bucket = json.loads(manifest.read_text()).get("warehouse_bucket_name", "") if manifest.exists() else ""
        if not bucket:
            acct = subprocess.run(["aws", "--region", region, "sts", "get-caller-identity",
                                    "--query", "Account", "--output", "text"],
                                  capture_output=True, text=True).stdout.strip()
            bucket = f"edgartools-{env}-warehouse-{acct}"
        local_path = f"/tmp/silver-neo4j-e2e-{env}.duckdb"
        print(f"  Downloading silver.duckdb …")
        subprocess.run(["aws", "s3", "cp", "--region", region,
                        f"s3://{bucket}/warehouse/silver/sec/silver.duckdb", local_path],
                       capture_output=True)
        size_mb = Path(local_path).stat().st_size / 1e6
        print(f"  {local_path} ({size_mb:.0f} MB)")

    conn = duckdb.connect(local_path, read_only=True)
    results = {}
    try:
        def q(sql: str):
            try: return conn.execute(sql).fetchone()[0]
            except: return "ERR"

        print()
        print("  FILINGS WITH OWNERSHIP FORMS (source for IS_INSIDER)")
        form4 = q("SELECT count(*) FROM sec_company_filing WHERE form IN ('3','3/A','4','4/A','5','5/A')")
        ok("Form 3/4/5 filings in silver",       form4, required=True)
        primaries = q("SELECT count(*) FROM sec_company_filing WHERE form IN ('3','3/A','4','4/A','5','5/A') AND primary_document IS NOT NULL AND primary_document <> ''")
        ok("  …with primary_document known",     primaries, required=True)
        results["form4_count"] = form4
        results["primaries_known"] = primaries

        print()
        print("  ARTIFACT PIPELINE OUTPUT")
        raw  = q("SELECT count(*) FROM sec_raw_object")
        att  = q("SELECT count(*) FROM sec_filing_attachment")
        runs = q("SELECT count(*) FROM sec_parse_run")
        ok("sec_raw_object",                     raw,  required=True)
        ok("sec_filing_attachment",              att,  required=True)
        ok("sec_parse_run",                      runs, required=True)
        results.update(raw_object=raw, filing_attachment=att, parse_run=runs)

        print()
        print("  OWNERSHIP DATA (needed by MDM for IS_INSIDER)")
        owners = q("SELECT count(*) FROM sec_ownership_reporting_owner")
        txn_nd = q("SELECT count(*) FROM sec_ownership_non_derivative_txn")
        ok("sec_ownership_reporting_owner",      owners, required=True)
        ok("sec_ownership_non_derivative_txn",   txn_nd)
        results.update(ownership_owners=owners, ownership_txn=txn_nd)

        # First Form 4 accession with known primary_document — useful for probe
        row = conn.execute("""
            SELECT accession_number, cik, primary_document
            FROM sec_company_filing
            WHERE form IN ('4','4/A')
              AND primary_document IS NOT NULL
              AND primary_document <> ''
            ORDER BY filing_date DESC
            LIMIT 1
        """).fetchone()
        if row:
            results["sample_accession"] = row[0]
            results["sample_cik"]       = row[1]
            results["sample_primary"]   = row[2]
            print(f"\n  Sample Form 4: cik={row[1]}  accession={row[0]}  doc={row[2]}")
    finally:
        conn.close()
    return results


# ── 2. MDM Postgres ───────────────────────────────────────────────────────────
def check_mdm(env: str, region: str) -> dict:
    hr("MDM POSTGRES")
    try:
        secret = aws_secret(f"edgartools-{env}/mdm/postgres_dsn", region)
    except RuntimeError as e:
        print(f"  ⚠  {e}"); return {}

    dsn = (secret if isinstance(secret, str) else secret.get("dsn", "")).replace("postgresql+psycopg2://", "postgresql://")
    try:
        import psycopg2
        conn = psycopg2.connect(dsn, connect_timeout=5)
    except Exception as e:
        print(f"  ⚠  MDM Postgres unreachable: {str(e)[:60]}"); return {}

    cur = conn.cursor()
    results = {}
    def q(sql: str):
        try: cur.execute(sql); return cur.fetchone()[0]
        except Exception as e: conn.rollback(); return f"ERR: {str(e)[:30]}"

    print()
    print("  ENTITIES")
    ok("mdm_company",                     q("SELECT count(*) FROM mdm_company"), required=True)
    ok("mdm_person",                      q("SELECT count(*) FROM mdm_person"),  required=True)

    print()
    print("  RELATIONSHIPS (IS_INSIDER requires ownership data in silver)")
    total = q("SELECT count(*) FROM mdm_relationship_instance")
    ok("mdm_relationship_instance total", total, required=True)
    results["mdm_relationships"] = total

    try:
        cur.execute("""
            SELECT rt.name, count(*) n,
                   count(*) FILTER (WHERE ri.graph_synced_at IS NOT NULL) AS synced
            FROM mdm_relationship_instance ri
            JOIN mdm_relationship_type rt ON rt.type_id = ri.rel_type_id
            GROUP BY rt.name ORDER BY n DESC
        """)
        for name, n, synced in cur.fetchall():
            icon = "✓" if n > 0 else "·"
            print(f"    {icon}  {name:<30s} {n:>8}  ({synced} synced to Neo4j)")
            if name == "IS_INSIDER":
                results["is_insider_count"] = n
    except Exception as e:
        conn.rollback()
        print(f"    ⚠ {str(e)[:60]}")

    cur.close(); conn.close()
    return results


# ── 3. Neo4j ─────────────────────────────────────────────────────────────────
def check_neo4j(env: str, region: str) -> dict:
    hr("NEO4J GRAPH")
    try:
        secret = aws_secret(f"edgartools-{env}/mdm/neo4j", region)
    except RuntimeError as e:
        print(f"  ⚠  {e}"); return {}

    import logging; logging.getLogger("neo4j").setLevel(logging.ERROR)
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            secret.get("uri", ""), auth=(secret.get("user",""), secret.get("password","")))
        results = {}
        with driver.session(database=secret.get("database","neo4j")) as s:
            nodes = s.run("MATCH (n) RETURN count(n) AS n").single()["n"]
            ok("nodes total",  nodes, required=True)
            for rel in ["IS_INSIDER","HOLDS","COMPANY_HOLDS","MANAGES_FUND","ISSUED_BY","IS_ENTITY_OF","IS_PERSON_OF"]:
                n = s.run(f"MATCH ()-[r:{rel}]->() RETURN count(r) AS n").single()["n"]
                ok(f"  {rel}", n, required=(rel == "IS_INSIDER"))
                if rel == "IS_INSIDER": results["neo4j_is_insider"] = n
        driver.close()
        return results
    except Exception as e:
        print(f"  ⚠ {str(e)[:80]}"); return {}


# ── 4. Live probe — fetch + parse one Form 4 ─────────────────────────────────
def probe_form4_parse(cik: int, accession_number: str, primary_document: str,
                      edgar_identity: str, region: str) -> None:
    hr("LIVE PROBE — fetch + parse one Form 4")
    print(f"  cik={cik}  accession={accession_number}  doc={primary_document}")

    # Strip XSLT prefix (xslXXX/filename.xml → filename.xml) and fetch directly.
    # The -index.html returns 503; raw document URLs return 200.
    acc_clean = accession_number.replace("-", "")
    parts = primary_document.replace("\\", "/").split("/")
    raw_doc = "/".join(parts[1:]) if len(parts) >= 2 and parts[0].lower().startswith("xsl") else primary_document
    doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{raw_doc}"
    print(f"  primary_document : {primary_document}")
    print(f"  raw_doc (no xsl) : {raw_doc}")
    print(f"  URL: {doc_url}")

    try:
        import httpx
        resp = httpx.get(doc_url, headers={"User-Agent": edgar_identity,
                                            "Accept": "*/*"}, timeout=15.0)
        print(f"  HTTP status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"  ✗ Document fetch failed — {resp.status_code}")
            # Also try the index to compare
            idx_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{acc_clean}-index.html"
            r2 = httpx.get(idx_url, headers={"User-Agent": edgar_identity}, timeout=10.0, follow_redirects=True)
            print(f"  Index URL status: {r2.status_code} (for comparison)")
            return

        print(f"  ✓ Fetched {len(resp.content)} bytes")
        content = resp.text

        from edgar.ownership import Ownership
        try:
            import edgar
            edgar.set_identity(edgar_identity)
        except Exception:
            pass
        parsed = Ownership.from_xml(content)
        owners = parsed.get("sec_ownership_reporting_owner", [])
        txns   = parsed.get("sec_ownership_non_derivative_txn", [])
        print(f"  ✓ Parsed: {len(owners)} reporting owners, {len(txns)} non-deriv txns")
        for o in owners[:3]:
            print(f"    owner: {o.get('owner_name')} (CIK {o.get('owner_cik')})"
                  f" → issuer CIK {o.get('issuer_cik')}")
        print("  → This data would become IS_INSIDER edges in Neo4j via MDM")
    except ImportError as e:
        print(f"  ⚠ Missing dependency: {e}")
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {str(e)[:100]}")


# ── Summary ───────────────────────────────────────────────────────────────────
def summary(silver: dict, mdm: dict, neo4j: dict) -> None:
    hr("IS_INSIDER PATH SUMMARY")
    chain = [
        ("Form 4 filings in silver",         silver.get("form4_count", 0),       True),
        ("primary_document known",           silver.get("primaries_known", 0),    True),
        ("sec_raw_object rows",              silver.get("raw_object", 0),          True),
        ("sec_filing_attachment rows",       silver.get("filing_attachment", 0),   True),
        ("sec_ownership_reporting_owner",    silver.get("ownership_owners", 0),    True),
        ("mdm_relationship_instance total",  mdm.get("mdm_relationships", 0),      True),
        ("IS_INSIDER in MDM",                mdm.get("is_insider_count", 0),       True),
        ("IS_INSIDER edges in Neo4j",        neo4j.get("neo4j_is_insider", 0),     True),
    ]
    print()
    first_fail = None
    for label, value, required in chain:
        n = value if isinstance(value, int) else 0
        if n > 0:
            print(f"  ✓  {label:<44s} {n:>8}")
        else:
            print(f"  ✗  {label:<44s} {str(value):>8}  ← BROKEN HERE")
            if first_fail is None:
                first_fail = label

    print()
    if first_fail:
        print(f"  Pipeline broken at: {first_fail}")
        print()
        if "sec_raw_object" in first_fail or "sec_filing_attachment" in first_fail:
            print("  Root cause: www.sec.gov/Archives/-index.html returns 503.")
            print("  Fix: skip index fetch — use primary_document from silver directly.")
            print("  → see fix_skip_index_fetch in bronze_filing_artifacts.py")
        elif "ownership_reporting_owner" in first_fail:
            print("  Root cause: artifact pipeline ran but parse produced no owners.")
            print("  → Check sec_parse_run for failed runs.")
        elif "IS_INSIDER in MDM" in first_fail:
            print("  Root cause: mdm run found no sec_ownership_reporting_owner rows.")
            print("  → Re-run: ./scripts/ops/trigger.sh mdm-gold")
        elif "Neo4j" in first_fail:
            print("  Root cause: mdm sync-graph not run or Neo4j unreachable.")
            print("  → Re-run: ./scripts/ops/trigger.sh mdm-gold")
    else:
        print("  ✓ Full IS_INSIDER path is working end-to-end")
    print()


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env",          default="dev")
    parser.add_argument("--region",       default=os.environ.get("AWS_REGION","us-east-1"))
    parser.add_argument("--silver-local", default="")
    parser.add_argument("--probe",        action="store_true",
                        help="Fetch + parse one real Form 4 from SEC to confirm parse path")
    parser.add_argument("--skip-mdm",     action="store_true")
    parser.add_argument("--skip-neo4j",   action="store_true")
    args = parser.parse_args()

    print(f"\n{'═'*62}")
    print(f"  NEO4J IS_INSIDER E2E CHECK  ·  {args.env}  ·  {args.region}")
    print(f"{'═'*62}")

    silver = check_silver(args.env, args.region, args.silver_local or None)
    mdm    = check_mdm(args.env, args.region)    if not args.skip_mdm   else {}
    neo4j  = check_neo4j(args.env, args.region)  if not args.skip_neo4j else {}

    if args.probe and silver.get("sample_accession"):
        try:
            identity_secret = aws_secret(f"edgartools-{args.env}-edgar-identity", args.region)
            identity = identity_secret if isinstance(identity_secret, str) else identity_secret.get("identity","")
        except Exception:
            identity = "edgartools-platform@example.com contact@example.com"
        probe_form4_parse(
            cik=silver["sample_cik"],
            accession_number=silver["sample_accession"],
            primary_document=silver["sample_primary"],
            edgar_identity=identity,
            region=args.region,
        )

    summary(silver, mdm, neo4j)


if __name__ == "__main__":
    main()
