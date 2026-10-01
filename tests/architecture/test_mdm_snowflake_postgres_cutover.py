from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_runtime_module_retires_bookkeeping_secret_without_deleting_archive() -> None:
    main = _read(REPO_ROOT / "infra" / "terraform" / "modules" / "warehouse_runtime" / "main.tf")
    outputs = _read(REPO_ROOT / "infra" / "terraform" / "modules" / "warehouse_runtime" / "outputs.tf")

    assert 'from = aws_secretsmanager_secret.bookkeeping_postgres_dsn' in main
    assert 'destroy = false' in main
    assert 'output "bookkeeping_postgres_dsn_secret_arn"' not in outputs


def test_terraform_moves_mdm_secret_containers_to_runtime_module() -> None:
    for env in ("dev", "prod"):
        moves = _read(REPO_ROOT / "infra" / "terraform" / "accounts" / env / "mdm_secret_moves.tf")
        assert "module.mdm[0].aws_secretsmanager_secret.postgres_dsn" in moves
        assert "module.runtime.aws_secretsmanager_secret.mdm_postgres_dsn" in moves
        assert "module.mdm[0].aws_secretsmanager_secret.snowflake" in moves
        assert "module.runtime.aws_secretsmanager_secret.mdm_snowflake" in moves


def test_terraform_account_roots_no_longer_provision_mdm_rds() -> None:
    terraform_paths = list((REPO_ROOT / "infra" / "terraform" / "accounts").rglob("*.tf"))
    terraform_paths += list((REPO_ROOT / "infra" / "terraform" / "modules").rglob("*.tf"))
    texts = {path: _read(path) for path in terraform_paths}

    assert not any("aws_db_instance" in text for text in texts.values())
    assert not any("mdm_enabled" in text for text in texts.values())
    assert not any("mdm_database" in str(path) for path in terraform_paths)


def test_runtime_module_owns_only_active_mdm_secret_outputs() -> None:
    main = _read(REPO_ROOT / "infra" / "terraform" / "modules" / "warehouse_runtime" / "main.tf")
    outputs = _read(REPO_ROOT / "infra" / "terraform" / "modules" / "warehouse_runtime" / "outputs.tf")

    for name in ("mdm_postgres_dsn", "mdm_snowflake"):
        assert f'resource "aws_secretsmanager_secret" "{name}"' in main
    for output in ("mdm_postgres_dsn_secret_arn", "mdm_snowflake_secret_arn"):
        assert f'output "{output}"' in outputs
    for retired in ("mdm_neo4j", "mdm_api_keys"):
        assert f'resource "aws_secretsmanager_secret" "{retired}"' not in main
        assert f"from = aws_secretsmanager_secret.{retired}" in main
        assert f'output "{retired}_secret_arn"' not in outputs
