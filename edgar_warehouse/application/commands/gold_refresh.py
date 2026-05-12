"""gold-refresh command module."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.gold_refresh import run_gold_refresh


def execute(args: Any) -> int:
    return run_gold_refresh(args)
