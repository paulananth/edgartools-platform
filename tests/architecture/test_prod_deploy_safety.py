from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY = REPO_ROOT / "infra" / "scripts" / "deploy-aws-application.sh"
CLEANUP = REPO_ROOT / "infra" / "scripts" / "cleanup-ecr-images.sh"


def test_prod_deploy_defaults_to_prod_scoped_runner_roles() -> None:
    script = DEPLOY.read_text(encoding="utf-8")

    assert 'RUNNER_ROLE_NAME_PREFIX=""' in script
    assert 'if [[ "$ENVIRONMENT" == "prod" ]]; then' in script
    assert 'RUNNER_ROLE_NAME_PREFIX="sec_platform_prod"' in script


def test_ecr_cleanup_retains_tagged_and_active_task_images() -> None:
    script = CLEANUP.read_text(encoding="utf-8")

    assert "'--family-prefix', family" in script
    assert "'--family-name', family" not in script
    assert 'if image_in_use "$full_repo" "$digest"; then' in script
    assert "if tags:" in script
