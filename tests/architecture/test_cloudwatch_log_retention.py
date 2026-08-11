"""ops-cost-control ticket 03: every production CloudWatch log group this
platform manages the retention of must stay at the seven-day Operational
Forensics Window across both provisioning paths -- Terraform (the one log
group it creates directly) and deploy-aws-application.sh (the two it manages
imperatively via ensure_log_group, one of which -- Container Insights'
performance log group -- AWS auto-creates and nothing else asserts).

Prior to this ticket, both paths hardcoded 30 days: every terraform apply or
deploy-aws-application.sh run silently reverted any out-of-band 7-day change
(confirmed live in prod via ticket 01's measurement -- see the ticket file).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_TERRAFORM = REPO_ROOT / "infra" / "terraform" / "modules" / "warehouse_runtime" / "main.tf"
DEPLOY_SCRIPT = REPO_ROOT / "infra" / "scripts" / "deploy-aws-application.sh"

OPERATIONAL_FORENSICS_WINDOW_DAYS = 7


def test_terraform_ecs_log_group_retention_is_seven_days() -> None:
    terraform = RUNTIME_TERRAFORM.read_text(encoding="utf-8")
    match = re.search(r'resource "aws_cloudwatch_log_group" "ecs" \{.*?\n\}', terraform, re.DOTALL)
    assert match, "aws_cloudwatch_log_group.ecs resource not found"
    block = match.group(0)
    assert f"retention_in_days = {OPERATIONAL_FORENSICS_WINDOW_DAYS}" in block
    assert "retention_in_days = 30" not in block


def test_ensure_log_group_has_no_hardcoded_retention_default() -> None:
    """The function must require every caller to state retention explicitly --
    no implicit default a future call site could silently inherit."""
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"^ensure_log_group\(\) \{.*?\n\}", script, re.DOTALL | re.MULTILINE)
    assert match, "ensure_log_group() function not found"
    body = match.group(0)
    assert "retention_days" in body
    assert re.search(r"--retention-in-days\s+30\b", body) is None
    assert '--retention-in-days "$retention_days"' in body


def test_step_functions_log_group_uses_the_operational_forensics_window() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert f"OPERATIONAL_FORENSICS_LOG_RETENTION_DAYS={OPERATIONAL_FORENSICS_WINDOW_DAYS}" in script
    assert (
        'ensure_log_group "$STEP_FUNCTIONS_LOG_GROUP_NAME" "$OPERATIONAL_FORENSICS_LOG_RETENTION_DAYS"'
        in script
    )


def test_container_insights_performance_log_group_is_managed() -> None:
    """The Container Insights performance log group is AWS-auto-created (not
    Terraform- or script-created), so nothing previously asserted its
    retention at all -- it just happened to be 7 days because it was set
    once, out-of-band, and never touched again. Must now be reasserted on
    every deploy, the same way the Step Functions log group already is."""
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert '/aws/ecs/containerinsights/${CLUSTER_NAME}/performance' in script
    assert (
        'ensure_log_group "$CONTAINER_INSIGHTS_LOG_GROUP_NAME" "$OPERATIONAL_FORENSICS_LOG_RETENTION_DAYS"'
        in script
    )


def test_no_remaining_thirty_day_log_retention_hardcodes() -> None:
    """Regression guard: neither file may hardcode the old 30-day value for a
    log group retention policy anywhere, not just at the two sites this
    ticket fixed."""
    terraform = RUNTIME_TERRAFORM.read_text(encoding="utf-8")
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert "retention_in_days = 30" not in terraform
    assert re.search(r"--retention-in-days\s+30\b", script) is None
