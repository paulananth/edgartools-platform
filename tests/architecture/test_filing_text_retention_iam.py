"""Narrow IAM contract for the versioned filing-text mutation lock."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ACCESS = (
    REPO_ROOT
    / "infra"
    / "terraform"
    / "access"
    / "aws"
    / "modules"
    / "runtime_access"
    / "main.tf"
)


def test_runtime_can_release_only_the_exact_versioned_filing_text_lock() -> None:
    terraform = RUNTIME_ACCESS.read_text(encoding="utf-8")

    expected_statement = """
      {
        Effect   = "Allow"
        Action   = ["s3:DeleteObjectVersion"]
        Resource = "${var.warehouse_bucket_arn}/warehouse/release/filing-text-retention/mutation.lock"
      },
"""

    assert expected_statement in terraform
