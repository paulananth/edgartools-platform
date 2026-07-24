from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_TERRAFORM = (
    REPO_ROOT / "infra" / "terraform" / "modules" / "warehouse_runtime" / "main.tf"
)


def test_ecr_lifecycle_never_expires_tagged_task_images() -> None:
    """Immutable sha tags referenced by ECS task definitions must survive."""
    terraform = RUNTIME_TERRAFORM.read_text(encoding="utf-8")

    assert 'resource "aws_ecr_lifecycle_policy" "warehouse"' in terraform
    assert 'tagStatus   = "untagged"' in terraform
    assert 'countType   = "imageCountMoreThan"' in terraform
    assert 'countNumber = 20' in terraform
    assert 'tagStatus   = "tagged"' not in terraform
