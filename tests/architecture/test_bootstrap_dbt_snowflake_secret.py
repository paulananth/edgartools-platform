"""Tests for infra/scripts/bootstrap-dbt-snowflake-secret.sh (Ticket 4 of
the credential-isolation breakdown).

Closes the gap the secrets manifest (Ticket 3) documented: dbt/snowflake had
no populating script anywhere in this repo, despite being read live in prod
by bootstrap-prod-mdm.sh (which jq-transforms it into mdm/snowflake). The
JSON payload shape this script writes -- DBT_SNOWFLAKE_ACCOUNT/USER/PASSWORD/
WAREHOUSE/DATABASE/ROLE -- is bootstrap-prod-mdm.sh's exact read contract;
several tests here lock that shape in directly.

--dry-run needs no AWS call at all, so most cases use it. The one test that
needs to see the real secret-string payload uses a fake `aws` on PATH
(mirroring tests/architecture/test_install_wizard.py's fake-tool pattern) to
capture it without touching real AWS.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "infra" / "scripts" / "bootstrap-dbt-snowflake-secret.sh"


def _run(*args: str, stdin: str = "hunter2\n", env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
    )


def test_script_has_valid_bash_syntax():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_dry_run_with_required_flags_only_defaults_database_and_omits_role():
    result = _run(
        "--env-name", "prod",
        "--account", "acct-123",
        "--user", "svc_dbt",
        "--warehouse", "EDGARTOOLS_PROD_REFRESH_WH",
        "--password-stdin",
        "--dry-run",
    )
    assert result.returncode == 0, result.stderr
    assert "DRY RUN - target secret: edgartools-prod/dbt/snowflake" in result.stderr
    assert "database=EDGARTOOLS_PROD" in result.stderr
    assert "role=<none>" in result.stderr
    # The password itself never appears anywhere in the output.
    assert "hunter2" not in result.stdout
    assert "hunter2" not in result.stderr


def test_dry_run_derives_database_from_a_hyphenated_env_name():
    result = _run(
        "--env-name", "eu-prod",
        "--account", "a", "--user", "u", "--warehouse", "w",
        "--password-stdin", "--dry-run",
    )
    assert result.returncode == 0, result.stderr
    assert "database=EDGARTOOLS_EU_PROD" in result.stderr
    assert "DRY RUN - target secret: edgartools-eu-prod/dbt/snowflake" in result.stderr


def test_explicit_database_and_role_override_the_default():
    result = _run(
        "--env-name", "prod",
        "--account", "a", "--user", "u", "--warehouse", "w",
        "--database", "CUSTOM_DB", "--role", "EDGARTOOLS_PROD_LOADER",
        "--password-stdin", "--dry-run",
    )
    assert result.returncode == 0, result.stderr
    assert "database=CUSTOM_DB" in result.stderr
    assert "role=EDGARTOOLS_PROD_LOADER" in result.stderr


def test_explicit_secret_id_bypasses_the_manifest():
    result = _run(
        "--env-name", "prod",
        "--account", "a", "--user", "u", "--warehouse", "w",
        "--secret-id", "custom/override",
        "--password-stdin", "--dry-run",
    )
    assert result.returncode == 0, result.stderr
    assert "DRY RUN - target secret: custom/override" in result.stderr


def test_missing_account_fails_loudly():
    result = _run("--env-name", "prod", "--user", "u", "--warehouse", "w", "--password-stdin", "--dry-run")
    assert result.returncode == 1
    assert "--account is required" in result.stderr


def test_missing_user_fails_loudly():
    result = _run("--env-name", "prod", "--account", "a", "--warehouse", "w", "--password-stdin", "--dry-run")
    assert result.returncode == 1
    assert "--user is required" in result.stderr


def test_missing_warehouse_fails_loudly():
    result = _run("--env-name", "prod", "--account", "a", "--user", "u", "--password-stdin", "--dry-run")
    assert result.returncode == 1
    assert "--warehouse is required" in result.stderr


def test_missing_password_stdin_flag_fails_loudly():
    result = _run("--env-name", "prod", "--account", "a", "--user", "u", "--warehouse", "w", "--dry-run")
    assert result.returncode == 1
    assert "--password-stdin is required" in result.stderr


def test_empty_password_from_stdin_fails_loudly():
    result = _run(
        "--env-name", "prod", "--account", "a", "--user", "u", "--warehouse", "w",
        "--password-stdin", "--dry-run",
        stdin="",
    )
    assert result.returncode == 1
    assert "password read from stdin was empty" in result.stderr


def test_invalid_env_name_slug_fails_loudly():
    result = _run(
        "--env-name", "Not_A_Slug", "--account", "a", "--user", "u", "--warehouse", "w",
        "--password-stdin", "--dry-run",
    )
    assert result.returncode == 2
    assert "not a valid environment slug" in result.stderr


def test_missing_manifest_entry_fails_loudly(tmp_path):
    broken_manifest = tmp_path / "secrets-manifest.json"
    broken_manifest.write_text(json.dumps({"secrets": []}))
    result = _run(
        "--env-name", "prod", "--account", "a", "--user", "u", "--warehouse", "w",
        "--password-stdin", "--dry-run",
        env_overrides={"SECRETS_MANIFEST_PATH": str(broken_manifest)},
    )
    assert result.returncode == 1
    assert "dbt/snowflake" in result.stderr
    assert "is not declared" in result.stderr


def test_real_run_writes_the_exact_payload_shape_bootstrap_prod_mdm_reads(tmp_path):
    """The one test that inspects the actual secret-string payload, via a
    fake `aws` on PATH -- this is bootstrap-prod-mdm.sh's read contract
    (DBT_SNOWFLAKE_ACCOUNT/USER/PASSWORD/WAREHOUSE/DATABASE/ROLE), locked in
    directly rather than inferred from --dry-run's human-readable summary.
    """
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    call_log = tmp_path / "aws-calls.log"
    secret_string_file = tmp_path / "secret-string.json"
    fake_aws = fakebin / "aws"
    fake_aws.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "aws $*" >> "{call_log}"
args=("$@")
for i in "${{!args[@]}}"; do
  if [[ "${{args[$i]}}" == "--secret-string" ]]; then
    printf '%s' "${{args[$((i+1))]}}" > "{secret_string_file}"
  fi
done
echo '{{"Name":"fake","VersionId":"1"}}'
exit 0
""",
        encoding="utf-8",
        newline="\n",
    )
    fake_aws.chmod(0o755)

    result = _run(
        "--env-name", "prod",
        "--account", "acct-123",
        "--user", "svc_dbt",
        "--warehouse", "EDGARTOOLS_PROD_REFRESH_WH",
        "--role", "EDGARTOOLS_PROD_LOADER",
        "--password-stdin",
        stdin="s3cr3t-p@ss w0rd\n",
        env_overrides={"PATH": f"{fakebin}{os.pathsep}{os.environ['PATH']}"},
    )

    assert result.returncode == 0, result.stderr
    assert call_log.exists()
    assert "put-secret-value" in call_log.read_text()
    assert "--secret-id edgartools-prod/dbt/snowflake" in call_log.read_text()

    payload = json.loads(secret_string_file.read_text())
    assert payload == {
        "DBT_SNOWFLAKE_ACCOUNT": "acct-123",
        "DBT_SNOWFLAKE_USER": "svc_dbt",
        "DBT_SNOWFLAKE_PASSWORD": "s3cr3t-p@ss w0rd",
        "DBT_SNOWFLAKE_WAREHOUSE": "EDGARTOOLS_PROD_REFRESH_WH",
        "DBT_SNOWFLAKE_DATABASE": "EDGARTOOLS_PROD",
        "DBT_SNOWFLAKE_ROLE": "EDGARTOOLS_PROD_LOADER",
    }
    # The password never appears in this script's own stdout/stderr, only
    # inside the payload the fake `aws` captured on its own argv.
    assert "s3cr3t-p@ss w0rd" not in result.stdout
    assert "s3cr3t-p@ss w0rd" not in result.stderr


def test_real_run_without_role_writes_an_empty_role_key(tmp_path):
    """Not omitted: bootstrap-prod-mdm.sh's jq transform unconditionally
    reads .DBT_SNOWFLAKE_ROLE, so an absent key and an empty string aren't
    equivalent there (null vs \"\") -- the key must always be present."""
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    secret_string_file = tmp_path / "secret-string.json"
    fake_aws = fakebin / "aws"
    fake_aws.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
args=("$@")
for i in "${{!args[@]}}"; do
  if [[ "${{args[$i]}}" == "--secret-string" ]]; then
    printf '%s' "${{args[$((i+1))]}}" > "{secret_string_file}"
  fi
done
echo '{{"Name":"fake","VersionId":"1"}}'
exit 0
""",
        encoding="utf-8",
        newline="\n",
    )
    fake_aws.chmod(0o755)

    result = _run(
        "--env-name", "prod", "--account", "a", "--user", "u", "--warehouse", "w",
        "--password-stdin",
        env_overrides={"PATH": f"{fakebin}{os.pathsep}{os.environ['PATH']}"},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(secret_string_file.read_text())
    assert payload["DBT_SNOWFLAKE_ROLE"] == ""
