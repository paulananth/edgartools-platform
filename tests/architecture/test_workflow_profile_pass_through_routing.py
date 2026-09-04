"""Proves workflow_profile() is genuinely a *pass-through* onto
command_task_profile() at runtime, not an independent case statement that
happens to agree with it.

Resolves task-profile-consolidation wayfinder map ticket 04
(.scratch/task-profile-consolidation/issues/
04-retire-workflow-profile-dead-cases.md). Before this ticket,
workflow_profile() held its own case statement (including two genuinely dead
cases for "daily_incremental"/"bootstrap") independently maintained from
command_task_profile() -- exactly the kind of silent-drift risk this whole
effort exists to close. workflow_profile() is now a one-line delegation:
``command_task_profile "${1//_/-}"``.

Mirrors test_bootstrap_next_task_profile_routing.py /
test_run_warehouse_task_profile_routing.py's technique: source the real
command_task_profile() first, then workflow_profile(), then *redefine*
command_task_profile() with a stub -- bash resolves function calls at call
time, so the later redefinition genuinely intercepts what workflow_profile()
calls internally. If workflow_profile() still had independent logic, the
stub would have nothing to intercept and this test would fail.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "infra" / "scripts" / "deploy-aws-application.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")

_COMMAND_TASK_PROFILE_START = "command_task_profile() {\n"
_COMMAND_TASK_PROFILE_END = "\n}\n"

_WORKFLOW_PROFILE_START = "workflow_profile() {\n"
_WORKFLOW_PROFILE_END = "\n}\n"


def _script_text() -> str:
    return DEPLOY_SCRIPT.read_text(encoding="utf-8")


def _extract_function_source(start_marker: str, end_marker: str) -> str:
    text = _script_text()
    start = text.index(start_marker)
    end = text.index(end_marker, start) + len(end_marker)
    return text[start:end]


def _run_workflow_profile(
    workflow_name: str, command_task_profile_override: str | None
) -> subprocess.CompletedProcess[str]:
    """Invoke the real workflow_profile() bash function, optionally with
    command_task_profile() redefined *after* workflow_profile() is already
    sourced -- a later definition wins at call time in bash, so this
    genuinely intercepts whatever workflow_profile() calls internally."""
    command_task_profile_source = _extract_function_source(
        _COMMAND_TASK_PROFILE_START, _COMMAND_TASK_PROFILE_END
    )
    workflow_profile_source = _extract_function_source(
        _WORKFLOW_PROFILE_START, _WORKFLOW_PROFILE_END
    )

    script_parts = [
        "set -euo pipefail",
        'fail() { echo "ERROR: $*" >&2; exit 1; }',
        command_task_profile_source,
        workflow_profile_source,
    ]
    if command_task_profile_override is not None:
        script_parts.append(command_task_profile_override)
    script_parts.append(f'workflow_profile "{workflow_name}"\n')

    return subprocess.run(
        ["bash", "-c", "\n".join(script_parts)],
        capture_output=True,
        text=True,
        timeout=10,
    )


@pytest.mark.parametrize(
    ("workflow_name", "expected_profile"),
    [
        ("bootstrap_full", "large"),
        ("targeted_resync", "large"),
        ("load_daily_form_index_for_date", "small"),
        ("catch_up_daily_form_index", "small"),
        ("gold_refresh", "large"),
        ("seed_universe", "medium"),
    ],
)
def test_workflow_profile_uses_real_command_task_profile_result(
    workflow_name: str, expected_profile: str
) -> None:
    """With the real, unmodified command_task_profile(), workflow_profile()
    must answer exactly what command_task_profile() answers for the
    equivalent hyphenated command name."""
    result = _run_workflow_profile(workflow_name, command_task_profile_override=None)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert result.stdout.strip() == expected_profile


@pytest.mark.parametrize(
    ("workflow_name", "real_command_name"),
    [
        ("bootstrap_full", "bootstrap-full"),
        ("load_daily_form_index_for_date", "load-daily-form-index-for-date"),
        ("seed_universe", "seed-universe"),
    ],
)
def test_workflow_profile_genuinely_routes_through_command_task_profile(
    workflow_name: str, real_command_name: str
) -> None:
    """Overriding command_task_profile() to answer a distinguishable value
    for this workflow's real hyphenated command name -- after
    workflow_profile()'s real body is already sourced -- must flip
    workflow_profile()'s own answer to match. If this fails, workflow_profile()
    is NOT genuinely delegating at runtime -- it still holds independent
    logic the override had nothing to intercept."""
    override = (
        'command_task_profile() {\n'
        f'  case "$1" in\n'
        f'    {real_command_name}) printf "%s\\n" "stubbed-value" ;;\n'
        '    *) fail "unexpected command_task_profile call: $1" ;;\n'
        '  esac\n'
        '}\n'
    )
    result = _run_workflow_profile(workflow_name, command_task_profile_override=override)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert result.stdout.strip() == "stubbed-value", (
        f"workflow_profile({workflow_name!r}) resolved to {result.stdout.strip()!r} even "
        f"with command_task_profile() stubbed to answer 'stubbed-value' for "
        f"{real_command_name!r} -- workflow_profile() is not genuinely routing through "
        "command_task_profile() at call time."
    )


@pytest.mark.parametrize(
    ("workflow_name", "real_command_name"),
    [
        ("bootstrap_full", "bootstrap-full"),
        ("catch_up_daily_form_index", "catch-up-daily-form-index"),
    ],
)
def test_workflow_profile_translates_underscores_to_the_exact_hyphenated_command_name(
    workflow_name: str, real_command_name: str
) -> None:
    """workflow_profile() must call command_task_profile() with exactly the
    real hyphenated CLI command name -- a stub that fails on anything else
    must still let resolution succeed."""
    strict_stub = (
        'command_task_profile() {\n'
        f'  if [ "$1" != "{real_command_name}" ]; then\n'
        f'    fail "expected command_task_profile to be called with exactly '
        f"'{real_command_name}', got: $1\"\n"
        '  fi\n'
        '  printf "%s\\n" "ok"\n'
        '}\n'
    )
    result = _run_workflow_profile(workflow_name, command_task_profile_override=strict_stub)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert result.stdout.strip() == "ok"


def test_workflow_profile_fails_closed_on_unknown_workflow() -> None:
    """An unmapped workflow name must still fail loudly (propagated from
    command_task_profile()'s own fail-closed default case), not silently
    default to a profile -- ticket 04's own acceptance bar for what
    "no independent case statement" must still guarantee."""
    result = _run_workflow_profile("not-a-real-workflow", command_task_profile_override=None)
    assert result.returncode != 0


def test_workflow_profile_has_no_case_statement_of_its_own() -> None:
    """workflow_profile()'s body must be a one-line delegation -- no `case`
    keyword anywhere in its extracted source. A regression here means
    someone re-added independent profile-resolution logic, exactly the
    drift ticket 04 closes."""
    fn_source = _extract_function_source(_WORKFLOW_PROFILE_START, _WORKFLOW_PROFILE_END)
    assert "case " not in fn_source, (
        f"workflow_profile() still contains a case statement:\n{fn_source}\n"
        "-- it must be a thin pass-through onto command_task_profile()."
    )
    assert "command_task_profile" in fn_source
