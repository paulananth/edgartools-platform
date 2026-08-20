"""Proves bootstrap-next's per-window task profile is genuinely *routed
through* command_task_profile() at runtime, not just coincidentally equal
to what command_task_profile() would say.

Resolves task-profile-consolidation wayfinder map ticket 03
(.scratch/task-profile-consolidation/issues/
03-route-bootstrap-next-through-the-shared-lookup.md). Ticket 01 already
proved command_task_profile("bootstrap-next") == "large" matches
write_load_history_definition's real live wiring
(test_task_profile_source_of_truth.py) -- but a value match alone doesn't
prove the *wiring itself* changed; write_load_history_definition could
still hardcode wh_task_large_arn directly and happen to agree. This file
proves the real call happens by overriding command_task_profile() with a
stub *after* sourcing write_load_history_definition's real body, and
checking the stub's answer -- not the original hardcode's -- is what
WindowedBootstrap/RunWindow's TaskDefinition ends up with. Function
resolution in bash happens at call time, not definition time, so a
redefinition between sourcing and invoking genuinely intercepts the call.
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


def _run_window_task_definition(command_task_profile_override: str | None) -> str:
    """Generate write_load_history_definition()'s real ASL and return
    WindowedBootstrap/RunWindow's resolved TaskDefinition ARN.

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

    tmp_root = REPO_ROOT / ".pytest_cache" / "bootstrap_next_routing_test"
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
            'MDM_RUN_LIMIT=100\n'
            'MDM_GRAPH_LIMIT=200\n'
            'MDM_SEED_UNIVERSE_TRACKING_STATUS="bootstrap_pending"\n'
            f'write_load_history_definition "{out_file.as_posix()}" '
            f'"{_WH_SMALL_ARN}" "{_WH_MEDIUM_ARN}" '
            '"arn:fake-mdm-small" "arn:fake-mdm-medium" '
            f'"{_WH_LARGE_ARN}"\n'
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

    branch_a_states = definition["States"]["IngestBronzeAndSilver"]["Branches"][0]["States"]
    run_window = branch_a_states["WindowedBootstrap"]["ItemProcessor"]["States"]["RunWindow"]
    return run_window["Parameters"]["TaskDefinition"]


def test_bootstrap_next_uses_real_command_task_profile_result() -> None:
    """With the real, unmodified command_task_profile(), RunWindow's
    TaskDefinition must equal the large ARN -- command_task_profile("bootstrap-next")
    resolves to "large" (ticket 01's corrected mapping)."""
    arn = _run_window_task_definition(command_task_profile_override=None)
    assert arn == _WH_LARGE_ARN, (
        f"RunWindow resolved to {arn!r}, expected the large ARN "
        f"{_WH_LARGE_ARN!r} -- command_task_profile('bootstrap-next') should "
        "resolve to 'large'"
    )


def test_bootstrap_next_genuinely_routes_through_command_task_profile() -> None:
    """Overriding command_task_profile() to answer "small" for bootstrap-next
    -- after write_load_history_definition's real body is already sourced --
    must flip RunWindow's TaskDefinition to the small ARN. If this fails
    (still resolves to large), write_load_history_definition is NOT calling
    command_task_profile() at runtime -- it's still hardcoding the ARN
    directly, and the override had nothing to intercept.

    write_load_history_definition also calls command_task_profile() for
    "seed-universe" (ticket 07) -- the override answers that call with its
    own real value too, so this test stays scoped to bootstrap-next's
    routing rather than incidentally asserting anything about SeedUniverse
    (see test_seed_universe_task_profile_routing.py for that)."""
    override = (
        'command_task_profile() {\n'
        '  case "$1" in\n'
        '    bootstrap-next) printf "%s\\n" "small" ;;\n'
        '    seed-universe) printf "%s\\n" "medium" ;;\n'
        '    *) fail "unexpected command_task_profile call: $1" ;;\n'
        '  esac\n'
        '}\n'
    )
    arn = _run_window_task_definition(command_task_profile_override=override)
    assert arn == _WH_SMALL_ARN, (
        f"RunWindow resolved to {arn!r} even with command_task_profile() "
        f"stubbed to answer 'small' for bootstrap-next -- expected the "
        f"small ARN {_WH_SMALL_ARN!r}. This means "
        "write_load_history_definition is not genuinely routing bootstrap-next's "
        "profile through command_task_profile() at call time."
    )


def test_bootstrap_next_calls_command_task_profile_with_exact_command_name() -> None:
    """write_load_history_definition must call command_task_profile() with
    exactly "bootstrap-next" (the real CLI command name), not some other
    spelling (e.g. an underscore workflow-name variant) -- a stub that
    fails on anything else (other than the also-real "seed-universe" call
    ticket 07 added) must still let generation succeed."""
    strict_stub = (
        'command_task_profile() {\n'
        '  case "$1" in\n'
        '    bootstrap-next) printf "%s\\n" "large" ;;\n'
        '    seed-universe) printf "%s\\n" "medium" ;;\n'
        '    *) fail "expected command_task_profile to be called with exactly '
        "'bootstrap-next' or 'seed-universe', got: $1\" ;;\n"
        '  esac\n'
        '}\n'
    )
    arn = _run_window_task_definition(command_task_profile_override=strict_stub)
    assert arn == _WH_LARGE_ARN
