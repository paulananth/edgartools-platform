"""Proves write_warehouse_mdm_gold_definition's own SeedUniverse state has
its task profile genuinely *routed through* command_task_profile() at
runtime, not just coincidentally equal to what command_task_profile()
would say.

Resolves large-profile-unscoped-load-audit map ticket 02
(.scratch/large-profile-unscoped-load-audit/issues/
02-audit-core-warehouse-commands-large-profile.md). This SeedUniverse
state (workflow_name="bootstrap" -- it only exists when workflow_name !=
"daily_incremental") was still hardcoded to wh_task_large_arn from the
original emergency bump, never ported to the ticket 06/07-decided
command_task_profile('seed-universe') == "medium" routing that
write_load_history_definition's own SeedUniverse already uses (ticket 07,
proven by test_seed_universe_task_profile_routing.py, the file this one
mirrors, and test_run_warehouse_task_profile_routing.py, whose technique
against this exact function this file also mirrors). A value match alone
doesn't prove the wiring itself changed; write_warehouse_mdm_gold_definition
could still hardcode wh_task_medium_arn directly and happen to agree. This
file proves the real call happens by overriding command_task_profile()
with a stub *after* sourcing write_warehouse_mdm_gold_definition's real
body, and checking the stub's answer -- not the original hardcode's -- is
what SeedUniverse's TaskDefinition ends up with.
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

_WMG_START = "write_warehouse_mdm_gold_definition() {\n"
_WMG_END = "\nPY\n}\n"

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
    """Generate write_warehouse_mdm_gold_definition()'s real ASL for
    workflow_name="bootstrap" (the only workflow_name that produces a
    SeedUniverse state in this function) and return SeedUniverse's
    resolved TaskDefinition ARN.

    When ``command_task_profile_override`` is given, it's sourced *after*
    the real command_task_profile() and write_warehouse_mdm_gold_definition
    -- a later function definition wins at call time in bash, so this
    genuinely intercepts whatever write_warehouse_mdm_gold_definition
    calls internally.
    """
    command_task_profile_source = _extract_function_source(
        _COMMAND_TASK_PROFILE_START, _COMMAND_TASK_PROFILE_END
    )
    wmg_source = _extract_function_source(_WMG_START, _WMG_END)

    tmp_root = REPO_ROOT / ".pytest_cache" / "wmg_seed_universe_routing_test"
    tmp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=tmp_root) as d:
        tmp_path = Path(d)
        out_file = tmp_path / "bootstrap.json"

        script_parts = [
            "set -euo pipefail",
            'fail() { echo "ERROR: $*" >&2; exit 1; }',
            command_task_profile_source,
            wmg_source,
        ]
        if command_task_profile_override is not None:
            script_parts.append(command_task_profile_override)
        script_parts.append(
            'CLUSTER_ARN="arn:aws:ecs:us-east-1:000000000000:cluster/fake-cluster"\n'
            'PUBLIC_SUBNET_IDS_JSON=\'["subnet-aaaa","subnet-bbbb"]\'\n'
            'SECURITY_GROUP_IDS_JSON=\'["sg-cccc"]\'\n'
            'MDM_RUN_LIMIT=100\n'
            'MDM_GRAPH_LIMIT=200\n'
            f'write_warehouse_mdm_gold_definition "{out_file.as_posix()}" '
            f'"{_WH_MEDIUM_ARN}" "arn:fake-mdm-small" "arn:fake-mdm-medium" "{_WH_LARGE_ARN}" '
            '"bootstrap" "fake-bronze-bucket" "arn:aws:sns:us-east-1:000000000000:fake-alerts"\n'
        )
        driver = tmp_path / "driver.sh"
        driver.write_text("\n".join(script_parts), encoding="utf-8")

        result = subprocess.run(
            ["bash", driver.as_posix()], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise AssertionError(
                f"bootstrap definition generation failed:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        definition = json.loads(out_file.read_text(encoding="utf-8"))

    return definition["States"]["SeedUniverse"]["Parameters"]["TaskDefinition"]


def test_seed_universe_uses_real_command_task_profile_result() -> None:
    """With the real, unmodified command_task_profile(), SeedUniverse's
    TaskDefinition must equal the medium ARN -- command_task_profile("seed-universe")
    resolves to "medium" (ticket 06's decision, converged onto by ticket 07,
    and now also this state)."""
    arn = _seed_universe_task_definition(command_task_profile_override=None)
    assert arn == _WH_MEDIUM_ARN, (
        f"SeedUniverse resolved to {arn!r}, expected the medium ARN "
        f"{_WH_MEDIUM_ARN!r} -- command_task_profile('seed-universe') should "
        "resolve to 'medium'"
    )


def test_seed_universe_genuinely_routes_through_command_task_profile() -> None:
    """Overriding command_task_profile() to answer "medium" for
    seed-universe -- after write_warehouse_mdm_gold_definition's real body
    is already sourced -- must produce the medium ARN. "medium" (not
    "large") is the only value that actually discriminates hardcode from
    routing here: the pre-fix hardcode was unconditionally wh_task_large_arn,
    so a stub answering "large" would pass even against the unfixed code by
    coincidence (this function only accepts "medium"/"large" -- unlike
    write_load_history_definition's sibling test, which has a third "small"
    value available to use as an unambiguous flip). If this test fails
    (resolves to large instead), write_warehouse_mdm_gold_definition is NOT
    calling command_task_profile() at runtime for this state -- it's still
    hardcoding the ARN directly, and the override had nothing to intercept.

    write_warehouse_mdm_gold_definition also calls command_task_profile()
    for "bootstrap" (RunWarehouseTask's own routing, task-profile-
    consolidation ticket 02) -- the override answers that call with its
    own real value too, so this test stays scoped to SeedUniverse's
    routing rather than incidentally asserting anything about
    RunWarehouseTask's (see test_run_warehouse_task_profile_routing.py for
    that)."""
    override = (
        'command_task_profile() {\n'
        '  case "$1" in\n'
        '    bootstrap) printf "%s\\n" "large" ;;\n'
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
        "write_warehouse_mdm_gold_definition is not genuinely routing "
        "SeedUniverse's profile through command_task_profile() at call "
        "time."
    )


def test_seed_universe_calls_command_task_profile_with_exact_command_name() -> None:
    """write_warehouse_mdm_gold_definition must call command_task_profile()
    with exactly "seed-universe" (the real CLI command name), not some
    other spelling -- a stub that fails on anything else (other than the
    also-real "bootstrap" call for RunWarehouseTask's own routing) must
    still let generation succeed."""
    strict_stub = (
        'command_task_profile() {\n'
        '  case "$1" in\n'
        '    bootstrap) printf "%s\\n" "large" ;;\n'
        '    seed-universe) printf "%s\\n" "medium" ;;\n'
        '    *) fail "expected command_task_profile to be called with exactly '
        "'seed-universe' or 'bootstrap', got: $1\" ;;\n"
        '  esac\n'
        '}\n'
    )
    arn = _seed_universe_task_definition(command_task_profile_override=strict_stub)
    assert arn == _WH_MEDIUM_ARN
