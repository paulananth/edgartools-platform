"""bootstrap-full command module."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.bronze_submissions_ingest import run_bootstrap_full


def execute(args: Any) -> int:
    return run_bootstrap_full(args)
