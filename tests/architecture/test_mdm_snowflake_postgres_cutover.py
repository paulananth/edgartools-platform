from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "infra" / "scripts" / "deploy-aws-application.sh"
AUDIT_SCRIPT = REPO_ROOT / "infra" / "scripts" / "audit-mdm-snowflake-postgres-cutover.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_audit_module():
    spec = importlib.util.spec_from_file_location("audit_mdm_snowflake_postgres_cutover", AUDIT_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_deploy_script_defaults_mdm_database_source_to_rds() -> None:
    text = _read(DEPLOY_SCRIPT)

    assert 'MDM_DATABASE_SOURCE=""' in text
    assert 'MDM_DATABASE_SOURCE="$(first_nonempty "$MDM_DATABASE_SOURCE" "$(manifest_value mdm.database_source)" "rds")"' in text
    assert "--mdm-database-source <rds|snowflake-postgres>" in text
    assert '--mdm-database-source) MDM_DATABASE_SOURCE="${2:?}"; shift 2 ;;' in text
    assert "--mdm-database-source must be rds or snowflake-postgres" in text


def test_deploy_script_snowflake_postgres_source_skips_rds_secret_sync() -> None:
    text = _read(DEPLOY_SCRIPT)

    assert 'if [[ "$MDM_DATABASE_SOURCE" == "rds" ]]; then' in text
    assert 'sync_mdm_postgres_dsn "$MDM_POSTGRES_DSN_SECRET_ARN" "$MDM_RDS_INSTANCE_ID"' in text
    assert "Skipping RDS DSN sync; using operator-managed Snowflake Postgres DSN secret" in text
    assert '"database_source": mdm_database_source' in text


def test_deploy_script_bucket_discovery_does_not_capture_head_bucket_output() -> None:
    text = _read(DEPLOY_SCRIPT)

    assert 'aws_cli s3api head-bucket --bucket "$unsuffixed" >/dev/null 2>&1' in text
    assert 'aws_cli s3api head-bucket --bucket "$suffixed" >/dev/null 2>&1' in text


def test_deploy_script_still_injects_mdm_database_url_into_warehouse_and_mdm_tasks() -> None:
    text = _read(DEPLOY_SCRIPT)

    assert '{"name": "MDM_DATABASE_URL", "valueFrom": mdm_postgres_dsn_secret_arn}' in text
    assert '{"name": "MDM_DATABASE_URL", "valueFrom": mdm_database_secret_arn}' in text


def test_terraform_moves_mdm_secret_containers_to_runtime_module() -> None:
    for env in ("dev", "prod"):
        moves = _read(REPO_ROOT / "infra" / "terraform" / "accounts" / env / "mdm_secret_moves.tf")
        assert "module.mdm[0].aws_secretsmanager_secret.postgres_dsn" in moves
        assert "module.runtime.aws_secretsmanager_secret.mdm_postgres_dsn" in moves
        assert "module.mdm[0].aws_secretsmanager_secret.api_keys" in moves
        assert "module.runtime.aws_secretsmanager_secret.mdm_api_keys" in moves
        assert "module.mdm[0].aws_secretsmanager_secret.snowflake" in moves
        assert "module.runtime.aws_secretsmanager_secret.mdm_snowflake" in moves


def test_terraform_account_roots_no_longer_provision_mdm_rds() -> None:
    terraform_paths = list((REPO_ROOT / "infra" / "terraform" / "accounts").rglob("*.tf"))
    terraform_paths += list((REPO_ROOT / "infra" / "terraform" / "modules").rglob("*.tf"))
    texts = {path: _read(path) for path in terraform_paths}

    assert not any("aws_db_instance" in text for text in texts.values())
    assert not any("mdm_enabled" in text for text in texts.values())
    assert not any("mdm_database" in str(path) for path in terraform_paths)


def test_runtime_module_owns_all_mdm_secret_outputs() -> None:
    main = _read(REPO_ROOT / "infra" / "terraform" / "modules" / "warehouse_runtime" / "main.tf")
    outputs = _read(REPO_ROOT / "infra" / "terraform" / "modules" / "warehouse_runtime" / "outputs.tf")

    for name in ("mdm_postgres_dsn", "mdm_neo4j", "mdm_api_keys", "mdm_snowflake"):
        assert f'resource "aws_secretsmanager_secret" "{name}"' in main
    for output in (
        "mdm_postgres_dsn_secret_arn",
        "mdm_neo4j_secret_arn",
        "mdm_api_keys_secret_arn",
        "mdm_snowflake_secret_arn",
    ):
        assert f'output "{output}"' in outputs


def test_audit_dsn_validation_fails_for_non_snowflake_postgres_host() -> None:
    audit = _load_audit_module()

    with pytest.raises(audit.AuditFailure, match="host must end with"):
        audit.validate_snowflake_postgres_dsn(
            "postgresql://application:secret@legacy.rds.amazonaws.com:5432/mdm?sslmode=require",
            expected_host=None,
            expected_host_suffix=".snowflake.app",
            database="mdm",
            resolve_dns=False,
        )


def test_audit_masks_dsn_credentials() -> None:
    audit = _load_audit_module()

    result = audit.validate_snowflake_postgres_dsn(
        "postgresql://application:super-secret@abc123.snowflake.app:5432/mdm?sslmode=require",
        expected_host=None,
        expected_host_suffix=".snowflake.app",
        database="mdm",
        resolve_dns=False,
    )

    assert "super-secret" not in result.masked
    assert "application:***@" in result.masked


def test_audit_task_definition_secret_check_requires_expected_arn() -> None:
    audit = _load_audit_module()
    task_definition = {
        "containerDefinitions": [{
            "secrets": [{"name": "MDM_DATABASE_URL", "valueFrom": "arn:expected"}],
        }],
    }

    assert audit.task_definition_injects_secret(task_definition, "arn:expected")
    assert not audit.task_definition_injects_secret(task_definition, "arn:other")


def test_audit_detects_stale_state_machine_task_definition_revision() -> None:
    audit = _load_audit_module()

    class FakeAws:
        def json(self, *args: str):
            assert args[:2] == ("stepfunctions", "describe-state-machine")
            return {
                "definition": json.dumps({
                    "States": {
                        "Run": {
                            "Parameters": {
                                "TaskDefinition": "arn:aws:ecs:us-east-1:1:task-definition/edgartools-dev-medium:1"
                            }
                        }
                    }
                })
            }

    with pytest.raises(audit.AuditFailure, match="stale task definition revisions"):
        audit.assert_state_machines_use_manifest_task_revisions(
            FakeAws(),
            {"bootstrap": "arn:state-machine"},
            {"arn:aws:ecs:us-east-1:1:task-definition/edgartools-dev-medium:2"},
        )
