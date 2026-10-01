"""ops-cost-control ticket 03: the CloudWatch log group Terraform creates
stays at the seven-day Operational Forensics Window. (The two log groups the
retired deploy-aws-application.sh managed are no longer managed in code.)
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_TERRAFORM = REPO_ROOT / "infra" / "terraform" / "modules" / "warehouse_runtime" / "main.tf"

OPERATIONAL_FORENSICS_WINDOW_DAYS = 7


def test_terraform_ecs_log_group_retention_is_seven_days() -> None:
    terraform = RUNTIME_TERRAFORM.read_text(encoding="utf-8")
    match = re.search(r'resource "aws_cloudwatch_log_group" "ecs" \{.*?\n\}', terraform, re.DOTALL)
    assert match, "aws_cloudwatch_log_group.ecs resource not found"
    block = match.group(0)
    assert f"retention_in_days = {OPERATIONAL_FORENSICS_WINDOW_DAYS}" in block
    assert "retention_in_days = 30" not in block
