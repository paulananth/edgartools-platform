"""
Diagnose why `mdm run` fails the silver preflight and recommend the correct
entity type to pass based on which tables actually have data.

5-why findings this script was written to surface:
  Why 1: mdm run --entity-type all --limit 5400 exits with code 1
  Why 2: _validate_silver_tables reports problems
  Why 3a (old image): row[0] on a dict raises KeyError(0); str(KeyError(0)) == "0"
  Why 3b (new image): sec_adv_filing and sec_adv_private_fund have 0 rows
  Why 4: no ADV data has been parsed — Form ADV pipeline has not run yet
  Why 5: _ENTITY_TYPE_REQUIRED_TABLES["all"] enforces non-zero rows for ALL
          entity types including adviser/fund, but only company/ownership data
          is present in silver.
  Fix:   run with --entity-type company (or whichever types are populated)

Usage:
  uv run python scripts/ops/diagnose-mdm-run.py
  uv run python scripts/ops/diagnose-mdm-run.py --silver-local /tmp/silver.duckdb
  uv run python scripts/ops/diagnose-mdm-run.py --fix --entity-type company --limit 5400
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


# ── shared helpers ────────────────────────────────────────────────────────────

def hr(label: str = "") -> None:
    width = 62
    if label:
        pad = (width - len(label) - 2) // 2
        print(f"\n{'─' * pad} {label} {'─' * max(0, width - pad - len(label) - 2)}")
    else:
        print("─" * width)


def ok(label: str, value: object, *, alert: bool = False) -> None:
    icon = "⚠ " if alert else ("✓ " if (isinstance(value, int) and value > 0) else ("· " if value == 0 else "? "))
    print(f"  {icon} {label:<44s} {value!s:>8}")


def warn(msg: str) -> None:
    print(f"  ⚠  {msg}", file=sys.stderr)


def aws(region: str, *args: str) -> str:
    r = subprocess.run(["aws", "--region", region, *args],
                       capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f"aws {args[0]} failed")
    return r.stdout.strip()


def resolve_silver(env: str, region: str, silver_local: str) -> str | None:
    if silver_local:
        return silver_local if Path(silver_local).exists() else None
    account = aws(region, "sts", "get-caller-identity", "--query", "Account", "--output", "text")
    bucket  = f"edgartools-{env}-warehouse-{account}"
    s3_uri  = f"s3://{bucket}/warehouse/silver/sec/silver.duckdb"
    local   = f"/tmp/silver-{env}.duckdb"
    print(f"  Downloading {s3_uri} ...")
    r = subprocess.run(["aws", "s3", "cp", "--region", region, s3_uri, local],
                       capture_output=True, text=True)
    if r.returncode != 0:
        warn(f"Download failed: {r.stderr.strip()[:120]}")
        return None
    print(f"  Saved to {local} ({Path(local).stat().st_size / 1e6:.0f} MB)")
    return local


# ── required table definitions (mirrors cli.py) ──────────────────────────────

REQUIRED = {
    "company":  {"sec_company"},
    "adviser":  {"sec_adv_filing"},
    "fund":     {"sec_adv_private_fund"},
    "person":   {"sec_company_filing", "sec_ownership_reporting_owner"},
    "security": {"sec_company_filing", "sec_ownership_non_derivative_txn"},
}


# ── diagnosis ────────────────────────────────────────────────────────────────

def diagnose(local_path: str) -> dict[str, int]:
    import duckdb
    con = duckdb.connect(local_path, read_only=True)

    # 1. Confirm preflight query works (catches KeyError(0) regression)
    hr("Preflight query sanity")
    try:
        rows = con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
        cols = [d[0] for d in con.description]
        tables_in_silver = {dict(zip(cols, r))["table_name"] for r in rows}
        print(f"  ✓  information_schema query: {len(tables_in_silver)} tables returned")
    except Exception as exc:
        warn(f"information_schema query failed: {type(exc).__name__}({exc!r})")
        warn("  This is the KeyError(0) bug — row[0] on a dict in _validate_silver_tables.")
        warn("  Fix: upgrade to the image containing commit ca82436.")
        con.close()
        return {}

    # 2. Row counts per required table
    hr("Required table row counts")
    counts: dict[str, int] = {}
    all_required = set().union(*REQUIRED.values())
    for table in sorted(all_required):
        if table in tables_in_silver:
            n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        else:
            n = -1  # missing entirely
        counts[table] = n
        ok(table, "MISSING" if n < 0 else n, alert=(n <= 0))

    con.close()
    return counts


def recommend(counts: dict[str, int]) -> list[str]:
    """Return entity types whose required tables are all non-empty."""
    viable = []
    for entity_type, tables in REQUIRED.items():
        if all(counts.get(t, -1) > 0 for t in tables):
            viable.append(entity_type)
    return viable


def report(counts: dict[str, int]) -> None:
    viable = recommend(counts)

    hr("Entity-type readiness")
    for entity_type, tables in REQUIRED.items():
        blocking = [t for t in tables if counts.get(t, -1) <= 0]
        if blocking:
            status = f"BLOCKED — {', '.join(blocking)} {'missing' if counts.get(blocking[0],-1)<0 else 'empty'}"
        else:
            status = "READY"
        icon = "✓" if not blocking else "✗"
        print(f"  {icon}  {entity_type:<12}  {status}")

    hr("5-why root cause")
    empty_adv = [t for t in ("sec_adv_filing", "sec_adv_private_fund") if counts.get(t, -1) == 0]
    if empty_adv:
        print(f"""
  Why 1: mdm run --entity-type all exits with code 1
  Why 2: _validate_silver_tables reports "{', '.join(empty_adv)} has 0 rows"
  Why 3: ADV tables are empty — Form ADV (investment adviser) pipeline has not run
  Why 4: ADV parsing requires bootstrap with --form-type ADV, which has not been
          triggered for any company in the tracking universe
  Why 5: _ENTITY_TYPE_REQUIRED_TABLES["all"] enforces non-zero rows for ALL
          entity types including adviser/fund — but only company + ownership data
          exists in silver, so "all" is an invalid target until ADV data arrives

  Fix A (immediate): run with --entity-type company to load all 5400 companies
                     into MDM without requiring ADV data:

    aws stepfunctions start-execution \\
      --region us-east-1 \\
      --state-machine-arn arn:aws:states:us-east-1:077127448006:stateMachine:edgartools-dev-mdm-run \\
      --name "company-only-$(date +%s)" \\
      --input '{{"entity_type": "company", "limit": 5400}}'

  Fix B (permanent): change _ENTITY_TYPE_REQUIRED_TABLES["all"] to only enforce
                     tables that are relevant to the entity types being processed,
                     or split "all" into separate per-type calls in the pipeline.
""")
    elif viable:
        print(f"\n  All viable entity types: {viable}")
        print(f"  Recommended: --entity-type {' '.join(viable)}")

    hr("Recommended command")
    if viable:
        et = "company" if "company" in viable else viable[0]
        print(f"""
  uv run python scripts/ops/diagnose-mdm-run.py --fix --entity-type {et} --limit 5400
""")
    else:
        print("\n  No entity types are ready. Ensure silver has been populated.")


# ── trigger fix ──────────────────────────────────────────────────────────────

def _app_json(env: str) -> dict:
    import json as _json
    p = Path(f"infra/aws-{env}-application.json")
    if p.exists():
        return _json.loads(p.read_text())
    return {}


def trigger_run(env: str, region: str, entity_type: str, limit: int) -> None:
    """Trigger via ECS RunTask directly so --entity-type is passed correctly.

    The mdm-run Step Functions SM hardcodes '--entity-type all' and ignores
    $.entity_type from the input payload.  Direct ECS avoids that constraint.
    """
    cfg = _app_json(env)
    cluster  = cfg.get("cluster", {}).get("arn") or f"arn:aws:ecs:{region}:077127448006:cluster/edgartools-{env}-warehouse"
    task_def = cfg.get("task_definitions", {}).get("mdm_medium") or f"edgartools-{env}-mdm-medium"
    nets     = cfg.get("network", {})
    subnets  = nets.get("subnets", [])
    sgs      = nets.get("security_groups", [])

    if not subnets:
        # Fall back to reading from the SM definition
        raw = aws(region,
            "stepfunctions", "describe-state-machine",
            "--state-machine-arn",
            f"arn:aws:states:{region}:077127448006:stateMachine:edgartools-{env}-mdm-run",
            "--query", "definition", "--output", "text",
        )
        sm_def = json.loads(raw)
        for state in sm_def.get("States", {}).values():
            net = (state.get("Parameters", {})
                   .get("NetworkConfiguration", {})
                   .get("AwsvpcConfiguration", {}))
            if net.get("Subnets"):
                subnets = net["Subnets"]
                sgs     = net.get("SecurityGroups", [])
                break

    command = ["mdm", "run", "--entity-type", entity_type, "--limit", str(limit)]

    hr(f"Triggering ECS task: mdm run --entity-type {entity_type} --limit {limit}")
    print(f"  Cluster:    {cluster.split('/')[-1]}")
    print(f"  Task def:   {task_def.split('/')[-1]}")
    print(f"  Subnets:    {subnets}")

    result_raw = aws(region,
        "ecs", "run-task",
        "--cluster", cluster,
        "--task-definition", task_def,
        "--launch-type", "FARGATE",
        "--network-configuration",
        json.dumps({"awsvpcConfiguration": {
            "subnets": subnets,
            "securityGroups": sgs,
            "assignPublicIp": "ENABLED",
        }}),
        "--overrides",
        json.dumps({"containerOverrides": [{
            "name": "edgar-warehouse",
            "command": command,
        }]}),
        "--output", "json",
    )
    result = json.loads(result_raw)
    tasks = result.get("tasks", [])
    if not tasks:
        failures = result.get("failures", [])
        print(f"  ✗  RunTask failed: {failures}")
        return

    task_arn = tasks[0]["taskArn"]
    print(f"  Task ARN:   {task_arn}")
    print()

    hr("Polling ECS task")
    while True:
        raw = aws(region,
            "ecs", "describe-tasks",
            "--cluster", cluster,
            "--tasks", task_arn,
            "--query", "tasks[0].lastStatus",
            "--output", "text",
        )
        status = raw.strip()
        print(f"  [{time.strftime('%H:%M:%S')}] {status}", flush=True)
        if status in ("STOPPED",):
            break
        time.sleep(15)

    # Get exit code
    raw = aws(region,
        "ecs", "describe-tasks",
        "--cluster", cluster,
        "--tasks", task_arn,
        "--query", "tasks[0].containers[0].exitCode",
        "--output", "text",
    )
    exit_code = raw.strip()
    if exit_code == "0":
        print(f"\n  ✓  Task SUCCEEDED (exit 0)")
        print(f"\n  Run backfill to link securities:")
        print(f"    uv run python scripts/ops/backfill-issued-by.py --limit 500")
    else:
        print(f"\n  ✗  Task failed (exit {exit_code}) — check ECS logs")


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnose silver preflight failures for mdm run."
    )
    parser.add_argument("--env",          default="dev")
    parser.add_argument("--region",       default=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    parser.add_argument("--silver-local", default="",
                        help="Use existing local silver.duckdb instead of downloading")
    parser.add_argument("--fix",          action="store_true",
                        help="Trigger the recommended mdm-run execution after diagnosis")
    parser.add_argument("--entity-type",  default="company",
                        help="Entity type to run when --fix is passed (default: company)")
    parser.add_argument("--limit",        type=int, default=5400)
    args = parser.parse_args()

    print(f"\n{'═' * 62}")
    print(f"  MDM RUN PREFLIGHT DIAGNOSIS  ·  {args.env}  ·  {args.region}")
    print(f"{'═' * 62}")

    try:
        import duckdb  # noqa: F401
    except ImportError:
        warn("duckdb not installed — run: uv pip install duckdb")
        sys.exit(1)

    hr("Silver source")
    local = resolve_silver(args.env, args.region, args.silver_local)
    if not local:
        warn("Could not resolve silver DuckDB.")
        sys.exit(1)
    print(f"  Using: {local}")

    counts = diagnose(local)
    if not counts:
        sys.exit(1)

    report(counts)

    if args.fix:
        viable = recommend(counts)
        if args.entity_type not in viable:
            warn(f"--entity-type {args.entity_type} is not ready (required tables empty).")
            warn(f"  Ready types: {viable}")
            sys.exit(1)
        trigger_run(args.env, args.region, args.entity_type, args.limit)

    print(f"\n{'═' * 62}\n")


if __name__ == "__main__":
    main()
