"""Generate real container definitions locally; no AWS calls or secret values."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "infra/scripts/deploy-aws-application.sh"


@pytest.mark.parametrize(
    "function", ["write_container_definitions", "write_mdm_container_definitions"]
)
@pytest.mark.parametrize("fresh", [False, True])
@pytest.mark.parametrize("provided", [False, True])
def test_generated_task_uses_separate_explicit_runtime_secrets(
    tmp_path, function, fresh, provided
):
    source = SCRIPT.read_text()
    start = source.index(function + "() {\n")
    end = source.index("\nPY\n}\n", start) + len("\nPY\n}\n")
    fn = tmp_path / "function.sh"
    fn.write_text(source[start:end])
    names = [
        "BOOKKEEPING_CLEAN_DATABASE_URL",
        "RULES_DATABASE_URL",
        "CHANGE_JOURNAL_DATABASE_URL",
    ]
    secrets = (
        [
            {
                "name": name,
                "valueFrom": f"arn:aws:secretsmanager:us-east-1:000000000000:secret:{name}",
            }
            for name in names
        ]
        if provided
        else []
    )
    output = tmp_path / "container.json"
    driver = tmp_path / "driver.sh"
    profile = (
        (
            "journal-large"
            if function == "write_container_definitions"
            else "mdm-journal-large"
        )
        if fresh
        else "medium"
    )
    driver.write_text(
        """set -euo pipefail
win_path() { printf '%s' "$1"; }
IMAGE_REF='warehouse-image'
MDM_IMAGE_REF='mdm-image'
AWS_REGION_NAME='us-east-1'
ENVIRONMENT='dev'
WAREHOUSE_RUNTIME_MODE='bronze_capture'
BRONZE_BUCKET_NAME='bronze'
WAREHOUSE_BUCKET_NAME='warehouse'
SNOWFLAKE_EXPORT_BUCKET_NAME='export'
EDGAR_IDENTITY_SECRET_ARN='identity-arn'
LOG_GROUP_NAME='log-group'
WAREHOUSE_BRONZE_CIK_LIMIT='10'
MDM_POSTGRES_DSN_SECRET_ARN='legacy-mdm-arn'
MDM_SNOWFLAKE_SECRET_ARN='snowflake-arn'
BOOKKEEPING_POSTGRES_DSN_SECRET_ARN='legacy-book-arn'
"""
        + "FRESH_CONTROL_SECRETS_JSON='"
        + json.dumps(secrets)
        + "'\nsource '"
        + str(fn)
        + "'\n"
        + function
        + " '"
        + str(output)
        + "' "
        + profile
        + "\n"
    )
    result = subprocess.run(["bash", str(driver)], capture_output=True, text=True)
    if fresh and not provided:
        assert result.returncode != 0 and "requires all three" in result.stderr
        assert not output.exists()
        return
    assert result.returncode == 0, result.stderr
    container = json.loads(output.read_text())[0]
    actual = {entry["name"]: entry["valueFrom"] for entry in container["secrets"]}
    if fresh:
        assert all(
            actual[name] == expected["valueFrom"]
            for name, expected in zip(names, secrets)
        )
        assert {entry["name"]: entry["value"] for entry in container["environment"]}[
            "BOOKKEEPING_MANIFEST_ROOT"
        ].startswith("s3://warehouse/")
        assert "BOOKKEEPING_DATABASE_URL" not in actual
        assert container["command"] == ["change-journal", "status"]
    else:
        assert not set(names) & set(actual)
        assert actual["BOOKKEEPING_DATABASE_URL"] == "legacy-book-arn"
        assert container["command"] == (
            ["--help"]
            if function == "write_container_definitions"
            else ["mdm", "--help"]
        )
    assert not any("MIGRATION_DATABASE_URL" in name for name in actual)
