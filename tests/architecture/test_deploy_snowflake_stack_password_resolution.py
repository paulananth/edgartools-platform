"""Tests for deploy-snowflake-stack.sh's load_password_from_snow_config()
(Ticket 2 of the credential-isolation breakdown).

This function used to reimplement Snowflake password resolution as bash +
inline python3 reading config.toml's own [connections] table -- a layout no
real SnowCLI config anywhere in this repo (including CI's smoke-test.yml)
actually produces, so it always silently resolved empty. It now delegates
to `edgar-warehouse resolve-snowflake-env` (see
tests/unit/test_resolve_snowflake_env_cli.py for that command's own
behavioral coverage against fixture toml files).

Running deploy-snowflake-stack.sh for real requires live Terraform roots,
AWS, and Snowflake -- out of reach for an automated test, and this repo's
own existing coverage for this script family (test_install_wizard.py) never
attempts it either, testing only wrapper command construction instead. This
file takes the same approach for the piece that changed: exercise the real
bash logic of load_password_from_snow_config() end to end via a fake `uv`
on PATH, letting the script continue naturally to the (unrelated) missing
Terraform-root die that follows -- proving both that the override
short-circuit still bypasses the resolver entirely, and that the resolver
call itself is wired with the right arguments and its failure is non-fatal,
without needing any real infrastructure.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "infra" / "scripts" / "deploy-snowflake-stack.sh"


def _resolve_bash() -> str:
    # See test_install_wizard.py::_resolve_bash for the full rationale
    # (System32's bash.exe shadowing a real Git Bash on Windows). Duplicated
    # rather than imported to keep this file's fake-tool setup self-contained.
    if os.name != "nt":
        return "bash"
    windir = (os.environ.get("WINDIR") or os.environ.get("SystemRoot") or "").lower()
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / "bash.exe"
        if not candidate.is_file():
            continue
        if windir and str(candidate).lower().startswith(windir):
            continue
        return str(candidate)
    return "bash"


BASH = _resolve_bash()

NONEXISTENT_ENV = "credential-isolation-test-env-does-not-exist"


def _make_fake_uv(tmp_path: Path, *, resolver_should_fail: bool) -> tuple[Path, Path]:
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    call_log = tmp_path / "uv-calls.log"

    if resolver_should_fail:
        resolver_body = (
            'echo "error: simulated resolve-snowflake-env failure for tests" >&2\n'
            "exit 1\n"
        )
    else:
        resolver_body = (
            "echo 'export DBT_SNOWFLAKE_ACCOUNT=fake-acct'\n"
            "echo 'export DBT_SNOWFLAKE_USER=fake-user'\n"
            "echo 'export DBT_SNOWFLAKE_PASSWORD=fake-password'\n"
            "echo 'export DBT_SNOWFLAKE_DATABASE=fake-db'\n"
            "echo 'export DBT_SNOWFLAKE_WAREHOUSE=fake-wh'\n"
            "echo 'export TF_VAR_snowflake_password=fake-password'\n"
            "echo \"resolved Snowflake credentials for connection 'fake-connection'\" >&2\n"
            "exit 0\n"
        )

    tool = f"""#!/usr/bin/env bash
set -euo pipefail
echo "uv $*" >> "{call_log}"
if [[ "$1" == "run" && "$*" == *"edgar-warehouse resolve-snowflake-env"* ]]; then
{resolver_body}
fi
exit 0
"""
    uv_path = fakebin / "uv"
    uv_path.write_text(tool, encoding="utf-8", newline="\n")
    uv_path.chmod(0o755)
    return fakebin, call_log


def _run_script(tmp_path: Path, *, fakebin: Path | None, extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for key in ("TF_VAR_snowflake_password", "SNOWFLAKE_PASSWORD"):
        env.pop(key, None)
    if fakebin is not None:
        env["PATH"] = f"{fakebin}{os.pathsep}{env.get('PATH', '')}"
    env.update(extra_env)
    return subprocess.run(
        [
            BASH, str(SCRIPT),
            "--env-name", NONEXISTENT_ENV,
            "--snow-connection", "fake-connection",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )


# --- static content assertions -----------------------------------------------


def test_script_has_valid_bash_syntax():
    subprocess.run([BASH, "-n", str(SCRIPT)], check=True)


def test_no_longer_contains_the_old_inline_python_config_toml_parser():
    content = SCRIPT.read_text()
    assert "tomllib" not in content
    assert 'data.get("connections", {})' not in content


def test_calls_the_shared_resolver_with_the_connection_flag():
    content = SCRIPT.read_text()
    assert 'uv run --project "${REPO_ROOT}" --extra mdm-runtime edgar-warehouse resolve-snowflake-env --connection "${SNOW_CONNECTION}"' in content


def test_resolver_call_requests_the_mdm_runtime_extra():
    """edgar_warehouse.mdm.export imports sqlalchemy at module level, which
    is only present under the mdm/mdm-runtime optional-dependency groups
    (pyproject.toml), never a base dependency. Reproduced live: `uv run
    --project . edgar-warehouse resolve-snowflake-env ...` against a fresh
    (no-extras) venv raises `ModuleNotFoundError: No module named
    'sqlalchemy'`; `--extra mdm-runtime` (the same extra
    bootstrap-prod-mdm.sh already uses for its own `edgar-warehouse mdm ...`
    calls) fixes it. Without this flag every real invocation of this script
    would fail at this line for any operator whose venv only has the base
    `uv sync --extra s3 --extra snowflake` install CLAUDE.md documents.
    """
    content = SCRIPT.read_text()
    assert "--extra mdm-runtime edgar-warehouse resolve-snowflake-env" in content


def test_requires_uv_before_calling_the_resolver():
    content = SCRIPT.read_text()
    assert "require_command uv" in content


# --- behavioral: override precedence still short-circuits the resolver ------


def test_tf_var_snowflake_password_already_set_never_invokes_the_resolver(tmp_path):
    fakebin, call_log = _make_fake_uv(tmp_path, resolver_should_fail=False)
    result = _run_script(tmp_path, fakebin=fakebin, extra_env={"TF_VAR_snowflake_password": "preset-password"})

    assert result.returncode == 1
    assert not call_log.exists(), f"uv should never have been invoked, but logged: {call_log.read_text() if call_log.exists() else ''}"
    assert "does not exist" in result.stderr
    assert "WARNING: could not resolve" not in result.stderr


def test_snowflake_password_env_var_never_invokes_the_resolver(tmp_path):
    fakebin, call_log = _make_fake_uv(tmp_path, resolver_should_fail=False)
    result = _run_script(tmp_path, fakebin=fakebin, extra_env={"SNOWFLAKE_PASSWORD": "preset-password"})

    assert result.returncode == 1
    assert not call_log.exists()
    assert "does not exist" in result.stderr
    assert "WARNING: could not resolve" not in result.stderr


# --- behavioral: no override -> the resolver is actually invoked ------------


def test_no_override_invokes_the_resolver_with_the_snow_connection(tmp_path):
    fakebin, call_log = _make_fake_uv(tmp_path, resolver_should_fail=False)
    result = _run_script(tmp_path, fakebin=fakebin, extra_env={})

    assert call_log.exists(), "expected the resolver to be invoked when no password override is set"
    logged = call_log.read_text()
    assert 'run --project' in logged
    assert 'edgar-warehouse resolve-snowflake-env --connection fake-connection' in logged
    # Died at the (unrelated) missing-Terraform-root check, not a resolver failure.
    assert result.returncode == 1
    assert "does not exist" in result.stderr
    assert "WARNING: could not resolve" not in result.stderr


def test_resolver_failure_is_non_fatal_and_falls_through(tmp_path):
    fakebin, call_log = _make_fake_uv(tmp_path, resolver_should_fail=True)
    result = _run_script(tmp_path, fakebin=fakebin, extra_env={})

    assert call_log.exists()
    # Still dies at the missing-Terraform-root check -- a resolver miss alone
    # doesn't abort the script, matching the pre-Ticket-2 best-effort behaviour.
    assert result.returncode == 1
    assert "does not exist" in result.stderr
    assert "WARNING: could not resolve a Snowflake password for connection 'fake-connection'" in result.stderr
    assert "simulated resolve-snowflake-env failure for tests" in result.stderr
