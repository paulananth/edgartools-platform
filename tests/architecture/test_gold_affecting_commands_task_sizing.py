"""Cross-check GOLD_AFFECTING_COMMANDS against ECS task-profile memory sizing.

Resolves the wayfinder ticket "Link GOLD_AFFECTING_COMMANDS membership to
required task-profile sizing" (.scratch/gold-build-memory-reliability/
issues/02-link-gold-affecting-commands-to-task-sizing.md).

edgar_warehouse.application.warehouse_orchestrator.GOLD_AFFECTING_COMMANDS and
infra/scripts/deploy-aws-application.sh's workflow_profile() are two
independent collections with no link between them -- this is exactly why
daily_incremental reproduced an OOM that gold-refresh had already hit and
gotten a dedicated fix for (commit 37c3171): adding a command to the first
doesn't flag that the second needs revisiting too.

This test invokes the real workflow_profile() bash function (no duplicated/
hand-maintained copy of its case statement, mirroring
test_daily_incremental_state_machine.py's approach) for every
GOLD_AFFECTING_COMMANDS member and asserts its resolved task profile's memory
meets GOLD_BUILD_MEMORY_FLOOR_MB. bootstrap-next is a documented exception:
it's the one member never passed to workflow_profile() at all -- inside the
load_history state machine it's hardcoded straight to the medium task
definition ARN (write_load_history_definition's wh_task_medium_arn parameter,
"per-window bootstrap-next/-fundamentals").

The floor is today's actual minimum (medium/large both currently 4096MB) --
not an aspirational value. Ticket 03 (a separate, still-open HITL decision)
is where that floor should actually be raised; when it lands, bump
GOLD_BUILD_MEMORY_FLOOR_MB here to match so this test keeps enforcing the new
minimum.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from edgar_warehouse.application.warehouse_orchestrator import GOLD_AFFECTING_COMMANDS

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "infra" / "scripts" / "deploy-aws-application.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")

# today's actual minimum memory (MB) across every GOLD_AFFECTING_COMMANDS
# member's resolved profile -- see module docstring for why this isn't the
# aspirational "large" floor yet.
GOLD_BUILD_MEMORY_FLOOR_MB = 4096

# bootstrap-next is never passed to workflow_profile() -- it's hardcoded to
# the medium task definition ARN inside write_load_history_definition (the
# only state machine that ever runs it). Verified live: no "bootstrap_next"
# state machine and no workflow_profile() case exist for it at all.
#
# Mapped to the *name* of the profile it's actually wired to, not a literal
# memory number -- resolved against _profile_memory_mb() below so that if
# medium's registered memory changes, this exception tracks it instead of
# silently going stale itself (the exact drift this ticket exists to catch).
_SPECIAL_CASED_PROFILE = {
    "bootstrap-next": "medium",
}

_TASK_DEF_MEMORY_PATTERN = re.compile(
    r'register_task_definition\s+(\S+)\s+\d+\s+(\d+)'
)

_START_MARKER = "workflow_profile() {\n"
_END_MARKER = "\n}\n"


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


def _extract_workflow_profile_source() -> str:
    text = _script_text()
    start = text.index(_START_MARKER)
    end = text.index(_END_MARKER, start) + len(_END_MARKER)
    return text[start:end]


def _resolve_profile(workflow_name: str) -> str | None:
    """Invoke the real workflow_profile() bash function. None if unmapped."""
    fn_source = _extract_workflow_profile_source()
    script = f'set -euo pipefail\n{fn_source}\nworkflow_profile "{workflow_name}"\n'
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _gold_affecting_command_memory_mb() -> dict[str, int]:
    profile_memory = _profile_memory_mb()
    resolved: dict[str, int] = {}
    for command_name in GOLD_AFFECTING_COMMANDS:
        workflow_name = command_name.replace("-", "_")
        profile = _resolve_profile(workflow_name)
        if profile is not None:
            assert profile in profile_memory, (
                f"{command_name!r} resolves to unknown profile {profile!r} -- "
                "add it to register_task_definition or update this test's expectations"
            )
            resolved[command_name] = profile_memory[profile]
            continue
        assert command_name in _SPECIAL_CASED_PROFILE, (
            f"{command_name!r} is in GOLD_AFFECTING_COMMANDS but workflow_profile() "
            f"has no case for {workflow_name!r}, and it isn't in this test's "
            "_SPECIAL_CASED_PROFILE allowlist either. Either add a case to "
            "workflow_profile() in infra/scripts/deploy-aws-application.sh, or if "
            "this command's task sizing is intentionally wired some other way "
            "(like bootstrap-next), document it in _SPECIAL_CASED_PROFILE with "
            "a comment explaining where its real memory comes from."
        )
        special_profile = _SPECIAL_CASED_PROFILE[command_name]
        assert special_profile in profile_memory, (
            f"{command_name!r}'s _SPECIAL_CASED_PROFILE entry {special_profile!r} "
            "isn't a known register_task_definition profile"
        )
        resolved[command_name] = profile_memory[special_profile]
    return resolved


def test_every_gold_affecting_command_has_a_resolvable_task_memory() -> None:
    """Every GOLD_AFFECTING_COMMANDS member must resolve to a known task
    memory -- either through workflow_profile() or the documented
    _SPECIAL_CASED_PROFILE exception. A new gold-affecting command with
    neither is exactly the silent-drift gap this ticket closes."""
    resolved = _gold_affecting_command_memory_mb()
    assert set(resolved.keys()) == GOLD_AFFECTING_COMMANDS


@pytest.mark.parametrize("command_name", sorted(GOLD_AFFECTING_COMMANDS))
def test_gold_affecting_command_meets_memory_floor(command_name: str) -> None:
    """Every command that calls build_gold() must run on a task with at
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
