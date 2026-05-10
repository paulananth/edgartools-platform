"""bootstrap-next command module."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.bronze_submissions_ingest import run_bootstrap_next


def execute(args: Any) -> int:
    return run_bootstrap_next(args)
