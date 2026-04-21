"""daily-incremental command module."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.daily_index_sync import run_daily_incremental


def execute(args: Any) -> int:
    return run_daily_incremental(args)
