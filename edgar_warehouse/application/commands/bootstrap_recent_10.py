"""bootstrap-recent-10 command module."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.bronze_submissions_ingest import run_bootstrap_recent_10


def execute(args: Any) -> int:
    return run_bootstrap_recent_10(args)
