"""Verifies deploy-aws-application.sh's off-by-default EventBridge schedule
controls for daily_incremental (release-readiness ticket 45/49): --configure-
daily-incremental-schedule enable|disable.

Generates the real configure_daily_incremental_schedule() /
build_daily_incremental_targets_json() bash functions (same extract-and-run
driver mechanism as tests/architecture/test_daily_identity_refresh_state_
machine.py), with a fake aws_cli stub that captures every invocation instead
of calling AWS, and asserts:

- enable creates/updates two EventBridge rules -- Daily Identity Refresh
  (Mon-Sat, refresh_mode=daily) and Identity Backstop Sweep (Sun,
  refresh_mode=backstop) -- both at 12:00 UTC, both targeting the
  deterministic daily_incremental state machine ARN via the given scheduler
  role.
- EventBridge's day-of-week cron form is used correctly ('?' on
  day-of-month, since day-of-week is explicit).
- disable removes targets and deletes both rules when they exist, and is a
  clean no-op (no delete/remove calls) when they don't.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "infra" / "scripts" / "deploy-aws-application.sh"

_FN_START = "build_daily_incremental_targets_json() {\n"
# _FN_END_ANCHOR is used only to *locate* the end of
# configure_daily_incremental_schedule -- "<closing brace>, blank line,
# if-guard" is unique in the file, unlike the bare "if ! is_empty
# ...CONFIGURE_DAILY_INCREMENTAL_SCHEDULE..." guard text alone (that also
# opens the earlier CLI-argument validation block; the validation block's
# occurrence is preceded by "fi\n", never "}\n\n", so requiring the closing
# brace immediately before disambiguates the two regardless of file order --
# code-review finding, 2026-07-30). Only _FN_END_INCLUDE (the closing brace
# itself) is actually kept in the extracted source -- the guard's own body
# (the function call + exit 0 + fi) is deliberately excluded, or the
# extracted fragment would end in a dangling, unterminated `if` and fail to
# parse when sourced on its own.
_FN_END_ANCHOR = '\n}\n\nif ! is_empty "$CONFIGURE_DAILY_INCREMENTAL_SCHEDULE"; then'
_FN_END_INCLUDE = "\n}"

_FAKE_ROLE_ARN = "arn:aws:iam::690839588395:role/edgartools-prod-daily-incremental-scheduler"
_FAKE_STATE_MACHINE_ARN = (
    "arn:aws:states:us-east-1:690839588395:stateMachine:edgartools-prod-daily-incremental"
)

_CALL_SEP = "---CALL---"


def _extract_function_source() -> str:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = text.index(_FN_START)
    anchor_pos = text.index(_FN_END_ANCHOR, start)
    end = anchor_pos + len(_FN_END_INCLUDE)
    return text[start:end]


def _run(action: str, *, rule_exists: bool) -> list[list[str]]:
    """Runs configure_daily_incremental_schedule(action, role_arn) with a fake
    aws_cli that records every call's argv (one call per line-group, separated
    by _CALL_SEP) instead of hitting AWS. Returns the parsed list of calls."""
    fn_source = _extract_function_source()
    tmp_root = REPO_ROOT / ".pytest_cache" / "daily_incremental_schedule_controls_test"
    tmp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=tmp_root) as d:
        tmp_path = Path(d)
        fn_file = tmp_path / "schedule_fns.sh"
        fn_file.write_text(fn_source, encoding="utf-8")
        capture_file = tmp_path / "calls.txt"

        driver = tmp_path / "driver.sh"
        driver.write_text(
            "set -euo pipefail\n"
            'AWS_REGION_NAME="us-east-1"\n'
            'ACCOUNT_ID="690839588395"\n'
            'NAME_PREFIX="edgartools-prod"\n'
            f'CAPTURE_FILE="{capture_file.as_posix()}"\n'
            f'FAKE_RULE_EXISTS="{"true" if rule_exists else "false"}"\n'
            "log() { :; }\n"
            "aws_cli() {\n"
            '  if [[ "$1" == "events" && "$2" == "describe-rule" ]]; then\n'
            '    [[ "$FAKE_RULE_EXISTS" == "true" ]] && return 0 || return 1\n'
            "  fi\n"
            "  {\n"
            '    for arg in "$@"; do printf \'%s\\n\' "$arg"; done\n'
            f"    printf '%s\\n' '{_CALL_SEP}'\n"
            '  } >> "$CAPTURE_FILE"\n'
            "  return 0\n"
            "}\n"
            f'source "{fn_file.as_posix()}"\n'
            f'configure_daily_incremental_schedule "{action}" "{_FAKE_ROLE_ARN}"\n',
            encoding="utf-8",
        )

        result = subprocess.run(
            ["bash", driver.as_posix()], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise AssertionError(
                f"configure_daily_incremental_schedule({action!r}) failed:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        if not capture_file.exists():
            return []
        lines = capture_file.read_text(encoding="utf-8").splitlines()
        calls: list[list[str]] = []
        current: list[str] = []
        for line in lines:
            if line == _CALL_SEP:
                calls.append(current)
                current = []
            else:
                current.append(line)
        return calls


def _arg_value(call: list[str], flag: str) -> str:
    return call[call.index(flag) + 1]


def _calls_matching(calls: list[list[str]], *prefix: str) -> list[list[str]]:
    return [c for c in calls if c[: len(prefix)] == list(prefix)]


def test_enable_creates_daily_rule_with_correct_cron_and_payload() -> None:
    calls = _run("enable", rule_exists=False)
    put_rule_calls = _calls_matching(calls, "events", "put-rule")
    daily_put_rule = next(
        c for c in put_rule_calls if _arg_value(c, "--name") == "edgartools-prod-daily-incremental-refresh"
    )
    assert _arg_value(daily_put_rule, "--schedule-expression") == "cron(0 12 ? * MON-SAT *)"
    assert _arg_value(daily_put_rule, "--state") == "ENABLED"

    put_targets_calls = _calls_matching(calls, "events", "put-targets")
    daily_put_targets = next(
        c for c in put_targets_calls if _arg_value(c, "--rule") == "edgartools-prod-daily-incremental-refresh"
    )
    targets = json.loads(_arg_value(daily_put_targets, "--targets"))
    assert len(targets) == 1
    assert targets[0]["Arn"] == _FAKE_STATE_MACHINE_ARN
    assert targets[0]["RoleArn"] == _FAKE_ROLE_ARN
    assert json.loads(targets[0]["Input"]) == {"refresh_mode": "daily"}


def test_enable_creates_backstop_rule_with_correct_cron_and_payload() -> None:
    calls = _run("enable", rule_exists=False)
    put_rule_calls = _calls_matching(calls, "events", "put-rule")
    backstop_put_rule = next(
        c for c in put_rule_calls if _arg_value(c, "--name") == "edgartools-prod-daily-incremental-backstop"
    )
    assert _arg_value(backstop_put_rule, "--schedule-expression") == "cron(0 12 ? * SUN *)"
    assert _arg_value(backstop_put_rule, "--state") == "ENABLED"

    put_targets_calls = _calls_matching(calls, "events", "put-targets")
    backstop_put_targets = next(
        c for c in put_targets_calls if _arg_value(c, "--rule") == "edgartools-prod-daily-incremental-backstop"
    )
    targets = json.loads(_arg_value(backstop_put_targets, "--targets"))
    assert len(targets) == 1
    assert targets[0]["Arn"] == _FAKE_STATE_MACHINE_ARN
    assert targets[0]["RoleArn"] == _FAKE_ROLE_ARN
    assert json.loads(targets[0]["Input"]) == {"refresh_mode": "backstop"}


def test_disable_removes_targets_and_deletes_both_rules_when_present() -> None:
    calls = _run("disable", rule_exists=True)
    delete_rule_names = {_arg_value(c, "--name") for c in _calls_matching(calls, "events", "delete-rule")}
    assert delete_rule_names == {
        "edgartools-prod-daily-incremental-refresh",
        "edgartools-prod-daily-incremental-backstop",
    }
    remove_targets_rules = {
        _arg_value(c, "--rule") for c in _calls_matching(calls, "events", "remove-targets")
    }
    assert remove_targets_rules == {
        "edgartools-prod-daily-incremental-refresh",
        "edgartools-prod-daily-incremental-backstop",
    }


def test_disable_is_a_clean_noop_when_rules_do_not_exist() -> None:
    """No delete-rule/remove-targets calls when describe-rule reports the rules
    already don't exist -- disable must not fail on an already-disabled schedule."""
    calls = _run("disable", rule_exists=False)
    assert _calls_matching(calls, "events", "delete-rule") == []
    assert _calls_matching(calls, "events", "remove-targets") == []


@pytest.mark.parametrize("rule_name", [
    "edgartools-prod-daily-incremental-refresh",
    "edgartools-prod-daily-incremental-backstop",
])
def test_enable_and_disable_use_the_same_rule_names(rule_name: str) -> None:
    """The rule names put-rule creates on enable must be exactly what
    delete-rule/remove-targets target on disable, or a disable after an
    enable would silently leave the enabled rule running."""
    enable_calls = _run("enable", rule_exists=False)
    disable_calls = _run("disable", rule_exists=True)
    enabled_names = {_arg_value(c, "--name") for c in _calls_matching(enable_calls, "events", "put-rule")}
    disabled_names = {_arg_value(c, "--name") for c in _calls_matching(disable_calls, "events", "delete-rule")}
    assert rule_name in enabled_names
    assert rule_name in disabled_names
