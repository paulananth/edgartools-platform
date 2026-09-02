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
2. ``daily-incremental``: workflow_profile() has a case for this, but it's
   DEAD CODE -- workflow_profile() is never called with this name anywhere
   in the script (see that function's own comment). Its actual
   RunWarehouseTask step -- the one that runs `daily-incremental` itself --
   is built directly by write_warehouse_mdm_gold_definition, which takes
   the medium/large ARNs as plain parameters. Resolved by generating that
   function's real state machine JSON and reading RunWarehouseTask's
   actual TaskDefinition. (``bootstrap`` was this path's other member
   until state-machine-consolidation ticket 06 retired it.)
3. ``bootstrap-next``: never passed to workflow_profile() or
   write_warehouse_mdm_gold_definition at all. load_history's per-window
   WindowedBootstrap/RunWindow task hardcodes its ARN directly. Resolved
   the same way as path 2 -- generating write_load_history_definition's
   real state machine JSON and reading RunWindow's actual TaskDefinition --
   NOT a hardcoded assumption. (An earlier version of this file hardcoded
   this as "medium" via a `_SPECIAL_CASED_PROFILE` entry, copied from
   test_source_export_commands_task_sizing.py's own stale assumption of the
   same shape. Both were wrong: the real wiring was bumped to large on
   2026-08-10 after a live exit-137 OOM on medium (see
   test_load_history_state_machine.py's
   test_windowed_bootstrap_uses_large_task_definition), and neither test
   had been updated since. Caught 2026-08-19 while implementing ticket 03 --
   had it gone uncorrected, "migrating" bootstrap-next onto
   command_task_profile()'s then-wrong "medium" value would have
   reintroduced that exact OOM. Fixed by deriving the value from live ASL
   generation instead of a hand-maintained assumption, closing the gap that
   let the drift go unnoticed in the first place.)

Ticket 05 (blocked by ticket 04) collapses
test_source_export_commands_task_sizing.py onto ``command_task_profile()``
once tickets 02-04 land and the legacy mechanisms are retired -- until
then, this file and that one independently duplicate a small amount of
extraction/dispatch logic, each proving the *current* live behavior it
covers.

UPDATE (2026-08-19, tickets 02-04 landed): all three paths above now
resolve through ``command_task_profile()`` themselves rather than through
independent logic -- path 1 because ``workflow_profile()`` is now a thin
pass-through onto it (ticket 04); paths 2 and 3 because
``write_warehouse_mdm_gold_definition``/``write_load_history_definition``
now call it directly (tickets 02/03). This test therefore no longer proves
the new mapping against genuinely independent legacy behavior -- it's a
regression-lock confirming the migration didn't change any command's
resolved profile, and confirming an unmapped command still fails loudly
end-to-end through whichever real caller reaches it.

UPDATE (2026-08-19, ticket 05 landed):
test_source_export_commands_task_sizing.py's own three-mechanism
reverse-engineering is now retired -- it asserts against
``command_task_profile()`` directly for its SOURCE_EXPORT_COMMANDS subset.
This file still covers the full _ALL_COMMANDS set (including
load-daily-form-index-for-date / catch-up-daily-form-index / seed-universe,
which aren't gold-affecting and so fall outside that file's scope) and still
regenerates real ASL for paths 2/3 rather than calling
``command_task_profile()`` a second time under a different name, so the two
files are not yet fully redundant -- left as two files, not folded into one,
since no ticket has scoped that decision.
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
    "bootstrap-next",
}

# Commands whose RunWarehouseTask step is built directly by
# write_warehouse_mdm_gold_definition -- workflow_profile() has a case for
# this name but it is unreachable dead code (see module docstring, path 2).
_WAREHOUSE_MDM_GOLD_MEMBERS = {"daily-incremental"}

# bootstrap-next is never passed to workflow_profile() or
# write_warehouse_mdm_gold_definition -- resolved instead via
# write_load_history_definition's real generated ASL (module docstring,
# path 3) by _run_load_history_bootstrap_next_profile below.
_LOAD_HISTORY_MEMBERS = {"bootstrap-next"}

_WORKFLOW_PROFILE_START = "workflow_profile() {\n"
_WORKFLOW_PROFILE_END = "\n}\n"

_COMMAND_TASK_PROFILE_START = "command_task_profile() {\n"
_COMMAND_TASK_PROFILE_END = "\n}\n"

_WMG_START = "write_warehouse_mdm_gold_definition() {\n"
_WMG_END = "\nPY\n}\n"

_LOAD_HISTORY_START = "write_load_history_definition() {\n"
_LOAD_HISTORY_END = "\nPY\n}\n"

# Fake ARNs passed into write_warehouse_mdm_gold_definition's medium/large
# parameters -- distinguishable strings so the generated JSON's
# RunWarehouseTask.Parameters.TaskDefinition tells us which one was used.
_FAKE_MEDIUM_ARN = "arn:fake-wh-medium"
_FAKE_LARGE_ARN = "arn:fake-wh-large"
_FAKE_ARN_PROFILE = {_FAKE_MEDIUM_ARN: "medium", _FAKE_LARGE_ARN: "large"}

# Fake ARNs for write_load_history_definition's 5-way small/medium/large
# (warehouse) + small/medium (mdm) parameter signature -- only the two
# warehouse-side values matter for resolving bootstrap-next's profile.
_FAKE_WH_SMALL_ARN = "arn:fake-wh-small"
_FAKE_WH_MEDIUM_ARN = "arn:fake-wh-medium-lh"
_FAKE_WH_LARGE_ARN = "arn:fake-wh-large-lh"
_FAKE_LOAD_HISTORY_ARN_PROFILE = {
    _FAKE_WH_SMALL_ARN: "small",
    _FAKE_WH_MEDIUM_ARN: "medium",
    _FAKE_WH_LARGE_ARN: "large",
}


def _script_text() -> str:
    return DEPLOY_SCRIPT.read_text(encoding="utf-8")


def _extract_function_source(start_marker: str, end_marker: str) -> str:
    text = _script_text()
    start = text.index(start_marker)
    end = text.index(end_marker, start) + len(end_marker)
    return text[start:end]


def _resolve_workflow_profile(workflow_name: str) -> str | None:
    """Invoke the real workflow_profile() bash function. None if unmapped
    (an unhandled workflow name causes it to `fail` -> non-zero exit).
    workflow_profile() is now a thin pass-through onto command_task_profile()
    (task-profile-consolidation ticket 04), so that function's source must
    be sourced first too."""
    fn_source = _extract_function_source(_WORKFLOW_PROFILE_START, _WORKFLOW_PROFILE_END)
    command_task_profile_source = _extract_function_source(
        _COMMAND_TASK_PROFILE_START, _COMMAND_TASK_PROFILE_END
    )
    script = (
        'set -euo pipefail\n'
        'fail() { echo "ERROR: $*" >&2; exit 1; }\n'
        f'{command_task_profile_source}\n{fn_source}\nworkflow_profile "{workflow_name}"\n'
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
    -- the one that actually runs `daily-incremental` itself -- resolves to.
    Same technique as
    test_source_export_commands_task_sizing.py's helper of the same shape.
    write_warehouse_mdm_gold_definition now calls command_task_profile()
    internally (task-profile-consolidation ticket 02), so that function's
    source must be sourced first too."""
    fn_source = _extract_function_source(_WMG_START, _WMG_END)
    command_task_profile_source = _extract_function_source(
        _COMMAND_TASK_PROFILE_START, _COMMAND_TASK_PROFILE_END
    )

    tmp_root = REPO_ROOT / ".pytest_cache" / "task_profile_source_of_truth_test"
    tmp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=tmp_root) as d:
        tmp_path = Path(d)
        fn_file = tmp_path / "wmg_fn.sh"
        fn_file.write_text(fn_source, encoding="utf-8")
        command_task_profile_file = tmp_path / "command_task_profile_fn.sh"
        command_task_profile_file.write_text(command_task_profile_source, encoding="utf-8")
        out_file = tmp_path / f"{workflow_name}.json"

        driver = tmp_path / "driver.sh"
        driver.write_text(
            "set -euo pipefail\n"
            'fail() { echo "ERROR: $*" >&2; exit 1; }\n'
            'CLUSTER_ARN="arn:aws:ecs:us-east-1:000000000000:cluster/fake-cluster"\n'
            'PUBLIC_SUBNET_IDS_JSON=\'["subnet-aaaa","subnet-bbbb"]\'\n'
            'SECURITY_GROUP_IDS_JSON=\'["sg-cccc"]\'\n'
            'MDM_RUN_LIMIT=100\n'
            'MDM_GRAPH_LIMIT=200\n'
            f'source "{command_task_profile_file.as_posix()}"\n'
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


def _run_load_history_bootstrap_next_profile() -> str:
    """Generate the real write_load_history_definition() state machine JSON
    and return which profile bootstrap-next's per-window RunWindow step --
    the actual `bootstrap-next --silver-only` task -- resolves to. Same
    technique as test_load_history_state_machine.py's `definition` fixture
    and _run_warehouse_task_profile above; this is what makes bootstrap-next
    a genuine live-derived value, not a hardcoded assumption (see module
    docstring, path 3, and the incident it documents). write_load_history_definition
    now calls command_task_profile() internally (task-profile-consolidation
    ticket 03), so that function's source must be sourced first too."""
    fn_source = _extract_function_source(_LOAD_HISTORY_START, _LOAD_HISTORY_END)
    command_task_profile_source = _extract_function_source(
        _COMMAND_TASK_PROFILE_START, _COMMAND_TASK_PROFILE_END
    )

    tmp_root = REPO_ROOT / ".pytest_cache" / "task_profile_source_of_truth_test"
    tmp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=tmp_root) as d:
        tmp_path = Path(d)
        fn_file = tmp_path / "load_history_fn.sh"
        fn_file.write_text(fn_source, encoding="utf-8")
        command_task_profile_file = tmp_path / "command_task_profile_fn.sh"
        command_task_profile_file.write_text(command_task_profile_source, encoding="utf-8")
        out_file = tmp_path / "load_history.json"

        driver = tmp_path / "driver.sh"
        driver.write_text(
            "set -euo pipefail\n"
            'fail() { echo "ERROR: $*" >&2; exit 1; }\n'
            'CLUSTER_ARN="arn:aws:ecs:us-east-1:000000000000:cluster/fake-cluster"\n'
            'BRONZE_BUCKET_NAME="fake-bronze-bucket"\n'
            'PUBLIC_SUBNET_IDS_JSON=\'["subnet-aaaa","subnet-bbbb"]\'\n'
            'SECURITY_GROUP_IDS_JSON=\'["sg-cccc"]\'\n'
            'MDM_RUN_LIMIT=100\n'
            'MDM_GRAPH_LIMIT=200\n'
            'MDM_SEED_UNIVERSE_TRACKING_STATUS="bootstrap_pending"\n'
            f'source "{command_task_profile_file.as_posix()}"\n'
            f'source "{fn_file.as_posix()}"\n'
            f'write_load_history_definition "{out_file.as_posix()}" '
            f'"{_FAKE_WH_SMALL_ARN}" "{_FAKE_WH_MEDIUM_ARN}" '
            '"arn:fake-mdm-small" "arn:fake-mdm-medium" '
            f'"{_FAKE_WH_LARGE_ARN}"\n',
            encoding="utf-8",
        )

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
    arn = run_window["Parameters"]["TaskDefinition"]
    assert arn in _FAKE_LOAD_HISTORY_ARN_PROFILE, (
        f"bootstrap-next's RunWindow resolved to an unrecognized ARN {arn!r} -- "
        "write_load_history_definition's parameter wiring changed shape"
    )
    return _FAKE_LOAD_HISTORY_ARN_PROFILE[arn]


def _legacy_resolved_profile(command_name: str) -> str:
    """Resolve command_name's *current real* profile via whichever of the
    three legacy mechanisms actually governs it live today."""
    if command_name in _WAREHOUSE_MDM_GOLD_MEMBERS:
        return _run_warehouse_task_profile(command_name.replace("-", "_"))

    if command_name in _LOAD_HISTORY_MEMBERS:
        return _run_load_history_bootstrap_next_profile()

    workflow_name = command_name.replace("-", "_")
    profile = _resolve_workflow_profile(workflow_name)
    assert profile is not None, (
        f"{command_name!r} has no legacy resolution path -- it isn't handled "
        "by workflow_profile(), isn't in _WAREHOUSE_MDM_GOLD_MEMBERS, and "
        "isn't in _LOAD_HISTORY_MEMBERS either. Either it doesn't belong in "
        "_ALL_COMMANDS, or this test's dispatch needs updating to match a "
        "real new mechanism."
    )
    return profile


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
