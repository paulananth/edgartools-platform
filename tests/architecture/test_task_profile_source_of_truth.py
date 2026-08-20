"""New single command -> task-profile mapping matches every command's
*current real* resolved profile across all three legacy mechanisms it is
meant to eventually replace.

Resolves task-profile-consolidation wayfinder map ticket 01
(.scratch/task-profile-consolidation/issues/
01-define-the-single-command-to-task-profile-source-of-truth.md). This is a
pure additive prefactor: ``command_task_profile()`` is added *alongside*
the existing three mechanisms in infra/scripts/deploy-aws-application.sh --
nothing yet calls it in production wiring (see tickets 02-04, blocked by
this one). This test exists to prove the new mapping is a faithful,
provably behavior-preserving stand-in for what's already live, before those
tickets switch any real caller over.

Every command handled by any of the three legacy mechanisms is resolved
here through its *real* dispatch path, not a re-implementation -- mirroring
tests/architecture/test_source_export_commands_task_sizing.py's technique
(that file covers the SOURCE_EXPORT_COMMANDS subset only; this one covers
the full set any of the three mechanisms answers for, including
load-daily-form-index-for-date / catch-up-daily-form-index / seed-universe,
which aren't gold-affecting but are still resolved via workflow_profile()
today):

1. ``bootstrap-full``, ``targeted-resync``, ``full-reconcile``,
   ``load-daily-form-index-for-date``, ``catch-up-daily-form-index``,
   ``gold-refresh``, ``seed-universe``: workflow_profile()'s case statement,
   invoked directly (the real bash function).
2. ``bootstrap``, ``daily-incremental``: workflow_profile() has cases for
   these two, but they're DEAD CODE -- workflow_profile() is never called
   with these names anywhere in the script (see that function's own
   comment). Their actual RunWarehouseTask step -- the one that runs
   `bootstrap`/`daily-incremental` themselves -- is built directly by
   write_warehouse_mdm_gold_definition, which takes the medium/large ARNs
   as plain parameters. Resolved by generating that function's real state
   machine JSON and reading RunWarehouseTask's actual TaskDefinition.
3. ``bootstrap-next``: never passed to workflow_profile() or
   write_warehouse_mdm_gold_definition at all. load_history's per-window
   task hardcodes its ARN directly to the medium profile -- documented
   here, not re-derived from live wiring, same as
   test_source_export_commands_task_sizing.py's own
   ``_SPECIAL_CASED_PROFILE`` approach.

Ticket 05 (blocked by ticket 04) collapses
test_source_export_commands_task_sizing.py onto ``command_task_profile()``
once tickets 02-04 land and the legacy mechanisms are retired -- until
then, this file and that one independently duplicate a small amount of
extraction/dispatch logic, each proving the *current* live behavior it
covers.
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

# Every command currently resolved by any of the three legacy mechanisms
# command_task_profile() is meant to replace (see module docstring).
_ALL_COMMANDS = {
    "bootstrap-full",
    "targeted-resync",
    "full-reconcile",
    "load-daily-form-index-for-date",
    "catch-up-daily-form-index",
    "gold-refresh",
    "seed-universe",
    "daily-incremental",
    "bootstrap",
    "bootstrap-next",
}

# Commands whose RunWarehouseTask step is built directly by
# write_warehouse_mdm_gold_definition -- workflow_profile() has cases for
# these names but they are unreachable dead code (see module docstring,
# path 2).
_WAREHOUSE_MDM_GOLD_MEMBERS = {"bootstrap", "daily-incremental"}

# bootstrap-next is never passed to workflow_profile() or
# write_warehouse_mdm_gold_definition -- its deployed load_history
# invocation hardcodes the medium profile directly (module docstring, path 3).
_SPECIAL_CASED_PROFILE = {
    "bootstrap-next": "medium",
}

_WORKFLOW_PROFILE_START = "workflow_profile() {\n"
_WORKFLOW_PROFILE_END = "\n}\n"

_COMMAND_TASK_PROFILE_START = "command_task_profile() {\n"
_COMMAND_TASK_PROFILE_END = "\n}\n"

_WMG_START = "write_warehouse_mdm_gold_definition() {\n"
_WMG_END = "\nPY\n}\n"

# Fake ARNs passed into write_warehouse_mdm_gold_definition's medium/large
# parameters -- distinguishable strings so the generated JSON's
# RunWarehouseTask.Parameters.TaskDefinition tells us which one was used.
_FAKE_MEDIUM_ARN = "arn:fake-wh-medium"
_FAKE_LARGE_ARN = "arn:fake-wh-large"
_FAKE_ARN_PROFILE = {_FAKE_MEDIUM_ARN: "medium", _FAKE_LARGE_ARN: "large"}


def _script_text() -> str:
    return DEPLOY_SCRIPT.read_text(encoding="utf-8")


def _extract_function_source(start_marker: str, end_marker: str) -> str:
    text = _script_text()
    start = text.index(start_marker)
    end = text.index(end_marker, start) + len(end_marker)
    return text[start:end]


def _resolve_workflow_profile(workflow_name: str) -> str | None:
    """Invoke the real workflow_profile() bash function. None if unmapped
    (an unhandled workflow name causes it to `fail` -> non-zero exit)."""
    fn_source = _extract_function_source(_WORKFLOW_PROFILE_START, _WORKFLOW_PROFILE_END)
    script = (
        'set -euo pipefail\n'
        'fail() { echo "ERROR: $*" >&2; exit 1; }\n'
        f'{fn_source}\nworkflow_profile "{workflow_name}"\n'
    )
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _resolve_command_task_profile(command_name: str) -> str:
    """Invoke the real command_task_profile() bash function -- the new
    ticket 01 single source of truth."""
    fn_source = _extract_function_source(
        _COMMAND_TASK_PROFILE_START, _COMMAND_TASK_PROFILE_END
    )
    script = (
        'set -euo pipefail\n'
        'fail() { echo "ERROR: $*" >&2; exit 1; }\n'
        f'{fn_source}\ncommand_task_profile "{command_name}"\n'
    )
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, (
        f"command_task_profile({command_name!r}) failed "
        f"(stdout={result.stdout!r} stderr={result.stderr!r})"
    )
    return result.stdout.strip()


def _run_warehouse_task_profile(workflow_name: str) -> str:
    """Generate the real write_warehouse_mdm_gold_definition() state machine
    JSON for workflow_name and return which profile its RunWarehouseTask step
    -- the one that actually runs `bootstrap`/`daily-incremental` themselves
    -- resolves to. Same technique as
    test_source_export_commands_task_sizing.py's helper of the same shape."""
    fn_source = _extract_function_source(_WMG_START, _WMG_END)

    tmp_root = REPO_ROOT / ".pytest_cache" / "task_profile_source_of_truth_test"
    tmp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=tmp_root) as d:
        tmp_path = Path(d)
        fn_file = tmp_path / "wmg_fn.sh"
        fn_file.write_text(fn_source, encoding="utf-8")
        out_file = tmp_path / f"{workflow_name}.json"

        driver = tmp_path / "driver.sh"
        driver.write_text(
            "set -euo pipefail\n"
            'CLUSTER_ARN="arn:aws:ecs:us-east-1:000000000000:cluster/fake-cluster"\n'
            'PUBLIC_SUBNET_IDS_JSON=\'["subnet-aaaa","subnet-bbbb"]\'\n'
            'SECURITY_GROUP_IDS_JSON=\'["sg-cccc"]\'\n'
            'MDM_RUN_LIMIT=100\n'
            'MDM_GRAPH_LIMIT=200\n'
            f'source "{fn_file.as_posix()}"\n'
            f'write_warehouse_mdm_gold_definition "{out_file.as_posix()}" '
            f'"{_FAKE_MEDIUM_ARN}" "arn:fake-mdm-small" "arn:fake-mdm-medium" "{_FAKE_LARGE_ARN}" '
            f'"{workflow_name}" "fake-bronze-bucket" "arn:aws:sns:us-east-1:000000000000:fake-alerts"\n',
            encoding="utf-8",
        )

        result = subprocess.run(
            ["bash", driver.as_posix()], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise AssertionError(
                f"{workflow_name} definition generation failed:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        definition = json.loads(out_file.read_text(encoding="utf-8"))

    arn = definition["States"]["RunWarehouseTask"]["Parameters"]["TaskDefinition"]
    assert arn in _FAKE_ARN_PROFILE, (
        f"{workflow_name}'s RunWarehouseTask resolved to an unrecognized ARN {arn!r} -- "
        "write_warehouse_mdm_gold_definition's parameter wiring changed shape"
    )
    return _FAKE_ARN_PROFILE[arn]


def _legacy_resolved_profile(command_name: str) -> str:
    """Resolve command_name's *current real* profile via whichever of the
    three legacy mechanisms actually governs it live today."""
    if command_name in _WAREHOUSE_MDM_GOLD_MEMBERS:
        return _run_warehouse_task_profile(command_name.replace("-", "_"))

    workflow_name = command_name.replace("-", "_")
    profile = _resolve_workflow_profile(workflow_name)
    if profile is not None:
        return profile

    assert command_name in _SPECIAL_CASED_PROFILE, (
        f"{command_name!r} has no legacy resolution path -- it isn't handled "
        "by workflow_profile(), isn't in _WAREHOUSE_MDM_GOLD_MEMBERS, and "
        "isn't in _SPECIAL_CASED_PROFILE either. Either it doesn't belong in "
        "_ALL_COMMANDS, or this test's dispatch needs updating to match a "
        "real new mechanism."
    )
    return _SPECIAL_CASED_PROFILE[command_name]


def test_command_task_profile_covers_every_legacy_command() -> None:
    """command_task_profile() must resolve every command any of the three
    legacy mechanisms currently answers for -- a command this new mapping
    can't answer for is exactly the gap tickets 02-04 would inherit."""
    for command_name in sorted(_ALL_COMMANDS):
        # Resolving must not raise/fail -- absence surfaces as an assertion
        # failure inside the helper itself.
        _resolve_command_task_profile(command_name)


@pytest.mark.parametrize("command_name", sorted(_ALL_COMMANDS))
def test_command_task_profile_matches_current_live_behavior(command_name: str) -> None:
    """command_task_profile()'s answer must equal what the command *actually*
    resolves to today via its real legacy mechanism -- the acceptance bar
    ticket 01 sets so tickets 02-04 are safe, mechanical migrations instead
    of judgment calls."""
    new_profile = _resolve_command_task_profile(command_name)
    legacy_profile = _legacy_resolved_profile(command_name)
    assert new_profile == legacy_profile, (
        f"{command_name!r}: command_task_profile() says {new_profile!r}, but "
        f"its real current dispatch path resolves to {legacy_profile!r}"
    )


def test_command_task_profile_rejects_unknown_command() -> None:
    """An unmapped command must fail loudly (matching workflow_profile()'s
    own `fail` behavior on an unknown workflow), not silently default to a
    profile -- the exact silent-drift failure mode this ticket closes."""
    fn_source = _extract_function_source(
        _COMMAND_TASK_PROFILE_START, _COMMAND_TASK_PROFILE_END
    )
    script = (
        'set -euo pipefail\n'
        'fail() { echo "ERROR: $*" >&2; exit 1; }\n'
        f'{fn_source}\ncommand_task_profile "not-a-real-command"\n'
    )
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=10
    )
    assert result.returncode != 0
