"""gold-refresh workflow entrypoint."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.command_runner import execute_standard_command


def run_gold_refresh(args: Any) -> int:
    return execute_standard_command("gold-refresh", args)
