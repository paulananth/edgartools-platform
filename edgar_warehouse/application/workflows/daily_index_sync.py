"""Daily index workflow entrypoints."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.command_execution import execute_standard_command


def run_daily_incremental(args: Any) -> int:
    return execute_standard_command("daily-incremental", args)


def run_load_daily_form_index_for_date(args: Any) -> int:
    return execute_standard_command("load-daily-form-index-for-date", args)


def run_catch_up_daily_form_index(args: Any) -> int:
    return execute_standard_command("catch-up-daily-form-index", args)
