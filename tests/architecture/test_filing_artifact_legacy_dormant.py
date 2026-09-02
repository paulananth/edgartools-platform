"""Ticket 27 filing_artifact cutover: legacy fetch stays dormant, not deleted.

Ticket 10 Decision 6: a family's legacy capture call stays unregistered
from the schedule, not deleted, for one full cycle after cutover.
Scheduled daily-incremental picks up gated capture from the CLI default,
so the Step Functions command array must not pin the old off-by-default
flag (or an explicit disable) into production.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "infra" / "scripts" / "deploy-aws-application.sh"


def test_fetch_filing_artifacts_remains_importable() -> None:
    from edgar_warehouse.bronze_filing_artifacts import fetch_filing_artifacts

    assert callable(fetch_filing_artifacts)


def test_daily_incremental_asl_does_not_pin_gated_capture_flag() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert "--enable-filing-artifact-gated-capture" not in source
    assert "--disable-filing-artifact-gated-capture" not in source
