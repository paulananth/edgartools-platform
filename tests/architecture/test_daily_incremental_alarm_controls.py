"""Contract tests for explicit daily identity refresh alarm controls."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "infra" / "scripts" / "deploy-aws-application.sh"
_START = "require_confirmed_operator_alert_topic() {\n"
_END = '\n}\n\nif ! is_empty "$CONFIGURE_DAILY_INCREMENTAL_ALARMS"; then'
_CALL_SEP = "---CALL---"
_TOPIC_ARN = "arn:aws:sns:us-east-1:690839588395:edgartools-prod-operator-alerts"


def _extract_function_source() -> str:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = text.index(_START)
    end = text.index(_END, start) + 2
    return text[start:end]


def _run(action: str, *, confirmed_subscriptions: int = 1) -> list[list[str]]:
    tmp_root = REPO_ROOT / ".pytest_cache" / "daily_incremental_alarm_controls_test"
    tmp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=tmp_root) as directory:
        tmp_path = Path(directory)
        fn_file = tmp_path / "alarm_fn.sh"
        fn_file.write_text(_extract_function_source(), encoding="utf-8")
        capture_file = tmp_path / "calls.txt"
        driver = tmp_path / "driver.sh"
        driver.write_text(
            "set -euo pipefail\n"
            'AWS_REGION_NAME="us-east-1"\n'
            'ACCOUNT_ID="690839588395"\n'
            'NAME_PREFIX="edgartools-prod"\n'
            f'CAPTURE_FILE="{capture_file.as_posix()}"\n'
            "log() { :; }\n"
            "fail() { printf 'ERROR: %s\\n' \"$*\" >&2; return 1; }\n"
            "aws_cli() {\n"
            '  if [[ "$1" == "sns" && "$2" == "list-subscriptions-by-topic" ]]; then\n'
            f"    printf '%s\\n' '{confirmed_subscriptions}'\n"
            "    return 0\n"
            "  fi\n"
            "  { for arg in \"$@\"; do printf '%s\\n' \"$arg\"; done; "
            f"printf '%s\\n' '{_CALL_SEP}'; }} >> \"$CAPTURE_FILE\"\n"
            "}\n"
            f'source "{fn_file.as_posix()}"\n'
            f'configure_daily_incremental_alarms "{action}" "{_TOPIC_ARN}"\n',
            encoding="utf-8",
        )
        result = subprocess.run(["bash", driver.as_posix()], capture_output=True, text=True)
        if confirmed_subscriptions == 0 and action == "enable":
            assert result.returncode != 0
            assert "at least one confirmed subscription" in result.stderr
            return []
        assert result.returncode == 0, result.stderr
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


def _arg(call: list[str], name: str) -> str:
    return call[call.index(name) + 1]


def test_enable_creates_the_timeout_alarm() -> None:
    calls = [call for call in _run("enable") if call[:2] == ["cloudwatch", "put-metric-alarm"]]
    assert {_arg(call, "--alarm-name") for call in calls} == {
        "edgartools-prod-daily-incremental-timeout",
    }
    by_name = {_arg(call, "--alarm-name"): call for call in calls}
    timeout = by_name["edgartools-prod-daily-incremental-timeout"]
    assert _arg(timeout, "--namespace") == "AWS/States"
    assert _arg(timeout, "--metric-name") == "ExecutionsTimedOut"
    assert _arg(timeout, "--alarm-actions") == _TOPIC_ARN
    assert (
        "Name=StateMachineArn,Value=arn:aws:states:us-east-1:690839588395:"
        "stateMachine:edgartools-prod-daily-incremental"
    ) in timeout


def test_disable_deletes_the_timeout_alarm() -> None:
    calls = [call for call in _run("disable") if call[:2] == ["cloudwatch", "delete-alarms"]]
    assert len(calls) == 1
    assert set(calls[0][calls[0].index("--alarm-names") + 1 :]) == {
        "edgartools-prod-daily-incremental-timeout",
    }


def test_enable_rejects_a_topic_without_confirmed_delivery() -> None:
    assert _run("enable", confirmed_subscriptions=0) == []


def test_step_functions_role_can_only_publish_to_the_operator_topic() -> None:
    policy = (
        REPO_ROOT / "infra/terraform/access/aws/accounts/prod/scheduled_daily_incremental.tf"
    ).read_text(encoding="utf-8")
    assert 'Action   = "sns:Publish"' in policy
    assert "Resource = local.identity_refresh_alert_topic_arn" in policy
