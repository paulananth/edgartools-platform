from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "infra" / "scripts" / "go-live.sh"
# Relative to REPO_ROOT (both subprocess.run calls below set cwd=REPO_ROOT) rather
# than an absolute path: on Windows, Git Bash's MSYS layer doesn't reliably resolve
# an absolute `C:/...`-style path passed as a bash argv element, even in POSIX
# (forward-slash) form. A relative path sidesteps the drive-letter/path-mapping
# ambiguity entirely and behaves identically on Linux, macOS, and Windows Git Bash.
SCRIPT_ARG = SCRIPT.relative_to(REPO_ROOT).as_posix()
TEST_ACCOUNT_ID = "123456789012"
# Environments are now operator-chosen slugs with no default, so tests must
# name one. "dev" is kept as the value so existing path/prefix assertions
# (workspace/setup/dev/..., edgartools-dev-*) stay meaningful.
DEFAULT_TEST_ENV = "dev"
DEFAULT_TEST_SNOW_CONNECTION = "snowconn"


def _resolve_bash() -> str:
    # On Linux/macOS there's exactly one "bash", so plain PATH resolution is fine.
    if os.name != "nt":
        return "bash"
    # On Windows, CreateProcess always checks %SystemRoot%\System32 before
    # consulting PATH (this is an OS-level search-order rule, not a PATH
    # ordering issue), so a bare "bash" resolves to the WSL launcher stub at
    # System32\bash.exe whenever WSL is installed -- even when Git Bash
    # appears earlier in the PATH string. WSL interop only forwards env vars
    # listed in WSLENV (empty by default), so every env-var-based test double
    # in this file (GO_LIVE_CALL_LOG, GO_LIVE_NO_GUM, fake tools prepended to
    # PATH) silently vanishes and the script falls back to unexpected
    # defaults instead of failing loudly. Explicitly prefer a real Git
    # Bash/MSYS bash.exe over the WSL stub, searching PATH in its own order
    # (unlike CreateProcess, Python's own directory walk here has no
    # System32-first special case).
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or ""
    windir = windir.lower()
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / "bash.exe"
        if not candidate.is_file():
            continue
        if windir and str(candidate).lower().startswith(windir):
            continue
        return str(candidate)
    return "bash"


BASH = _resolve_bash()


def run_wizard(
    *args: str,
    input_text: str = "y\n",
    env: dict[str, str] | None = None,
    check: bool = True,
    explicit_flags: bool = True,
) -> subprocess.CompletedProcess[str]:
    proc_env = os.environ.copy()
    # go-live.sh treats AWS_PROFILE/AWS_REGION/AWS_DEFAULT_REGION as implicit
    # overrides of its "aws-admin-<env>"/"us-east-1" defaults (go-live.sh:40,42),
    # so inheriting them from the calling shell verbatim makes this test's
    # assertions depend on whatever AWS CLI profile/region the developer or CI
    # runner happens to have exported -- confirmed live: with AWS_PROFILE set
    # to a real deploy profile (as this repo's own CLAUDE.md workflow commands
    # routinely export), test_plan_prints_preview_only_aws_ordered_commands
    # failed asserting on 'aws-admin-dev' while the wizard actually printed
    # the ambient profile. No test in this file relies on inheriting these, so
    # strip them unconditionally before any explicit `env` override is applied
    # below (a test that wants a specific profile passes it via `env=`).
    proc_env.pop("AWS_PROFILE", None)
    proc_env.pop("AWS_REGION", None)
    proc_env.pop("AWS_DEFAULT_REGION", None)
    proc_env.setdefault("GO_LIVE_NO_GUM", "1")
    proc_env.setdefault("GO_LIVE_AWS_ACCOUNT_ID", TEST_ACCOUNT_ID)
    proc_env.setdefault("FAKE_AWS_ACCOUNT_ID", TEST_ACCOUNT_ID)
    if env:
        proc_env.update(env)
    # --env-name and --snow-connection became required for every non-wizard
    # command (wayfinder ticket 03): the dev default and the derived connection
    # name are both gone. Supply them here so each test keeps exercising what it
    # was written to exercise; tests that assert on their absence pass
    # explicit_flags=False.
    args = list(args)
    if explicit_flags and args and not args[0].startswith("-"):
        if "--env-name" not in args:
            args += ["--env-name", DEFAULT_TEST_ENV]
        if "--snow-connection" not in args:
            args += ["--snow-connection", DEFAULT_TEST_SNOW_CONNECTION]
    # Deliberately NOT text=True for the subprocess call itself: on Windows,
    # subprocess's text/universal-newlines mode translates \n in `input` to
    # \r\n before writing to the child's stdin. bash's `read -r` terminates
    # on \n but leaves the preceding \r as part of the captured value, so
    # e.g. an "accept the default" blank-line answer becomes reply="\r"
    # rather than reply="" -- [[ -z "$reply" ]] then fails and the wizard
    # takes the wrong branch on every multi-prompt sequence. Encode input as
    # LF-only bytes explicitly and decode stdout/stderr back to str after,
    # so callers still get the str-based CompletedProcess they expect.
    raw_result = subprocess.run(
        [BASH, SCRIPT_ARG, *args],
        cwd=REPO_ROOT,
        input=input_text.encode("utf-8"),
        capture_output=True,
        env=proc_env,
        check=False,
    )
    result = subprocess.CompletedProcess(
        args=raw_result.args,
        returncode=raw_result.returncode,
        stdout=raw_result.stdout.decode("utf-8", errors="replace"),
        stderr=raw_result.stderr.decode("utf-8", errors="replace"),
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
    if [[ "$*" == *"get-caller-identity"* && "$*" == *"--query Account"* ]]; then
      printf '%s\n' "${FAKE_AWS_ACCOUNT_ID}"
    else
      printf '{"Account":"%s","Arn":"arn:aws:iam::%s:user/test","UserId":"test"}\n' \
        "${FAKE_AWS_ACCOUNT_ID}" "${FAKE_AWS_ACCOUNT_ID}"
    fi
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
        path.write_text(tool, encoding="utf-8", newline="\n")
        path.chmod(0o755)
    return fakebin, call_log


def test_go_live_script_has_valid_bash_syntax() -> None:
    subprocess.run([BASH, "-n", SCRIPT_ARG], cwd=REPO_ROOT, check=True)


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
    # operation, env slug, aws profile, deployer profile, region, snow connection,
    # workspace, confirm. Env and connection must be typed: neither has a default.
    input_text = "\n".join(["", "dev", "", "", "", "snowconn", "", "y", ""])

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
        newline="\n",
    )
    brew.chmod(0o755)
    workspace = tmp_path / "workspace"
    # Leading "n" declines the gum install; the rest is the prompt sequence above.
    input_text = "\n".join(["n", "", "dev", "", "", "", "snowconn", "", "y", ""])
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
    prompt=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --value) value="${{2:-}}"; shift 2 ;;
        --prompt) prompt="${{2:-}}"; shift 2 ;;
        *) shift ;;
      esac
    done
    # The environment slug and the Snowflake connection have no defaults to echo
    # back (wayfinder ticket 03 removed both), so stand in for what an operator
    # would type.
    if [[ -z "$value" && "$prompt" == *"Environment slug"* ]]; then
      echo "dev"
    elif [[ -z "$value" && "$prompt" == *"Snowflake connection"* ]]; then
      echo "snowconn"
    else
      echo "$value"
    fi
    ;;
  confirm)
    exit 0
    ;;
esac
SH
chmod +x "{fakebin / 'gum'}"
""",
        encoding="utf-8",
        newline="\n",
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
    # Environments are operator-chosen slugs now, so this is a free-text input
    # rather than a dev|prod pick-list (wayfinder ticket 03).
    assert "input --prompt Environment slug:" in log
    assert "choose --header Select environment" not in log
    assert "input --prompt AWS admin/provisioning profile:" in log
    assert "confirm Continue with selected environment dev?" in log


def test_tui_makes_all_core_config_selectable(tmp_path: Path) -> None:
    workspace = tmp_path / "custom-workspace"
    input_text = "\n".join(
        [
            "3",
            "prod",
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
    assert "bootstrap-prod-mdm.sh" in out
    assert "mdm_post_restore.sql" not in out
    assert "-D database=EDGARTOOLS_DEV" in out
    assert "Data: bounded smoke only" in out
    assert "bootstrap-next --limit 100" in out
    assert "Current go-live notes and issues:" in out
    assert "batch_size" in out
    assert "shard-manifest.json" in out
    assert "Blocker 4" in out
    assert "bootstrap-full" not in out
    assert "full bootstrap" not in out.lower()
    assert not workspace.exists()


def test_prod_plan_uses_canonical_names_and_maintained_delegates(tmp_path: Path) -> None:
    result = run_wizard("plan", "--env-name", "prod", "--snow-connection", "snowconn", "--workspace", str(tmp_path / "workspace"))

    out = result.stdout
    assert "EDGARTOOLS_PROD" in out
    assert "edgartools-prod" in out
    assert "infra/aws-prod-application.json" in out
    assert "deploy-aws-application.sh" in out
    assert "deploy-snowflake-stack.sh" in out
    assert "bootstrap-prod-mdm.sh" in out
    assert "infra/snowflake/streamlit/deploy.sh" in out
    assert "PRODB" not in out


def test_prod_apply_rejects_wrong_aws_account_before_any_stage(tmp_path: Path) -> None:
    fakebin, call_log = make_fake_tools(tmp_path)
    env = {
        "PATH": f"{fakebin}{os.pathsep}{os.environ['PATH']}",
        "GO_LIVE_CALL_LOG": str(call_log),
    }

    result = run_wizard(
        "deploy",
        "--apply",
        "--env-name",
        "prod",
        "--snow-connection",
        "snowconn",
        "--workspace",
        str(tmp_path / "workspace"),
        input_text="y\n",
        env={**env, "GO_LIVE_AWS_ACCOUNT_ID": "210987654321"},
        check=False,
    )

    assert result.returncode != 0
    assert "AWS account mismatch" in result.stderr
    calls = call_log.read_text(encoding="utf-8")
    assert "terraform apply" not in calls


def test_bronze_seed_stage_uses_pr95_batchsilver_progress_contract(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    result = run_wizard("plan", "--workspace", str(workspace))

    out = result.stdout
    assert "PR95" in out
    assert "bulk-upsert" in out
    assert "executionCounts.succeeded" in out
    assert "executionCounts.failed" in out
    assert "executionCounts.total" in out
    assert "itemCounts" not in out
    assert "7-10 minutes per batch" not in out


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
    assert "s3api head-object" in calls
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
    assert "sts get-caller-identity --query Account --output text" in calls
    assert "terraform apply" not in calls
    assert "deploy-aws-application" not in calls
    assert "publish-warehouse-image" not in calls


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
    assert "## Current Notes and Issues" in report
    assert "shard-manifest.json" in report


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
        newline="\n",
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
    prompt=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --value) value="${2:-}"; shift 2 ;;
        --prompt) prompt="${2:-}"; shift 2 ;;
        *) shift ;;
      esac
    done
    # Env slug and Snowflake connection have no defaults to echo back
    # (wayfinder ticket 03 removed both); stand in for an operator's typing.
    if [[ -z "$value" && "$prompt" == *"Environment slug"* ]]; then
      echo "dev"
    elif [[ -z "$value" && "$prompt" == *"Snowflake connection"* ]]; then
      echo "snowconn"
    else
      echo "$value"
    fi
    ;;
  confirm)
    exit 0
    ;;
esac
""",
        encoding="utf-8",
        newline="\n",
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
    # Environments are operator-chosen slugs now, so this is a free-text input
    # rather than a dev|prod pick-list (wayfinder ticket 03).
    assert "input --prompt Environment slug:" in log
    assert "choose --header Select environment" not in log
    assert "input --prompt AWS admin/provisioning profile:" in log
    assert "confirm Continue with selected environment dev?" in log


# ---------------------------------------------------------------------------
# Wayfinder snowflake-env-provisioning ticket 03: --env <dev|prod> became
# --env-name <slug>, and --snow-connection became required with no derived
# default. These pin the new contract; the tests above only prove the old one
# stopped being required.
# ---------------------------------------------------------------------------


def test_env_name_is_required_for_non_wizard_commands(tmp_path: Path) -> None:
    result = run_wizard(
        "plan",
        "--snow-connection",
        "snowconn",
        "--workspace",
        str(tmp_path / "workspace"),
        check=False,
        explicit_flags=False,
    )
    assert result.returncode != 0
    assert "--env-name is required" in result.stdout + result.stderr


def test_snow_connection_is_required_and_never_derived(tmp_path: Path) -> None:
    """Deriving it is what let go-live.sh and deploy-snowflake-stack.sh disagree
    about the default connection for the same environment."""
    result = run_wizard(
        "plan",
        "--env-name",
        "prod",
        "--workspace",
        str(tmp_path / "workspace"),
        check=False,
        explicit_flags=False,
    )
    assert result.returncode != 0
    assert "--snow-connection is required" in result.stdout + result.stderr


def test_old_env_flag_is_gone(tmp_path: Path) -> None:
    """Clean breaking rename -- no back-compat alias (dev is decommissioned, so
    prod's call sites were the only ones to update)."""
    result = run_wizard(
        "plan",
        "--env",
        "prod",
        "--snow-connection",
        "snowconn",
        check=False,
        explicit_flags=False,
    )
    assert result.returncode != 0


def test_arbitrary_slug_is_accepted_not_just_dev_or_prod(tmp_path: Path) -> None:
    """The whole point of ticket 03: a third environment fits neither bucket."""
    result = run_wizard(
        "plan",
        "--env-name",
        "eu-prod",
        "--snow-connection",
        "some-connection",
        "--workspace",
        str(tmp_path / "workspace"),
        explicit_flags=False,
    )
    combined = result.stdout + result.stderr
    assert "Ordered go-live plan for eu-prod:" in combined
    assert "EDGARTOOLS_EU-PROD" not in combined  # hyphen must not leak untouched


def test_malformed_slug_is_rejected(tmp_path: Path) -> None:
    for bad in ("BAD_Env", "1prod", "eu--prod", "eu-prod-"):
        result = run_wizard(
            "plan",
            "--env-name",
            bad,
            "--snow-connection",
            "snowconn",
            check=False,
            explicit_flags=False,
        )
        assert result.returncode != 0, bad
        assert "not a valid environment slug" in result.stdout + result.stderr, bad


def test_snowflake_delegates_get_env_name_and_aws_delegates_keep_env(
    tmp_path: Path,
) -> None:
    """go-live threads one identifier to two different flag names.

    The Snowflake-side scripts were renamed by ticket 03; the AWS-side ones were
    deliberately not (AWS provisioning is this map's documented precondition, and
    ticket 04 recorded their enum as the deferred gap). Getting this split wrong
    silently breaks either half.
    """
    result = run_wizard(
        "plan",
        "--env-name",
        "prod",
        "--snow-connection",
        "edgartools-prod",
        "--workspace",
        str(tmp_path / "workspace"),
        explicit_flags=False,
    )
    combined = result.stdout + result.stderr

    assert "deploy-snowflake-stack.sh --env-name prod" in combined
    assert "bootstrap-prod-mdm.sh --env-name prod" in combined
    assert "deploy-aws-application.sh --env prod" in combined
    assert "run-aws-mdm-e2e.sh --env prod" in combined
