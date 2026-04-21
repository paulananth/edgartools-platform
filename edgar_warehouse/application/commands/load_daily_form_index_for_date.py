"""load-daily-form-index-for-date command module."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.daily_index_sync import run_load_daily_form_index_for_date


def execute(args: Any) -> int:
    return run_load_daily_form_index_for_date(args)
