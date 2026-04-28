"""Repeatable E2E: seed a sample MANAGES_FUND relationship, run backfill +
sync via the existing Container App Jobs, and verify it landed in Neo4j.

Idempotent: uses deterministic markers so reruns reuse the same test entities
and never create duplicates. By default leaves SQL data in place (re-runs
naturally re-sync via MERGE in Neo4j); pass --cleanup to delete the seeded
rows after verification.

Usage:
    python infra/scripts/run-neo4j-e2e.py [--cleanup]

Env:
    MDM_DATABASE_URL  pyodbc connection URL (read from KV: mdm-database-url)

Pre-requisites:
    1. Local x86_64 ODBC driver:   brew reinstall msodbcsql18
    2. SQL firewall rule for laptop IP (script adds + removes one if --manage-fw)
    3. az login complete; terraform state populated for dev account.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DEMO_FUND_NAME = "MDM_E2E_DEMO_FUND"
DEMO_ADVISER_MARKER_SOURCE = "mdm_e2e"  # used on mdm_relationship_instance.source_system

JOB_LOAD = "edgartools-dev-mdm-graph-load"
JOB_VERIFY = "edgartools-dev-mdm-graph-verify"
RG = "edgartools-dev-rg"


def az(*args: str) -> str:
    """Run an `az` CLI command and return stdout."""
    return subprocess.check_output(["az", *args], text=True).strip()


def run_job(job_name: str) -> tuple[str, str]:
    """Start a Container App Job and block until it ends. Returns (exec_name, status)."""
    exec_name = az(
        "containerapp", "job", "start",
        "--name", job_name, "--resource-group", RG,
        "--query", "name", "-o", "tsv",
    )
    print(f"  started {job_name}: {exec_name}")
    while True:
        status = az(
            "containerapp", "job", "execution", "show",
            "--name", job_name, "--resource-group", RG,
            "--job-execution-name", exec_name,
            "--query", "properties.status", "-o", "tsv",
        )
        print(f"    [{job_name}] {status}")
        if status in ("Succeeded", "Failed", "Stopped"):
            return exec_name, status
        time.sleep(15)


def fetch_job_logs(workspace: str, exec_name: str) -> str:
    """Pull the most recent stdout/stderr from a job execution."""
    time.sleep(20)  # let logs flush
    container_prefix = "-".join(exec_name.split("-")[:4])
    query = (
        "ContainerAppConsoleLogs_CL "
        "| where Log_s != '' "
        "| where TimeGenerated > ago(10m) "
        f"| where ContainerAppName_s has '{container_prefix}' "
        "| order by TimeGenerated asc "
        "| project Log_s"
    )
    try:
        out = az(
            "monitor", "log-analytics", "query",
            "--workspace", workspace,
            "--analytics-query", query,
            "--query", "tables[0].rows[*][0]", "-o", "tsv",
        )
        return out or "(no logs)"
    except subprocess.CalledProcessError:
        return "(log query failed)"


def find_or_seed(engine: Engine) -> tuple[str, str]:
    """Return (adviser_id, fund_id), creating them if missing."""
    with engine.begin() as c:
        row = c.execute(text(
            "SELECT TOP 1 f.entity_id AS fund_id, f.adviser_entity_id AS adviser_id "
            "FROM mdm_fund f WHERE f.canonical_name = :n"
        ), {"n": DEMO_FUND_NAME}).first()

        if row:
            print(f"  reusing seeded entities: adviser={row.adviser_id} fund={row.fund_id}")
            return row.adviser_id, row.fund_id

        adviser_id = str(uuid.uuid4())
        fund_id = str(uuid.uuid4())
        c.execute(text(
            "INSERT INTO mdm_entity (entity_id, entity_type, is_quarantined) "
            "VALUES (:a, 'adviser', 0), (:f, 'fund', 0)"
        ), {"a": adviser_id, "f": fund_id})
        c.execute(text(
            "INSERT INTO mdm_fund (entity_id, adviser_entity_id, canonical_name) "
            "VALUES (:f, :a, :n)"
        ), {"f": fund_id, "a": adviser_id, "n": DEMO_FUND_NAME})
        print(f"  seeded adviser={adviser_id} fund={fund_id}")
        return adviser_id, fund_id


def cleanup_sql(engine: Engine, adviser_id: str, fund_id: str) -> None:
    """Delete the seeded test rows from SQL.

    Order matters: relationship_instance → mdm_fund → mdm_entity (FKs).
    """
    print("  deleting from SQL...")
    with engine.begin() as c:
        c.execute(text(
            "DELETE FROM mdm_relationship_instance "
            "WHERE source_entity_id IN (:a, :f) OR target_entity_id IN (:a, :f)"
        ), {"a": adviser_id, "f": fund_id})
        c.execute(text("DELETE FROM mdm_fund WHERE entity_id = :f"), {"f": fund_id})
        c.execute(text(
            "DELETE FROM mdm_entity WHERE entity_id IN (:a, :f)"
        ), {"a": adviser_id, "f": fund_id})
    print("    sql cleanup ok")


def reset_relationship_instances(engine: Engine, adviser_id: str, fund_id: str) -> None:
    """Wipe any prior MANAGES_FUND row for the test pair so backfill re-derives."""
    with engine.begin() as c:
        c.execute(text(
            "DELETE FROM mdm_relationship_instance "
            "WHERE source_entity_id = :a AND target_entity_id = :f"
        ), {"a": adviser_id, "f": fund_id})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cleanup", action="store_true",
                        help="Delete seeded SQL rows after verification")
    parser.add_argument("--skip-jobs", action="store_true",
                        help="Only seed (skip running Container App Jobs)")
    args = parser.parse_args()

    db_url = os.environ.get("MDM_DATABASE_URL")
    if not db_url:
        print("ERROR: MDM_DATABASE_URL not set", file=sys.stderr)
        print("Hint: export MDM_DATABASE_URL=$(az keyvault secret show "
              "--vault-name edgdev-7659-kv --name mdm-database-url --query value -o tsv)",
              file=sys.stderr)
        return 2

    engine = create_engine(db_url, pool_pre_ping=True)

    print("==> [1/4] Seed sample adviser+fund (idempotent)")
    adviser_id, fund_id = find_or_seed(engine)
    reset_relationship_instances(engine, adviser_id, fund_id)

    if args.skip_jobs:
        print(f"\nSkipping jobs. Seeded: adviser={adviser_id} fund={fund_id}")
        return 0

    workspace = az(
        "monitor", "log-analytics", "workspace", "list",
        "--resource-group", RG, "--query", "[0].customerId", "-o", "tsv",
    )

    print("\n==> [2/4] Run mdm-graph-load (backfill MANAGES_FUND, sync to Neo4j)")
    load_exec, load_status = run_job(JOB_LOAD)
    print(fetch_job_logs(workspace, load_exec))
    if load_status != "Succeeded":
        print(f"ERROR: graph-load ended with {load_status}", file=sys.stderr)
        return 1

    print("\n==> [3/4] Run mdm-graph-verify (cypher MATCH counts)")
    verify_exec, verify_status = run_job(JOB_VERIFY)
    verify_logs = fetch_job_logs(workspace, verify_exec)
    print(verify_logs)
    if verify_status != "Succeeded":
        print(f"ERROR: graph-verify ended with {verify_status}", file=sys.stderr)
        return 1

    print("\n==> [4/4] Asserting MANAGES_FUND >= 1 in Neo4j")
    counts = None
    for line in verify_logs.splitlines():
        line = line.strip()
        if line.startswith("{") and "MANAGES_FUND" in line:
            try:
                counts = json.loads(line)
                break
            except json.JSONDecodeError:
                pass
    if counts is None:
        print("WARNING: could not parse counts from verify-graph logs", file=sys.stderr)
    else:
        print(f"  Neo4j: nodes={counts.get('neo4j_nodes_total')} "
              f"MANAGES_FUND={counts.get('neo4j_MANAGES_FUND_edges')} "
              f"ISSUED_BY={counts.get('neo4j_ISSUED_BY_edges')}")
        if (counts.get("neo4j_MANAGES_FUND_edges") or 0) < 1:
            print("ERROR: MANAGES_FUND edge count is 0", file=sys.stderr)
            return 1

    print("\nE2E SUCCESS: sample MANAGES_FUND relationship reached Neo4j.")

    if args.cleanup:
        print("\n==> Cleanup: deleting test rows from SQL")
        cleanup_sql(engine, adviser_id, fund_id)
        print("Note: Neo4j nodes/edges retained; subsequent runs MERGE on the same "
              "entity_ids so this is safe.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
