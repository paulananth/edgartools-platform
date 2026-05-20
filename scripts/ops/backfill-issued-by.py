"""
Backfill mdm_security.issuer_entity_id and create ISSUED_BY edges for all
Company→Security relationships that were missed because run_companies hit its
per-run limit before the security's issuer was processed.

Runs entirely on ECS via the existing edgartools-dev-mdm-backfill-relationships
Step Function — no local DuckDB download required.

What it does:
  1. Triggers edgartools-dev-mdm-backfill-relationships (runs
     'mdm backfill-relationships --limit <n>' on ECS Fargate).
     The command now includes a Phase 1 that patches NULL issuer_entity_id
     rows in mdm_security by re-running the silver→company lookup, followed by
     Phase 2 that creates ISSUED_BY instances and syncs them to Neo4j.
  2. Polls until the execution finishes.
  3. Tails the ECS log stream to surface the result JSON.
  4. Runs check-issued-by-coverage.py --skip-silver for a before/after summary.

Usage:
  uv run python scripts/ops/backfill-issued-by.py
  uv run python scripts/ops/backfill-issued-by.py --limit 1000 --env dev

Options:
  --limit N     Max relationship instances to create/sync (default: 500)
  --env ENV     Environment prefix (default: dev)
  --region R    AWS region (default: us-east-1)
  --dry-run     Print the execution input and exit without triggering
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

SCRIPT_DIR = Path(__file__).parent


def hr(label: str = "") -> None:
    width = 62
    if label:
        pad = (width - len(label) - 2) // 2
        print(f"\n{'─' * pad} {label} {'─' * max(0, width - pad - len(label) - 2)}")
    else:
        print("─" * width)


def info(msg: str) -> None:
    print(f"  ·  {msg}")


def ok(label: str, value: object) -> None:
    icon = "✓" if isinstance(value, int) and value > 0 else ("·" if value == 0 else "?")
    print(f"  {icon}  {label:<46s} {value!s:>6}")


def warn(msg: str) -> None:
    print(f"  ⚠  {msg}", file=sys.stderr)


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def aws(*args: str, region: str) -> str:
    result = run(["aws", "--region", region, *args], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"aws {args[0]} failed")
    return result.stdout.strip()


# ── Step Functions helpers ────────────────────────────────────────────────────

def sm_arn(env: str, name: str, region: str) -> str:
    account = aws("sts", "get-caller-identity", "--query", "Account", "--output", "text",
                  region=region)
    return f"arn:aws:states:{region}:{account}:stateMachine:edgartools-{env}-{name}"


def start_execution(arn: str, name: str, payload: dict, region: str) -> str:
    raw = aws(
        "stepfunctions", "start-execution",
        "--state-machine-arn", arn,
        "--name", name,
        "--input", json.dumps(payload),
        "--query", "executionArn",
        "--output", "text",
        region=region,
    )
    return raw.strip()


def poll_execution(exec_arn: str, region: str, poll_secs: int = 10) -> str:
    """Block until execution reaches a terminal state; return final status."""
    while True:
        status = aws(
            "stepfunctions", "describe-execution",
            "--execution-arn", exec_arn,
            "--query", "status",
            "--output", "text",
            region=region,
        ).strip()
        print(f"  [{time.strftime('%H:%M:%S')}] {status}", flush=True)
        if status not in ("RUNNING",):
            return status
        time.sleep(poll_secs)


# ── ECS log helpers ───────────────────────────────────────────────────────────

def latest_log_stream(log_group: str, prefix: str, region: str) -> str | None:
    # AWS does not allow combining --log-stream-name-prefix with --order-by LastEventTime.
    # Fetch the 10 most-recently-active streams and filter by prefix in Python.
    raw = aws(
        "logs", "describe-log-streams",
        "--log-group-name", log_group,
        "--order-by", "LastEventTime",
        "--descending",
        "--max-items", "10",
        "--query", "logStreams[*].logStreamName",
        "--output", "json",
        region=region,
    )
    try:
        streams = json.loads(raw)
    except json.JSONDecodeError:
        return None
    for s in streams:
        if s.startswith(prefix):
            return s
    return None


def tail_log_stream(log_group: str, stream: str, region: str,
                    start_ms: int | None = None) -> list[str]:
    cmd = [
        "aws", "--region", region,
        "logs", "get-log-events",
        "--log-group-name", log_group,
        "--log-stream-name", stream,
        "--start-from-head",
        "--query", "events[*].message",
        "--output", "json",
    ]
    if start_ms:
        cmd += ["--start-time", str(start_ms)]
    result = run(cmd, check=False)
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def parse_backfill_result(messages: list[str]) -> dict | None:
    """Extract the final JSON result blob from backfill-relationships log lines.

    The CLI prints the result as a pretty-printed multi-line block, so we
    reassemble all messages into one string and scan for the result object.
    """
    full = "\n".join(msg.strip() for msg in messages if msg.strip())

    # Walk backwards through potential JSON objects in the concatenated text
    depth = 0
    end = -1
    for i in range(len(full) - 1, -1, -1):
        c = full[i]
        if c == "}":
            if depth == 0:
                end = i
            depth += 1
        elif c == "{":
            depth -= 1
            if depth == 0 and end != -1:
                candidate = full[i : end + 1]
                try:
                    d = json.loads(candidate)
                    if "backfilled" in d or "issuers_repaired" in d:
                        return d
                except (json.JSONDecodeError, ValueError):
                    depth = 0
                    end = -1
    return None


# ── coverage check ────────────────────────────────────────────────────────────

def run_coverage_check(env: str, region: str) -> None:
    check_script = SCRIPT_DIR / "check-issued-by-coverage.py"
    if not check_script.exists():
        warn(f"Coverage script not found: {check_script}")
        return
    subprocess.run(
        [sys.executable, str(check_script),
         "--env", env, "--region", region,
         "--skip-silver"],
        check=False,
    )


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill Company→Security ISSUED_BY edges via Step Functions."
    )
    parser.add_argument("--limit",   type=int, default=500,
                        help="Max relationship instances to create/sync (default: 500)")
    parser.add_argument("--env",     default="dev")
    parser.add_argument("--region",  default=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    parser.add_argument("--dry-run", action="store_true",
                        help="Print execution input and exit without triggering")
    args = parser.parse_args()

    print(f"\n{'═' * 62}")
    print(f"  ISSUED_BY BACKFILL  ·  {args.env}  ·  {args.region}")
    print(f"{'═' * 62}")

    arn = sm_arn(args.env, "mdm-backfill-relationships", args.region)
    exec_name = f"issued-by-backfill-{int(time.time())}"
    payload = {"limit": args.limit}

    hr("Configuration")
    info(f"State machine : {arn.split(':')[-1]}")
    info(f"Execution name: {exec_name}")
    info(f"Limit         : {args.limit}")

    if args.dry_run:
        print(f"\n  [dry-run] would start: {json.dumps(payload)}")
        return

    # ── Pre-flight coverage check ─────────────────────────────────────────────
    hr("Pre-backfill coverage")
    run_coverage_check(args.env, args.region)

    # ── Trigger ───────────────────────────────────────────────────────────────
    hr("Triggering Step Function")
    start_ms = int(time.time() * 1000)
    try:
        exec_arn = start_execution(arn, exec_name, payload, args.region)
    except RuntimeError as e:
        warn(f"Failed to start execution: {e}")
        sys.exit(1)

    info(f"Execution ARN : {exec_arn}")

    # ── Poll ──────────────────────────────────────────────────────────────────
    hr("Polling")
    final_status = poll_execution(exec_arn, args.region)

    if final_status != "SUCCEEDED":
        warn(f"Execution ended with status: {final_status}")
        # Still try to get logs for diagnosis
    else:
        print(f"\n  ✓  Execution SUCCEEDED")

    # ── Pull ECS logs ─────────────────────────────────────────────────────────
    hr("ECS log output")
    log_group = f"/aws/ecs/edgartools-{args.env}-warehouse"

    stream = latest_log_stream(log_group, "mdm-mdm-", args.region)
    if not stream:
        warn("No MDM log stream found")
    else:
        info(f"Stream: {stream}")
        messages = tail_log_stream(log_group, stream, args.region, start_ms=start_ms)
        result = parse_backfill_result(messages)
        if result:
            print()
            ok("issuers_repaired (NULL issuer_entity_id patched)", result.get("issuers_repaired", "n/a"))
            ok("backfilled (ISSUED_BY instances created)",         result.get("backfilled", 0))
            ok("synced (edges pushed to Neo4j)",                   result.get("synced", 0))
        else:
            warn("Could not parse result JSON from logs")
            # Print raw non-SQL lines for diagnosis
            for msg in messages:
                raw = msg.strip()
                try:
                    d = json.loads(raw)
                    if "mdm_sql" not in d.get("event", ""):
                        print(f"  {raw[:200]}")
                except (json.JSONDecodeError, TypeError):
                    if raw:
                        print(f"  {raw[:200]}")

    # ── Post-backfill coverage check ──────────────────────────────────────────
    hr("Post-backfill coverage")
    run_coverage_check(args.env, args.region)

    print(f"\n{'═' * 62}\n")


if __name__ == "__main__":
    main()
