from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLEANUP = REPO_ROOT / "infra" / "scripts" / "cleanup-ecr-images.sh"
CREATE_DEPLOYER = REPO_ROOT / "infra" / "scripts" / "create-deployer.sh"


def test_ecr_cleanup_retains_tagged_and_active_task_images() -> None:
    script = CLEANUP.read_text(encoding="utf-8")

    assert "'--family-prefix', family" in script
    assert "'--family-name', family" not in script
    assert 'if image_in_use "$full_repo" "$digest"; then' in script
    assert "keep   = bool(tags)" in script


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
