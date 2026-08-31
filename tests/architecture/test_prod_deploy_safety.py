from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY = REPO_ROOT / "infra" / "scripts" / "deploy-aws-application.sh"
CLEANUP = REPO_ROOT / "infra" / "scripts" / "cleanup-ecr-images.sh"
CREATE_DEPLOYER = REPO_ROOT / "infra" / "scripts" / "create-deployer.sh"


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
    assert "keep   = bool(tags)" in script


def test_deploy_holds_the_release_cleanup_lock_while_registering_candidates() -> None:
    script = DEPLOY.read_text(encoding="utf-8")

    acquire = script.index("acquire-lock")
    register = script.index('TASK_DEF_SMALL_ARN="$(register_task_definition')
    release = script.index("release-lock")

    assert acquire < register
    assert "ROLLBACK_CLEANUP_LOCK_HELD" in script
    assert release < register  # release command is defined in the EXIT trap before deployment begins


def test_deploy_does_not_run_the_legacy_ecr_deletion_path() -> None:
    script = DEPLOY.read_text(encoding="utf-8")

    assert "cleanup-ecr-images.sh" not in script
    assert "legacy automatic ECR deletion is disabled" in script


def test_deployer_policy_can_run_the_hash_bound_rollback_cleanup_path() -> None:
    script = CREATE_DEPLOYER.read_text(encoding="utf-8")

    assert 'repository/${NAME_PREFIX}-images' in script
    assert '${NAME_PREFIX}-warehouse-${ACCOUNT_ID}' in script
    for action in (
        "ecr:BatchDeleteImage",
        "ecr:BatchGetImage",
        "ecs:DeregisterTaskDefinition",
        "ecs:DescribeTasks",
        "ecs:ListClusters",
        "ecs:ListServices",
        "ecs:ListTaskDefinitionFamilies",
        "ecs:ListTaskDefinitions",
        "ecs:ListTasks",
        "states:ListStateMachines",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
    ):
        assert f'"{action}"' in script

    registration = script.split('Sid: "RegisterWarehouseTaskDefinitions"', 1)[1].split(
        'Sid: "ManageRollbackRegistryAndLock"', 1
    )[0]
    scoped_management = script.split(
        'Sid: "ManageWarehouseTaskDefinitions"', 1
    )[1].split('Sid: "DescribeApplicationLogGroups"', 1)[0]
    assert '"ecs:DeregisterTaskDefinition"' not in registration
    assert '"ecs:DeregisterTaskDefinition"' in scoped_management
    assert "Resource: $task_definition_arn" in scoped_management
