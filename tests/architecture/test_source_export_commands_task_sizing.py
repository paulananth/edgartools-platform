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

Every SOURCE_EXPORT_COMMANDS member is resolved through the single
task-profile-consolidation dispatch point, ``command_task_profile()``
(.scratch/task-profile-consolidation/issues/
01-define-the-single-command-to-task-profile-source-of-truth.md) -- invoking
the real bash function directly, no duplicated case-statement logic. Before
task-profile-consolidation ticket 05 (this collapse), this file had to
reverse-engineer three independently-maintained mechanisms with no link
between them (``workflow_profile()``'s case statement,
``write_warehouse_mdm_gold_definition``'s hardcoded params, and
``bootstrap-next``'s own special case) -- see git history for that shape if
useful context, but it no longer reflects the current dispatch architecture:
tickets 01-04 collapsed all three onto ``command_task_profile()``, so there
is exactly one place task-profile resolution logic lives, and every
SOURCE_EXPORT_COMMANDS member (all 7 are members of ticket 01's mapping) is
resolved the same simple way.

The floor is today's actual minimum across every SOURCE_EXPORT_COMMANDS
member's real resolved profile -- not an aspirational value. Bump
GOLD_BUILD_MEMORY_FLOOR_MB whenever that minimum changes so this test keeps
enforcing the current floor. As of this collapse (2026-08-19), all 7 members
resolve to "large" (8192MB) -- raised from a stale 4096MB (see git history:
the previous 4096MB value predates bootstrap-next's 2026-08-10 bump to large,
and this test's floor assertion's `>=` never caught the drift because 8192MB
already cleared 4096MB either way).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from edgar_warehouse.application.warehouse_orchestrator import SOURCE_EXPORT_COMMANDS

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "infra" / "scripts" / "deploy-aws-application.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")

# today's actual minimum memory (MB) across every SOURCE_EXPORT_COMMANDS
# member's real resolved profile -- all 7 resolve to "large" (8192MB) as of
# this collapse (task-profile-consolidation ticket 05). See module docstring.
GOLD_BUILD_MEMORY_FLOOR_MB = 8192

_TASK_DEF_MEMORY_PATTERN = re.compile(
    r'register_task_definition\s+(\S+)\s+\d+\s+(\d+)'
)

_COMMAND_TASK_PROFILE_START = "command_task_profile() {\n"
_COMMAND_TASK_PROFILE_END = "\n}\n"


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


def _resolve_command_task_profile(command_name: str) -> str:
    """Invoke the real command_task_profile() bash function -- the single
    task-profile-consolidation dispatch point every SOURCE_EXPORT_COMMANDS
    member now resolves through."""
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
        f"command_task_profile({command_name!r}) failed -- {command_name!r} is in "
        "SOURCE_EXPORT_COMMANDS but has no case in command_task_profile() "
        "(infra/scripts/deploy-aws-application.sh). Add one, or if this command's "
        "task sizing is intentionally not part of the shared mapping, that's a "
        "task-profile-consolidation regression worth investigating, not something "
        f"to route around here (stdout={result.stdout!r} stderr={result.stderr!r})"
    )
    return result.stdout.strip()


def _gold_affecting_command_memory_mb() -> dict[str, int]:
    profile_memory = _profile_memory_mb()
    resolved: dict[str, int] = {}
    for command_name in SOURCE_EXPORT_COMMANDS:
        profile = _resolve_command_task_profile(command_name)
        assert profile in profile_memory, (
            f"{command_name!r} resolves to unknown profile {profile!r} -- "
            "add it to register_task_definition or update this test's expectations"
        )
        resolved[command_name] = profile_memory[profile]
    return resolved


def test_every_gold_affecting_command_has_a_resolvable_task_memory() -> None:
    """Every SOURCE_EXPORT_COMMANDS member must resolve to a known task
    memory through command_task_profile(). A new gold-affecting command
    command_task_profile() has no case for is exactly the silent-drift gap
    this ticket closes."""
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
