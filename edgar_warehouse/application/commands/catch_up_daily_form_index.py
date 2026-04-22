"""catch-up-daily-form-index command module."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.bronze_daily_index_ingest import run_catch_up_daily_form_index


def execute(args: Any) -> int:
    return run_catch_up_daily_form_index(args)
