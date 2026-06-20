from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "infra" / "scripts" / "go-live.sh"


def run_wizard(
    *args: str,
    input_text: str = "y\n",
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    proc_env = os.environ.copy()
    proc_env.setdefault("GO_LIVE_NO_GUM", "1")
    if env:
        proc_env.update(env)
    result = subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=REPO_ROOT,
        input=input_text,
        text=True,
        capture_output=True,
        env=proc_env,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"wizard failed with {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def make_fake_tools(tmp_path: Path) -> tuple[Path, Path]:
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    call_log = tmp_path / "calls.log"
    tool = """#!/usr/bin/env bash
set -euo pipefail
echo "$(basename "$0") $*" >> "${GO_LIVE_CALL_LOG}"
case "$(basename "$0")" in
  aws)
    echo '{"Account":"123456789012","Arn":"arn:aws:iam::123456789012:user/test","UserId":"test"}'
    ;;
  snow)
    echo "snow ok"
    ;;
  terraform)
    echo "Terraform v1.6.0"
    ;;
  docker)
    echo "Docker version 25.0.0"
    ;;
  uv)
    echo "uv 0.5.0"
    ;;
esac
exit 0
"""
    for name in ("aws", "snow", "terraform", "docker", "uv"):
        path = fakebin / name
        path.write_text(tool, encoding="utf-8")
        path.chmod(0o755)
    return fakebin, call_log


def test_go_live_script_has_valid_bash_syntax() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], cwd=REPO_ROOT, check=True)


def test_default_env_is_dev_and_decline_exits_without_mutation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    result = run_wizard("plan", "--workspace", str(workspace), input_text="n\n")

    combined = result.stdout + result.stderr
    assert "selected environment: dev" in combined
    assert "Continue with selected environment dev?" in combined
    assert "Declined selected environment dev; exiting without mutation." in combined
    assert not workspace.exists()


def test_single_command_launches_tui_preview_plan(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    input_text = "\n\n\n\n\n\n\ny\n"

    result = run_wizard("--workspace", str(workspace), input_text=input_text)

    combined = result.stdout + result.stderr
    assert "EdgarTools go-live TUI" in combined
    assert "Run with one command: bash infra/scripts/go-live.sh" in combined
    assert "Select operation" in combined
    assert "AWS admin/provisioning profile" in combined
    assert "Ordered go-live plan for dev:" in combined
    assert "[preview only]" in combined
    assert not workspace.exists()


def test_tui_offers_gum_install_and_continues_with_bash_when_declined(tmp_path: Path) -> None:
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    brew_log = tmp_path / "brew.log"
    brew = fakebin / "brew"
    brew.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "${BREW_LOG}"
""",
        encoding="utf-8",
    )
    brew.chmod(0o755)
    workspace = tmp_path / "workspace"
    input_text = "n\n\n\n\n\n\n\n\ny\n"
    env = {
        "PATH": f"{fakebin}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
        "GO_LIVE_NO_GUM": "0",
        "BREW_LOG": str(brew_log),
    }

    result = run_wizard("--workspace", str(workspace), input_text=input_text, env=env)

    combined = result.stdout + result.stderr
    assert "gum is not installed" in combined
    assert "Install gum now with Homebrew?" in combined
    assert "Continuing with the plain Bash fallback." in combined
    assert "Ordered go-live plan for dev:" in combined
    assert not brew_log.exists()


def test_tui_can_install_gum_with_homebrew_and_use_it_immediately(tmp_path: Path) -> None:
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    brew_log = tmp_path / "brew.log"
    gum_log = tmp_path / "gum.log"
    brew = fakebin / "brew"
    brew.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "${{BREW_LOG}}"
cat > "{fakebin / 'gum'}" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "${{GUM_LOG}}"
case "$1" in
  choose)
    if [[ "$*" == *"Select operation"* ]]; then
      echo "plan"
    elif [[ "$*" == *"Select environment"* ]]; then
      echo "dev"
    else
      sed -n '1p'
    fi
    ;;
  input)
    value=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --value) value="${{2:-}}"; shift 2 ;;
        *) shift ;;
      esac
    done
    echo "$value"
    ;;
  confirm)
    exit 0
    ;;
esac
SH
chmod +x "{fakebin / 'gum'}"
""",
        encoding="utf-8",
    )
    brew.chmod(0o755)
    env = {
        "PATH": f"{fakebin}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
        "GO_LIVE_NO_GUM": "0",
        "GO_LIVE_FORCE_GUM": "1",
        "BREW_LOG": str(brew_log),
        "GUM_LOG": str(gum_log),
    }

    result = run_wizard("--workspace", str(tmp_path / "workspace"), input_text="y\n", env=env)

    combined = result.stdout + result.stderr
    assert "gum installed; continuing with the gum TUI." in combined
    assert "Ordered go-live plan for dev:" in combined
    assert "install gum" in brew_log.read_text(encoding="utf-8")
    log = gum_log.read_text(encoding="utf-8")
    assert "choose --header Select operation --selected plan" in log
    assert "choose --header Select environment --selected dev" in log
    assert "input --prompt AWS admin/provisioning profile:" in log
    assert "confirm Continue with selected environment dev?" in log


def test_tui_makes_all_core_config_selectable(tmp_path: Path) -> None:
    workspace = tmp_path / "custom-workspace"
    input_text = "\n".join(
        [
            "3",
            "2",
            "aws-admin-custom",
            "deployer-custom",
            "us-west-2",
            "snow-prod-custom",
            str(workspace),
            "y",
            "",
        ]
    )

    result = run_wizard("wizard", input_text=input_text)

    combined = result.stdout + result.stderr
    assert "selected environment: prod" in combined
    assert "AWS profile: aws-admin-custom" in combined
    assert "AWS deployer profile: deployer-custom" in combined
    assert "AWS region: us-west-2" in combined
    assert "Snowflake connection: snow-prod-custom" in combined
    assert "Ordered go-live plan for prod:" in combined
    assert "AWS_PROFILE='aws-admin-custom' AWS_DEFAULT_REGION='us-west-2' terraform apply" in combined
    assert "SNOW_CONNECTION='snow-prod-custom' bash infra/scripts/deploy-snowflake-stack.sh" in combined
    assert not workspace.exists()


def test_plan_prints_preview_only_aws_ordered_commands(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    result = run_wizard("plan", "--workspace", str(workspace))

    out = result.stdout
    assert "Ordered go-live plan for dev:" in out
    assert "No real infrastructure will be deployed unless you confirm an apply stage." in out
    assert "[preview only] AWS_PROFILE='aws-admin-dev' AWS_DEFAULT_REGION='us-east-1' terraform apply" in out
    assert "AWS: Terraform state bucket" in out
    assert "AWS: passive infrastructure" in out
    assert "AWS: access roles/policies" in out
    assert "AWS: ECR image publish" in out
    assert "AWS: ECS task definitions and Step Functions" in out
    assert "CloudWatch logs" in out
    assert "Secrets Manager containers" in out
    assert "Snowflake: native-pull foundation" in out
    assert "baseline database/schemas/warehouses" in out
    assert "dbt gold" in out
    assert "Streamlit dashboard" in out
    assert "Snowflake Postgres / graph prerequisites" in out
    assert "MDM + graph: secret bootstrap" in out
    assert "Data: bounded smoke only" in out
    assert "bootstrap-next --limit 100" in out
    assert "bootstrap-full" not in out
    assert "full bootstrap" not in out.lower()
    assert not workspace.exists()


def test_doctor_init_plan_do_not_call_state_changing_commands(tmp_path: Path) -> None:
    fakebin, call_log = make_fake_tools(tmp_path)
    workspace = tmp_path / "workspace"
    env = {
        "PATH": f"{fakebin}{os.pathsep}{os.environ['PATH']}",
        "GO_LIVE_CALL_LOG": str(call_log),
    }

    run_wizard("doctor", "--workspace", str(workspace), env=env, check=False)
    run_wizard("init", "--workspace", str(workspace), env=env)
    run_wizard("plan", "--workspace", str(workspace), env=env)

    calls = call_log.read_text(encoding="utf-8") if call_log.exists() else ""
    assert "terraform apply" not in calls
    assert "deploy-aws-application" not in calls
    assert "publish-warehouse-image" not in calls
    assert "dbt run" not in calls
    assert "docker build" not in calls
    assert "sts get-caller-identity" in calls
    assert "snow connection test --connection snowconn" in calls
    assert (workspace / "state.json").is_file()
    assert (workspace / "reports").is_dir()
    assert (workspace / "setup" / "dev" / "infra" / "terraform" / "accounts" / "dev" / "backend.hcl.example").is_file()


def test_deploy_preview_and_declined_apply_do_not_execute_stages(tmp_path: Path) -> None:
    fakebin, call_log = make_fake_tools(tmp_path)
    workspace = tmp_path / "workspace"
    env = {
        "PATH": f"{fakebin}{os.pathsep}{os.environ['PATH']}",
        "GO_LIVE_CALL_LOG": str(call_log),
    }

    preview = run_wizard("deploy", "--workspace", str(workspace), env=env)
    state = json.loads((workspace / "state.json").read_text(encoding="utf-8"))
    assert "Preview complete. No real commands were run because --apply was not provided." in preview.stdout
    assert {event["status"] for event in state["events"]} == {"previewed"}

    call_log.write_text("", encoding="utf-8")
    declined_input = "y\n" + ("n\n" * 20)
    declined = run_wizard("deploy", "--apply", "--workspace", str(workspace), input_text=declined_input, env=env)
    state = json.loads((workspace / "state.json").read_text(encoding="utf-8"))
    assert "Skipped stage: AWS: Terraform state bucket" in declined.stdout
    assert {event["status"] for event in state["events"]} == {"skipped"}
    calls = call_log.read_text(encoding="utf-8")
    assert calls == ""


def test_report_redacts_sensitive_values_from_state_and_commands(tmp_path: Path) -> None:
    fakebin, call_log = make_fake_tools(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    report_file = tmp_path / "report.md"
    (workspace / "state.json").write_text(
        json.dumps(
            {
                "events": [
                    {
                        "stage": "arn:aws:iam::123456789012:role/example s3://bucket/path",
                        "status": "skipped",
                        "detail": (
                            "external_id = abc123 "
                            "postgresql://user:pass@example.snowflake.app:5432/mdm "
                            "password=secret token=tok sha256:" + ("a" * 64)
                        ),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    env = {
        "PATH": f"{fakebin}{os.pathsep}{os.environ['PATH']}",
        "GO_LIVE_CALL_LOG": str(call_log),
    }

    run_wizard("report", "--workspace", str(workspace), "--report-file", str(report_file), env=env, check=False)

    report = report_file.read_text(encoding="utf-8")
    forbidden = [
        "arn:aws:iam::123456789012:role/example",
        "123456789012",
        "s3://bucket/path",
        "external_id = abc123",
        "postgresql://user:pass@example.snowflake.app:5432/mdm",
        "password=secret",
        "token=tok",
        "sha256:" + ("a" * 64),
    ]
    for value in forbidden:
        assert value not in report
    assert "<redacted-arn>" in report
    assert "<redacted-s3-url>" in report
    assert "<redacted-dsn>" in report
    assert "<redacted-image-digest>" in report


def test_gum_is_used_when_present_and_forced(tmp_path: Path) -> None:
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    gum_log = tmp_path / "gum.log"
    gum = fakebin / "gum"
    gum.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "${GUM_LOG}"
exit 0
""",
        encoding="utf-8",
    )
    gum.chmod(0o755)

    env = {
        "PATH": f"{fakebin}{os.pathsep}{os.environ['PATH']}",
        "GO_LIVE_FORCE_GUM": "1",
        "GO_LIVE_NO_GUM": "0",
        "GUM_LOG": str(gum_log),
    }

    run_wizard("plan", "--workspace", str(tmp_path / "workspace"), input_text="", env=env)

    assert "confirm Continue with selected environment dev?" in gum_log.read_text(encoding="utf-8")


def test_gum_is_used_for_tui_choose_and_input_when_present(tmp_path: Path) -> None:
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    gum_log = tmp_path / "gum.log"
    gum = fakebin / "gum"
    gum.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "${GUM_LOG}"
case "$1" in
  choose)
    if [[ "$*" == *"Select operation"* ]]; then
      echo "plan"
    elif [[ "$*" == *"Select environment"* ]]; then
      echo "dev"
    else
      sed -n '1p'
    fi
    ;;
  input)
    value=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --value) value="${2:-}"; shift 2 ;;
        *) shift ;;
      esac
    done
    echo "$value"
    ;;
  confirm)
    exit 0
    ;;
esac
""",
        encoding="utf-8",
    )
    gum.chmod(0o755)

    env = {
        "PATH": f"{fakebin}{os.pathsep}{os.environ['PATH']}",
        "GO_LIVE_FORCE_GUM": "1",
        "GO_LIVE_NO_GUM": "0",
        "GUM_LOG": str(gum_log),
    }

    result = run_wizard("--workspace", str(tmp_path / "workspace"), input_text="", env=env)

    assert "Ordered go-live plan for dev:" in result.stdout
    log = gum_log.read_text(encoding="utf-8")
    assert "choose --header Select operation" in log
    assert "choose --header Select environment" in log
    assert "input --prompt AWS admin/provisioning profile:" in log
    assert "confirm Continue with selected environment dev?" in log
