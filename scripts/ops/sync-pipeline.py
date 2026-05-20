"""
Sync the full pipeline — Bronze→Silver→MDM→Neo4j→Gold — without making
any SEC API calls.  Uses only cached bronze artifacts already in S3.

Layers and what each does:
  bronze→silver   seed-silver-batches seeds CIK batches, then bootstrap-batch
                  re-parses ownership XMLs from S3 bronze with --artifact-policy skip.
                  No submissions.json or filing index re-downloaded from SEC.

  mdm             edgar-warehouse mdm run --entity-type all  (ECS direct)
                  Resolves companies, persons, securities, advisers into MDM Postgres.

  backfill        mdm backfill-relationships  (Step Functions SM)
                  Patches NULL issuer_entity_id, creates ISSUED_BY / MANAGES_FUND
                  instances, syncs to Neo4j.

  sync            mdm sync-graph  (Step Functions SM)
                  Pushes pending mdm_relationship_instance rows to Neo4j AuraDB.

  verify          mdm verify-graph  (Step Functions SM)
                  Prints Neo4j node/edge counts to CloudWatch; exits non-zero on mismatch.

  gold            gold-refresh  (Step Functions SM)
                  Rebuilds all gold Parquet tables from silver DuckDB, writes Snowflake
                  export manifests; SNOWFLAKE_RUN_MANIFEST_TASK picks up within ~1 min.

Usage:
  # Full sync (all layers)
  uv run python scripts/ops/sync-pipeline.py

  # Skip layers already up to date
  uv run python scripts/ops/sync-pipeline.py --skip-bronze --skip-mdm

  # Dry-run: print what would run, trigger nothing
  uv run python scripts/ops/sync-pipeline.py --dry-run

  # Adjust MDM entity limit (default 5400)
  uv run python scripts/ops/sync-pipeline.py --mdm-limit 1000

Options:
  --env ENV             Environment prefix (default: dev)
  --region REGION       AWS region (default: us-east-1)
  --mdm-limit N         Max entities per type for mdm run (default: 5400)
  --sync-limit N        Max relationship rows for mdm sync-graph (default: 500)
  --skip-bronze         Skip bronze→silver layer
  --skip-mdm            Skip MDM layer
  --skip-backfill       Skip backfill layer
  --skip-sync           Skip sync-graph layer
  --skip-verify         Skip verify-graph layer
  --skip-gold           Skip gold refresh layer
  --dry-run             Print plan; do not trigger anything
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

def hr(label: str) -> None:
    width = 64
    pad = (width - len(label) - 2) // 2
    print(f"\n{'─' * pad} {label} {'─' * max(0, width - pad - len(label) - 2)}")


def info(msg: str) -> None:
    print(f"  ·  {msg}")


def ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def warn(msg: str) -> None:
    print(f"  ⚠  {msg}", file=sys.stderr)


def run_aws(*args: str) -> str:
    r = subprocess.run(["aws", *args], capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f"aws {args[0]} failed (rc={r.returncode})")
    return r.stdout.strip()


def account_id(region: str) -> str:
    return run_aws("--region", region, "sts", "get-caller-identity",
                   "--query", "Account", "--output", "text")


def sm_arn(env: str, name: str, region: str, acct: str) -> str:
    return f"arn:aws:states:{region}:{acct}:stateMachine:edgartools-{env}-{name}"


# ── ECS direct task (for MDM run — SM hardcodes --entity-type all) ─────────

def ecs_task_config(env: str, region: str) -> dict:
    """Read cluster, task def, subnets, SGs from the gold-refresh SM definition
    (authoritative source; aws-dev-application.json may have empty network config)."""
    arn = f"arn:aws:states:{region}:077127448006:stateMachine:edgartools-{env}-gold-refresh"
    try:
        raw = run_aws("--region", region, "stepfunctions", "describe-state-machine",
                      "--state-machine-arn", arn, "--query", "definition", "--output", "text")
    except RuntimeError:
        return {}

    d = json.loads(raw)

    def find(obj: object, key: str, depth: int = 0) -> object | None:
        if depth > 10:
            return None
        if isinstance(obj, dict):
            if key in obj:
                return obj[key]
            for v in obj.values():
                r = find(v, key, depth + 1)
                if r is not None:
                    return r
        elif isinstance(obj, list):
            for i in obj:
                r = find(i, key, depth + 1)
                if r is not None:
                    return r
        return None

    net = find(d, "AwsvpcConfiguration") or {}
    cluster = find(d, "Cluster") or f"arn:aws:ecs:{region}:077127448006:cluster/edgartools-{env}-warehouse"

    # MDM medium task def — read from silver_mdm_gold SM which has it
    smg_arn = f"arn:aws:states:{region}:077127448006:stateMachine:edgartools-{env}-silver-mdm-gold"
    try:
        raw2 = run_aws("--region", region, "stepfunctions", "describe-state-machine",
                       "--state-machine-arn", smg_arn, "--query", "definition", "--output", "text")
        d2 = json.loads(raw2)
        mdm_td = find(d2, "TaskDefinition") or f"edgartools-{env}-mdm-medium"
        # Find the MDM-specific one (not warehouse)
        # Walk all TaskDefinition values and pick the mdm one
        def find_all(obj: object, key: str, depth: int = 0) -> list:
            if depth > 10: return []
            results = []
            if isinstance(obj, dict):
                if key in obj: results.append(obj[key])
                for v in obj.values(): results.extend(find_all(v, key, depth + 1))
            elif isinstance(obj, list):
                for i in obj: results.extend(find_all(i, key, depth + 1))
            return results
        tds = find_all(d2, "TaskDefinition")
        mdm_td = next((t for t in tds if "mdm-medium" in t), tds[0] if tds else f"edgartools-{env}-mdm-medium")
    except RuntimeError:
        mdm_td = f"edgartools-{env}-mdm-medium"

    return {
        "cluster": cluster,
        "mdm_task_def": mdm_td,
        "subnets": net.get("Subnets", []),
        "security_groups": net.get("SecurityGroups", []),
    }


def run_ecs_task(command: list[str], cfg: dict, region: str,
                 dry_run: bool = False) -> bool:
    """Run an ECS Fargate task directly and poll until STOPPED.  Returns True on exit 0."""
    info(f"Command: {' '.join(command)}")
    if dry_run:
        info("[dry-run] would call ecs run-task")
        return True

    raw = run_aws(
        "--region", region,
        "ecs", "run-task",
        "--cluster", cfg["cluster"],
        "--task-definition", cfg["mdm_task_def"],
        "--launch-type", "FARGATE",
        "--network-configuration", json.dumps({"awsvpcConfiguration": {
            "subnets": cfg["subnets"],
            "securityGroups": cfg["security_groups"],
            "assignPublicIp": "ENABLED",
        }}),
        "--overrides", json.dumps({"containerOverrides": [{
            "name": "edgar-warehouse",
            "command": command,
        }]}),
        "--output", "json",
    )
    result = json.loads(raw)
    tasks = result.get("tasks", [])
    if not tasks:
        warn(f"run-task returned no tasks: {result.get('failures', [])}")
        return False

    task_arn = tasks[0]["taskArn"]
    info(f"Task ARN: {task_arn.split('/')[-1]}")

    while True:
        status = run_aws("--region", region,
                         "ecs", "describe-tasks",
                         "--cluster", cfg["cluster"],
                         "--tasks", task_arn,
                         "--query", "tasks[0].lastStatus",
                         "--output", "text").strip()
        print(f"    [{time.strftime('%H:%M:%S')}] {status}", flush=True)
        if status == "STOPPED":
            break
        time.sleep(15)

    exit_code = run_aws("--region", region,
                        "ecs", "describe-tasks",
                        "--cluster", cfg["cluster"],
                        "--tasks", task_arn,
                        "--query", "tasks[0].containers[0].exitCode",
                        "--output", "text").strip()
    success = exit_code == "0"
    if success:
        ok(f"exit 0")
    else:
        warn(f"exit {exit_code}")
    return success


# ── Step Functions helpers ────────────────────────────────────────────────────

def run_sm(arn: str, name: str, payload: dict, region: str,
           dry_run: bool = False) -> bool:
    """Start a Step Functions execution and poll to completion."""
    info(f"SM: {arn.split(':')[-1]}  input={json.dumps(payload)}")
    if dry_run:
        info("[dry-run] would start-execution")
        return True

    exec_arn = run_aws("--region", region,
                       "stepfunctions", "start-execution",
                       "--state-machine-arn", arn,
                       "--name", name,
                       "--input", json.dumps(payload),
                       "--query", "executionArn",
                       "--output", "text").strip()
    info(f"Execution: {exec_arn.split(':')[-1]}")

    while True:
        status = run_aws("--region", region,
                         "stepfunctions", "describe-execution",
                         "--execution-arn", exec_arn,
                         "--query", "status",
                         "--output", "text").strip()
        print(f"    [{time.strftime('%H:%M:%S')}] {status}", flush=True)
        if status not in ("RUNNING",):
            break
        time.sleep(15)

    success = status == "SUCCEEDED"
    if success:
        ok(f"SUCCEEDED")
    else:
        warn(f"{status}")
    return success


# ── Layer implementations ──────────────────────────────────────────────────

def layer_bronze_silver(env: str, region: str, acct: str,
                         dry_run: bool) -> bool:
    """Re-parse ownership XMLs from cached S3 bronze → silver DuckDB.
    Uses seed-silver-batches + bootstrap-batch --artifact-policy skip.
    No SEC API calls; reads only from s3://edgartools-dev-bronze-*."""
    hr("LAYER 1 — Bronze → Silver  (no SEC calls)")
    info("Strategy: silver_mdm_gold SM — re-processes bronze with --artifact-policy skip")
    info("  SeedSilverBatches: writes CIK batch file to bronze reference/")
    info("  BatchSilver (distributed map, MaxConcurrency=3): bootstrap-batch --artifact-policy skip")
    info("  (MDM + gold steps inside that SM are also triggered — use --skip-bronze")
    info("   and run remaining layers standalone if you need finer control)")

    # silver_mdm_gold runs the full chain; we run it and skip remaining layers
    # by letting it complete, then return True so caller skips duplicating MDM/gold.
    arn = sm_arn(env, "silver-mdm-gold", region, acct)
    name = f"sync-bronze-silver-{int(time.time())}"
    return run_sm(arn, name, {"tracking_status_filter": "active"}, region, dry_run)


def layer_mdm(env: str, region: str, cfg: dict, limit: int,
              dry_run: bool) -> bool:
    """Run mdm run --entity-type all via ECS direct (SM hardcodes all, bypassed here)."""
    hr("LAYER 2 — MDM  (entity resolution)")
    info(f"entity-type: all  limit: {limit}")
    command = ["mdm", "run", "--entity-type", "all", "--limit", str(limit)]
    return run_ecs_task(command, cfg, region, dry_run)


def layer_backfill(env: str, region: str, acct: str,
                   dry_run: bool) -> bool:
    """mdm backfill-relationships — patches issuer_entity_id nulls, creates ISSUED_BY instances."""
    hr("LAYER 3 — MDM Backfill  (ISSUED_BY / MANAGES_FUND)")
    arn = sm_arn(env, "mdm-backfill-relationships", region, acct)
    name = f"sync-backfill-{int(time.time())}"
    return run_sm(arn, name, {"limit": 500}, region, dry_run)


def layer_sync(env: str, region: str, acct: str,
               limit: int, dry_run: bool) -> bool:
    """mdm sync-graph — pushes pending relationship instances to Neo4j AuraDB."""
    hr("LAYER 4 — Neo4j Sync  (sync-graph)")
    arn = sm_arn(env, "mdm-sync-graph", region, acct)
    name = f"sync-neo4j-{int(time.time())}"
    return run_sm(arn, name, {"limit": limit}, region, dry_run)


def layer_verify(env: str, region: str, acct: str,
                 dry_run: bool) -> bool:
    """mdm verify-graph — prints Neo4j counts to CloudWatch, validates coverage."""
    hr("LAYER 5 — Neo4j Verify  (verify-graph)")
    arn = sm_arn(env, "mdm-verify-graph", region, acct)
    name = f"sync-verify-{int(time.time())}"
    return run_sm(arn, name, {}, region, dry_run)


def layer_gold(env: str, region: str, acct: str,
               dry_run: bool) -> bool:
    """gold-refresh — rebuilds all gold Parquet tables, writes Snowflake export manifests."""
    hr("LAYER 6 — Gold Refresh  (gold-refresh)")
    info("Rebuilds dim_* + fact_* from silver DuckDB → S3 Parquet → Snowflake export")
    arn = sm_arn(env, "gold-refresh", region, acct)
    name = f"sync-gold-{int(time.time())}"
    return run_sm(arn, name, {}, region, dry_run)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync bronze→silver→MDM→Neo4j→gold without SEC API calls."
    )
    parser.add_argument("--env",           default="dev")
    parser.add_argument("--region",        default=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    parser.add_argument("--mdm-limit",     type=int, default=5400,
                        help="Max entities per type for mdm run (default: 5400)")
    parser.add_argument("--sync-limit",    type=int, default=500,
                        help="Max relationship rows for sync-graph (default: 500)")
    parser.add_argument("--skip-bronze",   action="store_true",
                        help="Skip bronze→silver re-parse (silver already current)")
    parser.add_argument("--skip-mdm",      action="store_true")
    parser.add_argument("--skip-backfill", action="store_true")
    parser.add_argument("--skip-sync",     action="store_true")
    parser.add_argument("--skip-verify",   action="store_true")
    parser.add_argument("--skip-gold",     action="store_true")
    parser.add_argument("--dry-run",       action="store_true",
                        help="Print plan without triggering anything")
    args = parser.parse_args()

    print(f"\n{'═' * 64}")
    print(f"  PIPELINE SYNC  ·  {args.env}  ·  {args.region}")
    if args.dry_run:
        print(f"  MODE: dry-run — nothing will be triggered")
    print(f"{'═' * 64}")

    try:
        acct = account_id(args.region)
        info(f"Account: {acct}")
    except RuntimeError as e:
        warn(f"Could not resolve AWS account: {e}")
        sys.exit(1)

    cfg = ecs_task_config(args.env, args.region)
    if not cfg.get("subnets"):
        warn("Could not read ECS network config — MDM layer will be skipped")
        args.skip_mdm = True

    results: dict[str, bool] = {}

    # Layer 1: Bronze → Silver
    # NOTE: silver_mdm_gold SM also runs MDM+gold internally.
    # If running the full pipeline, use --skip-bronze and run layers 2-6
    # individually for finer control and visibility per layer.
    if not args.skip_bronze:
        ok_b = layer_bronze_silver(args.env, args.region, acct, args.dry_run)
        results["bronze→silver"] = ok_b
        if not ok_b and not args.dry_run:
            warn("Bronze→silver failed — aborting remaining layers")
            sys.exit(1)
        # silver_mdm_gold runs MDM+gold too; if it succeeded skip those layers
        if ok_b and not args.dry_run:
            info("silver_mdm_gold completed MDM + gold internally.")
            info("Skipping layers 2-6 to avoid double-processing.")
            print(f"\n{'═' * 64}\n")
            return

    # Layer 2: MDM
    if not args.skip_mdm:
        ok_m = layer_mdm(args.env, args.region, cfg, args.mdm_limit, args.dry_run)
        results["mdm"] = ok_m
        if not ok_m and not args.dry_run:
            warn("MDM layer failed — aborting remaining layers")
            sys.exit(1)

    # Layer 3: Backfill
    if not args.skip_backfill:
        ok_bf = layer_backfill(args.env, args.region, acct, args.dry_run)
        results["backfill"] = ok_bf
        if not ok_bf and not args.dry_run:
            warn("Backfill failed — continuing to sync/verify/gold anyway")

    # Layer 4: Neo4j sync
    if not args.skip_sync:
        ok_s = layer_sync(args.env, args.region, acct, args.sync_limit, args.dry_run)
        results["sync"] = ok_s

    # Layer 5: Neo4j verify
    if not args.skip_verify:
        ok_v = layer_verify(args.env, args.region, acct, args.dry_run)
        results["verify"] = ok_v

    # Layer 6: Gold
    if not args.skip_gold:
        ok_g = layer_gold(args.env, args.region, acct, args.dry_run)
        results["gold"] = ok_g

    # Summary
    hr("Summary")
    all_ok = True
    for layer, success in results.items():
        icon = "✓" if success else "✗"
        print(f"  {icon}  {layer}")
        if not success:
            all_ok = False

    skipped = []
    for flag, name in [
        (args.skip_bronze,   "bronze→silver"),
        (args.skip_mdm,      "mdm"),
        (args.skip_backfill, "backfill"),
        (args.skip_sync,     "sync"),
        (args.skip_verify,   "verify"),
        (args.skip_gold,     "gold"),
    ]:
        if flag:
            skipped.append(name)
    if skipped:
        print(f"  ·  skipped: {', '.join(skipped)}")

    print(f"\n{'═' * 64}\n")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
