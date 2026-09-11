"""GitHub Actions must not revive the decommissioned AWS dev environment."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_ROOT = REPO_ROOT / ".github" / "workflows"


def test_github_actions_do_not_target_decommissioned_aws_dev() -> None:
    offenders = []
    for workflow in sorted(WORKFLOWS_ROOT.glob("*.y*ml")):
        source = workflow.read_text(encoding="utf-8")
        if "edgartools-dev" in source:
            offenders.append(workflow.relative_to(REPO_ROOT).as_posix())

    assert offenders == [], (
        "AWS dev was decommissioned; GitHub Actions must not reference its "
        f"removed roles or resources: {offenders}"
    )
