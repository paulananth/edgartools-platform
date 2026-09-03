"""Proves load_history's SeedUniverse state has its task profile genuinely
*routed through* command_task_profile() at runtime, not just coincidentally
equal to what command_task_profile() would say.

Resolves task-profile-consolidation wayfinder map ticket 07
(.scratch/task-profile-consolidation/issues/
07-decide-whether-to-revert-load-historys-seeduniverse-off-large.md).
SeedUniverse was hardcoded to wh_task_large_arn from a 2026-08-09 emergency
OOM bump; ticket 07 (2026-08-20, user-confirmed) reverted it to route
through command_task_profile('seed-universe') -- the same ticket 01 single
source of truth bootstrap-next already uses (ticket 03,
test_bootstrap_next_task_profile_routing.py, the file this one mirrors) --
instead of a second hardcode. A value match alone (SeedUniverse's
TaskDefinition happening to equal the medium ARN) doesn't prove the wiring
itself changed; write_load_history_definition could still hardcode
wh_task_medium_arn directly and happen to agree. This file proves the real
call happens by overriding command_task_profile() with a stub *after*
sourcing write_load_history_definition's real body, and checking the
stub's answer -- not the original hardcode's -- is what SeedUniverse's
TaskDefinition ends up with. Function resolution in bash happens at call
time, not definition time, so a redefinition between sourcing and invoking
genuinely intercepts the call.
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

_LOAD_HISTORY_START = "write_load_history_definition() {\n"
_LOAD_HISTORY_END = "\nPY\n}\n"

_WH_SMALL_ARN = "arn:fake-wh-small"
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
    """Generate write_load_history_definition()'s real ASL and return
    SeedUniverse's resolved TaskDefinition ARN.

    When ``command_task_profile_override`` is given, it's sourced *after*
    the real command_task_profile() (and after the real
    write_load_history_definition, though definition order doesn't matter
    for bash function resolution -- only call order does) -- a later
    function definition wins at call time, so this genuinely intercepts
    whatever write_load_history_definition calls internally, rather than
    relying on write_load_history_definition importing/calling a
    Python-side copy.
    """
    command_task_profile_source = _extract_function_source(
        _COMMAND_TASK_PROFILE_START, _COMMAND_TASK_PROFILE_END
    )
    load_history_source = _extract_function_source(_LOAD_HISTORY_START, _LOAD_HISTORY_END)

    tmp_root = REPO_ROOT / ".pytest_cache" / "seed_universe_routing_test"
    tmp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=tmp_root) as d:
        tmp_path = Path(d)
        out_file = tmp_path / "load_history.json"

        script_parts = [
            "set -euo pipefail",
            'fail() { echo "ERROR: $*" >&2; exit 1; }',
            command_task_profile_source,
            load_history_source,
        ]
        if command_task_profile_override is not None:
            script_parts.append(command_task_profile_override)
        script_parts.append(
            'CLUSTER_ARN="arn:aws:ecs:us-east-1:000000000000:cluster/fake-cluster"\n'
            'BRONZE_BUCKET_NAME="fake-bronze-bucket"\n'
            'PUBLIC_SUBNET_IDS_JSON=\'["subnet-aaaa","subnet-bbbb"]\'\n'
            'SECURITY_GROUP_IDS_JSON=\'["sg-cccc"]\'\n'
            'MDM_SEED_UNIVERSE_TRACKING_STATUS="bootstrap_pending"\n'
            f'SCRIPT_DIR="{(REPO_ROOT / "infra" / "scripts").as_posix()}"\n'
            f'write_load_history_definition "{out_file.as_posix()}" '
            f'"{_WH_SMALL_ARN}" "{_WH_MEDIUM_ARN}" '
            '"arn:fake-mdm-medium" '
            f'"{_WH_LARGE_ARN}" "arn:fake-mdm-machine"\n'
        )
        driver = tmp_path / "driver.sh"
        driver.write_text("\n".join(script_parts), encoding="utf-8")

        result = subprocess.run(
            ["bash", driver.as_posix()], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise AssertionError(
                f"load_history definition generation failed:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        definition = json.loads(out_file.read_text(encoding="utf-8"))

    return definition["States"]["SeedUniverse"]["Parameters"]["TaskDefinition"]


def test_seed_universe_uses_real_command_task_profile_result() -> None:
    """With the real, unmodified command_task_profile(), SeedUniverse's
    TaskDefinition must equal the medium ARN -- command_task_profile("seed-universe")
    resolves to "medium" (ticket 06's decision, converged onto by ticket 07)."""
    arn = _seed_universe_task_definition(command_task_profile_override=None)
    assert arn == _WH_MEDIUM_ARN, (
        f"SeedUniverse resolved to {arn!r}, expected the medium ARN "
        f"{_WH_MEDIUM_ARN!r} -- command_task_profile('seed-universe') should "
        "resolve to 'medium'"
    )


def test_seed_universe_genuinely_routes_through_command_task_profile() -> None:
    """Overriding command_task_profile() to answer "small" for seed-universe
    -- after write_load_history_definition's real body is already sourced --
    must flip SeedUniverse's TaskDefinition to the small ARN. If this fails
    (still resolves to medium), write_load_history_definition is NOT calling
    command_task_profile() at runtime for this state -- it's still hardcoding
    the ARN directly, and the override had nothing to intercept.

    write_load_history_definition also calls command_task_profile() for
    "bootstrap-next" (ticket 03), earlier in the function body -- the
    override answers that call with its own real value too, so this test
    stays scoped to SeedUniverse's routing rather than incidentally
    asserting anything about bootstrap-next's (see
    test_bootstrap_next_task_profile_routing.py for that)."""
    override = (
        'command_task_profile() {\n'
        '  case "$1" in\n'
        '    bootstrap-next) printf "%s\\n" "large" ;;\n'
        '    seed-universe) printf "%s\\n" "small" ;;\n'
        '    *) fail "unexpected command_task_profile call: $1" ;;\n'
        '  esac\n'
        '}\n'
    )
    arn = _seed_universe_task_definition(command_task_profile_override=override)
    assert arn == _WH_SMALL_ARN, (
        f"SeedUniverse resolved to {arn!r} even with command_task_profile() "
        f"stubbed to answer 'small' for seed-universe -- expected the "
        f"small ARN {_WH_SMALL_ARN!r}. This means "
        "write_load_history_definition is not genuinely routing SeedUniverse's "
        "profile through command_task_profile() at call time."
    )


def test_seed_universe_calls_command_task_profile_with_exact_command_name() -> None:
    """write_load_history_definition must call command_task_profile() with
    exactly "seed-universe" (the real CLI command name), not some other
    spelling (e.g. an underscore workflow-name variant) -- a stub that
    fails on anything else (other than the also-real "bootstrap-next" call
    ticket 03 already made) must still let generation succeed."""
    strict_stub = (
        'command_task_profile() {\n'
        '  case "$1" in\n'
        '    bootstrap-next) printf "%s\\n" "large" ;;\n'
        '    seed-universe) printf "%s\\n" "medium" ;;\n'
        '    *) fail "expected command_task_profile to be called with exactly '
        "'seed-universe' or 'bootstrap-next', got: $1\" ;;\n"
        '  esac\n'
        '}\n'
    )
    arn = _seed_universe_task_definition(command_task_profile_override=strict_stub)
    assert arn == _WH_MEDIUM_ARN
