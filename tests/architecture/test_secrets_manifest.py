"""Tests for the credential-isolation secrets manifest (Ticket 3).

Covers three layers:
1. infra/scripts/secrets-manifest.json itself -- the declared secret list is
   accurate (checked against live investigation, not guessed).
2. infra/scripts/lib/secrets-manifest.sh's secrets_manifest_name() -- the
   shared lookup function every populating script now calls instead of
   hardcoding a name string.
3. The populating scripts (bootstrap-aws-mdm-secrets.sh, bootstrap-prod-mdm.sh,
   bootstrap-bookkeeping-postgres.sh) actually consume the manifest rather
   than a second hardcoded literal. bootstrap-aws-mdm-secrets.sh is fully
   exercised via its existing --dry-run mode (no AWS calls); the other two
   scripts' --dry-run still requires a live `snow sql` connection, so their
   wiring is covered by content assertions instead, matching this repo's
   existing tests/architecture/test_runtime_shim.py convention for "this
   file no longer does X" checks.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "infra" / "scripts" / "secrets-manifest.json"
LIB_PATH = REPO_ROOT / "infra" / "scripts" / "lib" / "secrets-manifest.sh"
BOOTSTRAP_AWS_MDM_SECRETS = REPO_ROOT / "infra" / "scripts" / "bootstrap-aws-mdm-secrets.sh"
BOOTSTRAP_PROD_MDM = REPO_ROOT / "infra" / "scripts" / "bootstrap-prod-mdm.sh"
BOOTSTRAP_BOOKKEEPING_POSTGRES = REPO_ROOT / "infra" / "scripts" / "bootstrap-bookkeeping-postgres.sh"

EXPECTED_NAMES = {
    "mdm/postgres_dsn",
    "mdm/snowflake",
    "mdm/neo4j",
    "mdm/api_keys",
    "dbt/snowflake",
    "bookkeeping/postgres_dsn",
}


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def test_manifest_is_valid_json_with_a_secrets_list():
    manifest = _load_manifest()
    assert isinstance(manifest["secrets"], list)
    assert manifest["secrets"]


def test_manifest_declares_exactly_the_six_known_secrets():
    manifest = _load_manifest()
    names = {entry["name"] for entry in manifest["secrets"]}
    assert names == EXPECTED_NAMES


def test_manifest_entry_shape_is_consistent():
    manifest = _load_manifest()
    for entry in manifest["secrets"]:
        assert set(entry) == {
            "name",
            "description",
            "terraform_resource",
            "populating_script",
            "populated_in_prod",
        }
        assert isinstance(entry["description"], str) and entry["description"]
        assert isinstance(entry["populated_in_prod"], bool)


def test_dbt_snowflake_entry_now_has_a_populating_script_but_still_no_terraform_resource():
    """dbt/snowflake was the whole point of the manifest: read live in prod
    (bootstrap-prod-mdm.sh) but originally had no Terraform resource and no
    populating script anywhere in the repo (confirmed via the architecture
    review's Explore pass, not guessed). Ticket 4 closed the populating-
    script half of that gap with bootstrap-dbt-snowflake-secret.sh; the
    Terraform half is unaffected (this secret's container was never
    Terraform-managed and still isn't).
    """
    manifest = _load_manifest()
    entry = next(e for e in manifest["secrets"] if e["name"] == "dbt/snowflake")
    assert entry["terraform_resource"] is None
    assert entry["populating_script"] == "infra/scripts/bootstrap-dbt-snowflake-secret.sh"
    assert entry["populated_in_prod"] is True


def test_mdm_neo4j_and_api_keys_are_declared_never_populated():
    manifest = _load_manifest()
    by_name = {e["name"]: e for e in manifest["secrets"]}
    assert by_name["mdm/neo4j"]["populated_in_prod"] is False
    assert by_name["mdm/api_keys"]["populated_in_prod"] is False


def test_mdm_postgres_dsn_and_mdm_snowflake_have_real_populating_scripts():
    manifest = _load_manifest()
    by_name = {e["name"]: e for e in manifest["secrets"]}
    assert by_name["mdm/postgres_dsn"]["populating_script"] == "infra/scripts/bootstrap-aws-mdm-secrets.sh"
    assert by_name["mdm/snowflake"]["populating_script"] == "infra/scripts/bootstrap-prod-mdm.sh"


def test_bookkeeping_postgres_dsn_has_a_real_populating_script_and_terraform_resource():
    """populated_in_prod is False, not True: the script is written and tested
    (DuckDB Retirement Cutover Ticket 04's tooling-built half) but has not
    actually run against live prod yet -- the live-execution half is still
    blocked on Ticket 03. Flip this to True only once that run happens, not
    when the tooling merely exists -- see CLAUDE.md's "MDM Postgres
    migration-011" lesson on why a stale claim that looks verified is worse
    than an honest gap.
    """
    manifest = _load_manifest()
    entry = next(e for e in manifest["secrets"] if e["name"] == "bookkeeping/postgres_dsn")
    assert entry["populating_script"] == "infra/scripts/bootstrap-bookkeeping-postgres.sh"
    assert entry["terraform_resource"] == (
        "infra/terraform/modules/warehouse_runtime/main.tf: aws_secretsmanager_secret.bookkeeping_postgres_dsn"
    )
    assert entry["populated_in_prod"] is False


# --- infra/scripts/lib/secrets-manifest.sh -----------------------------------


def _run_lookup(key: str, manifest_path: Path = MANIFEST_PATH) -> subprocess.CompletedProcess[str]:
    script = f'source "{LIB_PATH}"; secrets_manifest_name "{key}"'
    env = os.environ.copy()
    env["SECRETS_MANIFEST_PATH"] = str(manifest_path)
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env=env,
    )


def test_secrets_manifest_name_returns_a_declared_name_unchanged():
    result = _run_lookup("mdm/postgres_dsn")
    assert result.returncode == 0
    assert result.stdout.strip() == "mdm/postgres_dsn"


def test_secrets_manifest_name_fails_loudly_on_an_undeclared_name():
    result = _run_lookup("not/a/real/secret")
    assert result.returncode == 1
    assert result.stdout.strip() == ""
    assert "not/a/real/secret" in result.stderr
    assert "is not declared" in result.stderr


def test_secrets_manifest_name_fails_loudly_when_the_manifest_file_is_missing(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    result = _run_lookup("mdm/postgres_dsn", manifest_path=missing)
    assert result.returncode == 1
    assert "not found" in result.stderr


# --- bootstrap-aws-mdm-secrets.sh --------------------------------------------


def _run_bootstrap_aws_mdm_secrets(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(BOOTSTRAP_AWS_MDM_SECRETS), *args],
        input="test-password\n",
        capture_output=True,
        text=True,
    )


def test_bootstrap_aws_mdm_secrets_default_secret_id_is_resolved_via_the_manifest():
    result = _run_bootstrap_aws_mdm_secrets(
        "--env-name", "prod",
        "--host", "foo.snowflake.app",
        "--username", "application",
        "--password-stdin",
        "--dry-run",
    )
    assert result.returncode == 0, result.stderr
    assert "DRY RUN - target secret: edgartools-prod/mdm/postgres_dsn" in result.stderr


def test_bootstrap_aws_mdm_secrets_explicit_secret_id_bypasses_the_manifest():
    result = _run_bootstrap_aws_mdm_secrets(
        "--env-name", "prod",
        "--secret-id", "custom/override",
        "--host", "foo.snowflake.app",
        "--username", "application",
        "--password-stdin",
        "--dry-run",
    )
    assert result.returncode == 0, result.stderr
    assert "DRY RUN - target secret: custom/override" in result.stderr


def test_bootstrap_aws_mdm_secrets_fails_loudly_if_the_manifest_is_missing_the_key(tmp_path):
    broken_manifest = tmp_path / "secrets-manifest.json"
    broken_manifest.write_text(json.dumps({"secrets": []}))
    env = os.environ.copy()
    env["SECRETS_MANIFEST_PATH"] = str(broken_manifest)
    result = subprocess.run(
        [
            "bash", str(BOOTSTRAP_AWS_MDM_SECRETS),
            "--env-name", "prod",
            "--host", "foo.snowflake.app",
            "--username", "application",
            "--password-stdin",
            "--dry-run",
        ],
        input="test-password\n",
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 1
    assert "mdm/postgres_dsn" in result.stderr
    assert "is not declared" in result.stderr


# --- bootstrap-prod-mdm.sh (content assertions -- see module docstring) -----


def test_bootstrap_prod_mdm_sources_the_shared_secrets_manifest_lib():
    content = BOOTSTRAP_PROD_MDM.read_text()
    assert 'source "${SCRIPT_DIR}/lib/secrets-manifest.sh"' in content


def test_bootstrap_prod_mdm_resolves_all_three_secret_ids_via_the_manifest():
    content = BOOTSTRAP_PROD_MDM.read_text()
    assert 'secret_id "mdm/postgres_dsn"' in content
    assert 'secret_id "mdm/snowflake"' in content
    assert 'secret_id "dbt/snowflake"' in content


def test_bootstrap_prod_mdm_only_resolves_snowflake_secret_ids_when_not_skipped():
    """The --skip-snowflake-secret path shouldn't fail just because
    mdm/snowflake or dbt/snowflake happen to be missing from the manifest --
    that's an unrelated concern to what the flag is skipping.
    """
    content = BOOTSTRAP_PROD_MDM.read_text()
    lines = content.splitlines()
    snowflake_secret_id_line = next(i for i, line in enumerate(lines) if 'MDM_SNOWFLAKE_SECRET_ID="$(secret_id' in line)
    guard_line = next(
        i for i in range(snowflake_secret_id_line, -1, -1)
        if 'if [[ "$SKIP_SNOWFLAKE_SECRET" != "true" ]]; then' in lines[i]
    )
    assert guard_line < snowflake_secret_id_line
    # And nothing between the guard and the resolution closes the if early.
    assert not any("fi" == lines[i].strip() for i in range(guard_line + 1, snowflake_secret_id_line))


def test_bootstrap_prod_mdm_no_longer_hardcodes_the_secret_ids_inline():
    content = BOOTSTRAP_PROD_MDM.read_text()
    assert '--secret-id "${NAME_PREFIX}/dbt/snowflake"' not in content
    assert '--secret-id "${NAME_PREFIX}/mdm/snowflake"' not in content
    assert '--secret-id "${NAME_PREFIX}/mdm/postgres_dsn"' not in content


# --- bootstrap-bookkeeping-postgres.sh (content assertions) ------------------


def test_bootstrap_bookkeeping_postgres_sources_the_shared_secrets_manifest_lib():
    content = BOOTSTRAP_BOOKKEEPING_POSTGRES.read_text()
    assert 'source "${SCRIPT_DIR}/lib/secrets-manifest.sh"' in content


def test_bootstrap_bookkeeping_postgres_resolves_its_secret_id_via_the_manifest():
    content = BOOTSTRAP_BOOKKEEPING_POSTGRES.read_text()
    assert 'secret_id "bookkeeping/postgres_dsn"' in content


def test_bootstrap_bookkeeping_postgres_no_longer_hardcodes_the_secret_id_inline():
    content = BOOTSTRAP_BOOKKEEPING_POSTGRES.read_text()
    assert '--secret-id "${NAME_PREFIX}/bookkeeping/postgres_dsn"' not in content


def test_bootstrap_bookkeeping_postgres_rotates_snowflake_admin_exactly_once():
    """Unlike bootstrap-prod-mdm.sh (two snowflake_admin rotations, because an
    intervening `application` rotation reopens the acquisition-ledger fence a
    second time), this script never touches `application` at all -- its
    dedicated bookkeeping_app role is a plain, self-managed Postgres LOGIN
    role, not one of Snowflake's two RESET ACCESS-managed principals. So it
    should rotate snowflake_admin exactly once, closing the fence via the
    same rotation's password rather than a second RESET ACCESS call.
    """
    content = BOOTSTRAP_BOOKKEEPING_POSTGRES.read_text()
    assert content.count("RESET ACCESS FOR 'snowflake_admin'") == 1
    assert "RESET ACCESS FOR 'application'" not in content
