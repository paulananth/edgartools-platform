"""Proves CaptureAndVerifyNewFilings's (daily-incremental's own run step) task
profile is genuinely *routed through* command_task_profile() at runtime,
not just coincidentally equal to what command_task_profile() would say.

Resolves task-profile-consolidation wayfinder map ticket 02
(.scratch/task-profile-consolidation/issues/
02-route-write-warehouse-mdm-gold-definition-through-the-shared-profile.md).
Ticket 01 already proved command_task_profile("daily-incremental") ==
"large" matches write_warehouse_mdm_gold_definition's real live wiring
(test_task_profile_source_of_truth.py) -- but a value match alone doesn't
prove the *wiring itself* changed; the function could still hardcode
wh_task_large_arn directly and happen to agree. This file proves the real
call happens by overriding command_task_profile() with a stub *after*
sourcing write_warehouse_mdm_gold_definition's real body, and checking the
stub's answer -- not the original hardcode's -- is what CaptureAndVerifyNewFilings's
TaskDefinition ends up with. Function resolution in bash happens at call
time, not definition time, so a redefinition between sourcing and invoking
genuinely intercepts the call. Mirrors
test_bootstrap_next_task_profile_routing.py's technique exactly (ticket 03's
equivalent proof for the sibling call site).

(Originally parametrized over ["bootstrap", "daily_incremental"] --
bootstrap was retired by state-machine-consolidation ticket 06, so these
now cover daily_incremental only.)
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


def _run_warehouse_task_definition(
    workflow_name: str, command_task_profile_override: str | None
) -> str:
    """Generate write_warehouse_mdm_gold_definition()'s real ASL for
    workflow_name and return CaptureAndVerifyNewFilings's resolved TaskDefinition ARN.

    When ``command_task_profile_override`` is given, it's sourced *after*
    the real command_task_profile() and write_warehouse_mdm_gold_definition
    -- a later function definition wins at call time in bash, so this
    genuinely intercepts whatever write_warehouse_mdm_gold_definition calls
    internally.
    """
    command_task_profile_source = _extract_function_source(
        _COMMAND_TASK_PROFILE_START, _COMMAND_TASK_PROFILE_END
    )
    wmg_source = _extract_function_source(_WMG_START, _WMG_END)

    tmp_root = REPO_ROOT / ".pytest_cache" / "run_warehouse_task_profile_routing_test"
    tmp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=tmp_root) as d:
        tmp_path = Path(d)
        out_file = tmp_path / f"{workflow_name}.json"

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
            f'SCRIPT_DIR="{(REPO_ROOT / "infra" / "scripts").as_posix()}"\n'
            f'write_warehouse_mdm_gold_definition "{out_file.as_posix()}" '
            f'"{_WH_MEDIUM_ARN}" "{_WH_LARGE_ARN}" '
            f'"{workflow_name}" "fake-bronze-bucket" "arn:aws:sns:us-east-1:000000000000:fake-alerts" '
            '"arn:fake-mdm-machine"\n'
        )
        driver = tmp_path / "driver.sh"
        driver.write_text("\n".join(script_parts), encoding="utf-8")

        result = subprocess.run(
            ["bash", driver.as_posix()], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise AssertionError(
                f"{workflow_name} definition generation failed:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        definition = json.loads(out_file.read_text(encoding="utf-8"))

    return definition["States"]["CaptureAndVerifyNewFilings"]["Parameters"]["TaskDefinition"]


@pytest.mark.parametrize("workflow_name", ["daily_incremental"])
def test_run_warehouse_task_uses_real_command_task_profile_result(workflow_name: str) -> None:
    """With the real, unmodified command_task_profile(), CaptureAndVerifyNewFilings's
    TaskDefinition must equal the large ARN -- command_task_profile('daily-incremental')
    resolves to "large" (ticket 01's mapping)."""
    arn = _run_warehouse_task_definition(workflow_name, command_task_profile_override=None)
    assert arn == _WH_LARGE_ARN, (
        f"{workflow_name}'s CaptureAndVerifyNewFilings resolved to {arn!r}, expected the "
        f"large ARN {_WH_LARGE_ARN!r}"
    )


@pytest.mark.parametrize("workflow_name", ["daily_incremental"])
def test_run_warehouse_task_genuinely_routes_through_command_task_profile(
    workflow_name: str,
) -> None:
    """Overriding command_task_profile() to answer "medium" for this
    workflow's real hyphenated command name -- after
    write_warehouse_mdm_gold_definition's real body is already sourced --
    must flip CaptureAndVerifyNewFilings's TaskDefinition to the medium ARN. If this
    fails (still resolves to large), write_warehouse_mdm_gold_definition is
    NOT calling command_task_profile() at runtime -- it's still hardcoding
    the ARN directly, and the override had nothing to intercept.

    The stub also answers 'seed-universe' unconditionally in case the
    generated definition includes a SeedUniverse state, so this test stays
    scoped to CaptureAndVerifyNewFilings's own routing regardless. (The dedicated
    SeedUniverse-routing proof this docstring used to point to,
    test_warehouse_mdm_gold_seed_universe_task_profile_routing.py, was
    deleted by state-machine-consolidation ticket 06: the production branch
    it exercised, write_warehouse_mdm_gold_definition's
    `if workflow_name != "daily_incremental":`, is now dead code with no
    live caller -- daily_incremental's own branch does not reach it. A
    future revival of that branch for a new second caller should re-add a
    routing test rather than assume this one still proves it.)"""
    real_command_name = "daily-incremental"
    override = (
        'command_task_profile() {\n'
        f'  case "$1" in\n'
        f'    {real_command_name}) printf "%s\\n" "medium" ;;\n'
        '    seed-universe) printf "%s\\n" "medium" ;;\n'
        '    *) fail "unexpected command_task_profile call: $1" ;;\n'
        '  esac\n'
        '}\n'
    )
    arn = _run_warehouse_task_definition(workflow_name, command_task_profile_override=override)
    assert arn == _WH_MEDIUM_ARN, (
        f"{workflow_name}'s CaptureAndVerifyNewFilings resolved to {arn!r} even with "
        f"command_task_profile() stubbed to answer 'medium' for "
        f"{real_command_name!r} -- expected the medium ARN {_WH_MEDIUM_ARN!r}. "
        "This means write_warehouse_mdm_gold_definition is not genuinely "
        "routing this workflow's profile through command_task_profile() at "
        "call time."
    )


@pytest.mark.parametrize(
    ("workflow_name", "real_command_name"),
    [("daily_incremental", "daily-incremental")],
)
def test_run_warehouse_task_calls_command_task_profile_with_exact_command_name(
    workflow_name: str, real_command_name: str
) -> None:
    """write_warehouse_mdm_gold_definition must call command_task_profile()
    with exactly the real hyphenated CLI command name, not the underscore
    workflow_name spelling -- a stub that fails on anything else must still
    let generation succeed. The stub also permits a 'seed-universe' call
    defensively (that lookup is gated on workflow_name != "daily_incremental"
    in the real function -- see its own comment -- so daily_incremental
    itself must never trigger it; this test's own parametrization is
    daily_incremental-only after state-machine-consolidation ticket 06
    retired the other former case, `bootstrap`, which did call it)."""
    strict_stub = (
        'command_task_profile() {\n'
        f'  if [ "$1" != "{real_command_name}" ] && [ "$1" != "seed-universe" ]; then\n'
        f'    fail "expected command_task_profile to be called with exactly '
        f"'{real_command_name}' or 'seed-universe', got: $1\"\n"
        '  fi\n'
        '  printf "%s\\n" "large"\n'
        '}\n'
    )
    arn = _run_warehouse_task_definition(workflow_name, command_task_profile_override=strict_stub)
    assert arn == _WH_LARGE_ARN
