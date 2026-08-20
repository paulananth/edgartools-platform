"""Cross-check SOURCE_EXPORT_COMMANDS against ECS task-profile memory sizing.

Resolves the wayfinder ticket "Link SOURCE_EXPORT_COMMANDS membership to
required task-profile sizing" (.scratch/gold-build-memory-reliability/
issues/02-link-gold-affecting-commands-to-task-sizing.md).

edgar_warehouse.application.warehouse_orchestrator.SOURCE_EXPORT_COMMANDS and
infra/scripts/deploy-aws-application.sh's task-sizing are independent, with no
link between them -- this is exactly why daily_incremental reproduced an OOM
that gold-refresh had already hit and gotten a dedicated fix for (commit
37c3171): adding a command to the first doesn't flag that the second needs
revisiting too.

Every SOURCE_EXPORT_COMMANDS member is resolved through its *real* dispatch
mechanism, not a single assumed one -- there turn out to be three:

1. `bootstrap-full`, `targeted-resync`, `full-reconcile`, `gold-refresh`
   (standalone): their own state machine is built by workflow_profile()'s
   case statement (the loop at deploy-aws-application.sh:~3098). Resolved by
   invoking the real bash function -- no duplicated case-statement logic.
2. `bootstrap`, `daily-incremental`: workflow_profile() has cases for these
   two, but they are DEAD CODE -- workflow_profile() is never called with
   these names anywhere in the script. Their actual RunWarehouseTask step
   (the one that runs `bootstrap`/`daily-incremental` themselves, i.e. the
   step that OOM'd in prod) is built directly by
   write_warehouse_mdm_gold_definition, which takes the medium/large ARNs as
   plain parameters. Resolved by generating that function's real state
   machine JSON (mirroring test_daily_incremental_state_machine.py's
   approach) and reading RunWarehouseTask's actual TaskDefinition.
3. `bootstrap-next`: never passed to workflow_profile() at all. Its deployed
   load_history path explicitly uses `--silver-only`, so it no longer
   executes the gold-affecting portion of the command there. The
   special-case below remains a guard on that real wiring;
   test_load_history_state_machine separately proves the policy flag is
   present.

The floor is today's actual minimum across all three paths -- not an
aspirational value. Bump GOLD_BUILD_MEMORY_FLOOR_MB whenever that minimum
changes so this test keeps enforcing the current floor.

CORRECTION (2026-08-19, found while implementing task-profile-consolidation
ticket 03): `_SPECIAL_CASED_PROFILE["bootstrap-next"]` was wrongly "medium"
-- stale since 2026-08-10, when the real load_history wiring was bumped to
`wh_large_arn` after a live exit-137 OOM on medium (see
test_load_history_state_machine.py's
test_windowed_bootstrap_uses_large_task_definition). This test's own floor
assertion (`>=` GOLD_BUILD_MEMORY_FLOOR_MB) never caught the drift because
large's 8192MB still cleared the 4096MB floor either way -- the wrong value
was silently harmless *here*, even though it would have been actively
harmful if task-profile-consolidation/task_profile_source_of_truth.py had
copied it uncritically (which it initially did, from this exact assumption,
before being independently corrected -- see that file's module docstring).
Now "large", matching live wiring. Separately: with all 7 SOURCE_EXPORT_COMMANDS
members now resolving to "large" (8192MB), "today's actual minimum" is
technically 8192MB, not the 4096MB GOLD_BUILD_MEMORY_FLOOR_MB still encodes
-- flagged, not bumped here, since raising the floor is a deliberate
tightening decision (not a correctness bug: `>=` still holds), left to
whoever next revisits this file or ticket 05's collapse.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from edgar_warehouse.application.warehouse_orchestrator import SOURCE_EXPORT_COMMANDS

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "infra" / "scripts" / "deploy-aws-application.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")

# today's actual minimum memory (MB) across every SOURCE_EXPORT_COMMANDS
# member's real resolved profile.
GOLD_BUILD_MEMORY_FLOOR_MB = 4096

# Commands whose RunWarehouseTask step is built directly by
# write_warehouse_mdm_gold_definition -- workflow_profile() is never called
# for these (see module docstring, path 2).
_WAREHOUSE_MDM_GOLD_MEMBERS = {"bootstrap", "daily-incremental"}

# bootstrap-next is never passed to workflow_profile() and never built by
# write_warehouse_mdm_gold_definition -- its deployed load_history invocation
# is hardcoded to large and explicitly silver-only (see module docstring,
# path 3 and test_load_history_state_machine.py). Corrected 2026-08-19 --
# was wrongly "medium" (see module docstring's CORRECTION note).
#
# Mapped to the profile actually wired so the architecture inventory remains
# complete. Its gold path is disabled at that call site; this floor assertion
# proves even a policy regression would retain the current safety floor
# while the generated-workflow test catches the regression.
_SPECIAL_CASED_PROFILE = {
    "bootstrap-next": "large",
}

_TASK_DEF_MEMORY_PATTERN = re.compile(
    r'register_task_definition\s+(\S+)\s+\d+\s+(\d+)'
)

_WORKFLOW_PROFILE_START = "workflow_profile() {\n"
_WORKFLOW_PROFILE_END = "\n}\n"

_WMG_START = "write_warehouse_mdm_gold_definition() {\n"
_WMG_END = "\nPY\n}\n"

# write_warehouse_mdm_gold_definition now calls command_task_profile()
# internally (task-profile-consolidation ticket 02) to resolve
# RunWarehouseTask's profile -- extracted and sourced alongside it below.
_COMMAND_TASK_PROFILE_START = "command_task_profile() {\n"
_COMMAND_TASK_PROFILE_END = "\n}\n"

# Fake ARNs passed into write_warehouse_mdm_gold_definition's medium/large
# parameters -- distinguishable strings so the generated JSON's
# RunWarehouseTask.Parameters.TaskDefinition tells us which one was used.
_FAKE_MEDIUM_ARN = "arn:fake-wh-medium"
_FAKE_LARGE_ARN = "arn:fake-wh-large"
_FAKE_ARN_PROFILE = {_FAKE_MEDIUM_ARN: "medium", _FAKE_LARGE_ARN: "large"}


def _script_text() -> str:
    return DEPLOY_SCRIPT.read_text(encoding="utf-8")


def _profile_memory_mb() -> dict[str, int]:
    """{profile_name: memory_mb} from the literal register_task_definition calls."""
    text = _script_text()
    memory = {name: int(mb) for name, mb in _TASK_DEF_MEMORY_PATTERN.findall(text)}
    assert {"small", "medium", "large"} <= memory.keys(), (
        "expected small/medium/large register_task_definition calls not found -- "
        "deploy-aws-application.sh's task-profile registration shape changed"
    )
    return memory


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


def _run_warehouse_task_profile(workflow_name: str) -> str:
    """Generate the real write_warehouse_mdm_gold_definition() state machine
    JSON for workflow_name and return which profile its RunWarehouseTask step
    -- the one that actually runs `bootstrap`/`daily-incremental` themselves
    -- resolves to. write_warehouse_mdm_gold_definition now calls
    command_task_profile() internally (task-profile-consolidation ticket 02),
    so that function's source must be sourced first too."""
    fn_source = _extract_function_source(_WMG_START, _WMG_END)
    command_task_profile_source = _extract_function_source(
        _COMMAND_TASK_PROFILE_START, _COMMAND_TASK_PROFILE_END
    )

    tmp_root = REPO_ROOT / ".pytest_cache" / "gold_affecting_task_sizing_test"
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


def _gold_affecting_command_memory_mb() -> dict[str, int]:
    profile_memory = _profile_memory_mb()
    resolved: dict[str, int] = {}
    for command_name in SOURCE_EXPORT_COMMANDS:
        workflow_name = command_name.replace("-", "_")

        if command_name in _WAREHOUSE_MDM_GOLD_MEMBERS:
            profile = _run_warehouse_task_profile(workflow_name)
            resolved[command_name] = profile_memory[profile]
            continue

        profile = _resolve_workflow_profile(workflow_name)
        if profile is not None:
            assert profile in profile_memory, (
                f"{command_name!r} resolves to unknown profile {profile!r} -- "
                "add it to register_task_definition or update this test's expectations"
            )
            resolved[command_name] = profile_memory[profile]
            continue

        assert command_name in _SPECIAL_CASED_PROFILE, (
            f"{command_name!r} is in SOURCE_EXPORT_COMMANDS but workflow_profile() "
            f"has no case for {workflow_name!r}, it isn't in _WAREHOUSE_MDM_GOLD_MEMBERS, "
            "and it isn't in this test's _SPECIAL_CASED_PROFILE allowlist either. Either "
            "add a case to workflow_profile() in infra/scripts/deploy-aws-application.sh "
            "(and confirm it's actually *called* for this workflow, not dead code -- see "
            "module docstring), or if this command's task sizing is intentionally wired "
            "some other way (like bootstrap-next), document it in _SPECIAL_CASED_PROFILE "
            "with a comment explaining where its real memory comes from."
        )
        special_profile = _SPECIAL_CASED_PROFILE[command_name]
        assert special_profile in profile_memory, (
            f"{command_name!r}'s _SPECIAL_CASED_PROFILE entry {special_profile!r} "
            "isn't a known register_task_definition profile"
        )
        resolved[command_name] = profile_memory[special_profile]
    return resolved


def test_every_gold_affecting_command_has_a_resolvable_task_memory() -> None:
    """Every SOURCE_EXPORT_COMMANDS member must resolve to a known task
    memory through one of its three real dispatch paths (see module
    docstring). A new gold-affecting command matching none of them is
    exactly the silent-drift gap this ticket closes."""
    resolved = _gold_affecting_command_memory_mb()
    assert set(resolved.keys()) == SOURCE_EXPORT_COMMANDS


@pytest.mark.parametrize("command_name", sorted(SOURCE_EXPORT_COMMANDS))
def test_gold_affecting_command_meets_memory_floor(command_name: str) -> None:
    """Every command that calls build_source_export() must run on a task with at
    least GOLD_BUILD_MEMORY_FLOOR_MB -- catches both a new command silently
    landing on an under-provisioned profile, and an existing profile's
    memory being lowered below what gold-affecting commands need."""
    resolved = _gold_affecting_command_memory_mb()
    memory_mb = resolved[command_name]
    assert memory_mb >= GOLD_BUILD_MEMORY_FLOOR_MB, (
        f"{command_name!r} resolves to only {memory_mb}MB, below the "
        f"{GOLD_BUILD_MEMORY_FLOOR_MB}MB floor gold-affecting commands need "
        "(see .scratch/gold-build-memory-reliability/issues/"
        "02-link-gold-affecting-commands-to-task-sizing.md)"
    )
