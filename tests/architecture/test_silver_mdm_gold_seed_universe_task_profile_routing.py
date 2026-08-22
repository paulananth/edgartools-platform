"""Proves write_silver_mdm_gold_definition's own SeedUniverse state has its
task profile genuinely *routed through* command_task_profile() at runtime,
not just coincidentally equal to what command_task_profile() would say.

Resolves large-profile-unscoped-load-audit map ticket 04
(.scratch/large-profile-unscoped-load-audit/issues/
04-audit-load-history-internal-large-states.md). This SeedUniverse state
was still hardcoded to wh_task_large_arn from the original emergency bump,
never ported to the ticket 06/07-decided
command_task_profile('seed-universe') == "medium" routing that
write_load_history_definition's own SeedUniverse already uses (ticket 07)
and that ticket 02 (this same map) already ported to
write_warehouse_mdm_gold_definition. Mirrors
test_warehouse_mdm_gold_seed_universe_task_profile_routing.py's exact
technique against this sibling function.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "infra" / "scripts" / "deploy-aws-application.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")

_COMMAND_TASK_PROFILE_START = "command_task_profile() {\n"
_COMMAND_TASK_PROFILE_END = "\n}\n"

_SMG_START = "write_silver_mdm_gold_definition() {\n"
_SMG_END = "\nPY\n}\n"

_WH_MEDIUM_ARN = "arn:fake-wh-medium"
_WH_LARGE_ARN = "arn:fake-wh-large"


def _script_text() -> str:
    return DEPLOY_SCRIPT.read_text(encoding="utf-8")


def _extract_function_source(start_marker: str, end_marker: str) -> str:
    text = _script_text()
    start = text.index(start_marker)
    end = text.index(end_marker, start) + len(end_marker)
    return text[start:end]


def _seed_universe_task_definition(command_task_profile_override: str | None) -> str:
    """Generate write_silver_mdm_gold_definition()'s real ASL and return
    SeedUniverse's resolved TaskDefinition ARN.

    When ``command_task_profile_override`` is given, it's sourced *after*
    the real command_task_profile() (and after the real
    write_silver_mdm_gold_definition) -- a later function definition wins
    at call time in bash, so this genuinely intercepts whatever
    write_silver_mdm_gold_definition calls internally.
    """
    command_task_profile_source = _extract_function_source(
        _COMMAND_TASK_PROFILE_START, _COMMAND_TASK_PROFILE_END
    )
    smg_source = _extract_function_source(_SMG_START, _SMG_END)

    tmp_root = REPO_ROOT / ".pytest_cache" / "smg_seed_universe_routing_test"
    tmp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=tmp_root) as d:
        tmp_path = Path(d)
        out_file = tmp_path / "silver_mdm_gold.json"

        script_parts = [
            "set -euo pipefail",
            'fail() { echo "ERROR: $*" >&2; exit 1; }',
            command_task_profile_source,
            smg_source,
        ]
        if command_task_profile_override is not None:
            script_parts.append(command_task_profile_override)
        script_parts.append(
            'CLUSTER_ARN="arn:aws:ecs:us-east-1:000000000000:cluster/fake-cluster"\n'
            'BRONZE_BUCKET_NAME="fake-bronze-bucket"\n'
            'PUBLIC_SUBNET_IDS_JSON=\'["subnet-aaaa","subnet-bbbb"]\'\n'
            'SECURITY_GROUP_IDS_JSON=\'["sg-cccc"]\'\n'
            'BOOTSTRAP_BATCH_CONCURRENCY=3\n'
            'MDM_RUN_LIMIT=100\n'
            'MDM_GRAPH_LIMIT=200\n'
            f'SCRIPT_DIR="{DEPLOY_SCRIPT.parent.as_posix()}"\n'
            f'write_silver_mdm_gold_definition "{out_file.as_posix()}" '
            f'"{_WH_MEDIUM_ARN}" "arn:fake-mdm-small" "arn:fake-mdm-medium" "{_WH_LARGE_ARN}"\n'
        )
        driver = tmp_path / "driver.sh"
        driver.write_text("\n".join(script_parts), encoding="utf-8")

        result = subprocess.run(
            ["bash", driver.as_posix()], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise AssertionError(
                f"silver_mdm_gold definition generation failed:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        definition = json.loads(out_file.read_text(encoding="utf-8"))

    return definition["States"]["SeedUniverse"]["Parameters"]["TaskDefinition"]


def test_seed_universe_uses_real_command_task_profile_result() -> None:
    """With the real, unmodified command_task_profile(), SeedUniverse's
    TaskDefinition must equal the medium ARN -- command_task_profile("seed-universe")
    resolves to "medium" (ticket 06's decision, converged onto by ticket
    07, and now also this state)."""
    arn = _seed_universe_task_definition(command_task_profile_override=None)
    assert arn == _WH_MEDIUM_ARN, (
        f"SeedUniverse resolved to {arn!r}, expected the medium ARN "
        f"{_WH_MEDIUM_ARN!r} -- command_task_profile('seed-universe') should "
        "resolve to 'medium'"
    )


def test_seed_universe_genuinely_routes_through_command_task_profile() -> None:
    """Overriding command_task_profile() to answer "medium" for
    seed-universe -- after write_silver_mdm_gold_definition's real body is
    already sourced -- must produce the medium ARN. "medium" (not "large")
    is the only value that actually discriminates hardcode from routing
    here: the pre-fix hardcode was unconditionally wh_task_large_arn, so a
    stub answering "large" would pass even against the unfixed code by
    coincidence (this function only accepts "medium"/"large"). If this
    test fails (resolves to large instead), write_silver_mdm_gold_definition
    is NOT calling command_task_profile() at runtime for this state --
    it's still hardcoding the ARN directly, and the override had nothing
    to intercept."""
    override = (
        'command_task_profile() {\n'
        '  case "$1" in\n'
        '    seed-universe) printf "%s\\n" "medium" ;;\n'
        '    *) fail "unexpected command_task_profile call: $1" ;;\n'
        '  esac\n'
        '}\n'
    )
    arn = _seed_universe_task_definition(command_task_profile_override=override)
    assert arn == _WH_MEDIUM_ARN, (
        f"SeedUniverse resolved to {arn!r} even with command_task_profile() "
        f"stubbed to answer 'medium' for seed-universe -- expected the "
        f"medium ARN {_WH_MEDIUM_ARN!r}. This means "
        "write_silver_mdm_gold_definition is not genuinely routing "
        "SeedUniverse's profile through command_task_profile() at call "
        "time."
    )


def test_seed_universe_calls_command_task_profile_with_exact_command_name() -> None:
    """write_silver_mdm_gold_definition must call command_task_profile()
    with exactly "seed-universe" (the real CLI command name), not some
    other spelling -- a stub that fails on anything else must still let
    generation succeed."""
    strict_stub = (
        'command_task_profile() {\n'
        f'  if [ "$1" != "seed-universe" ]; then\n'
        f'    fail "expected command_task_profile to be called with exactly '
        "'seed-universe', got: $1\"\n"
        '  fi\n'
        '  printf "%s\\n" "medium"\n'
        '}\n'
    )
    arn = _seed_universe_task_definition(command_task_profile_override=strict_stub)
    assert arn == _WH_MEDIUM_ARN
