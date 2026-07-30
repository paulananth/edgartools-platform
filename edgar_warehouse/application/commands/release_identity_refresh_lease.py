"""release-identity-refresh-lease command module."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.warehouse_orchestrator import run_command


def execute(args: Any) -> int:
    return run_command("release-identity-refresh-lease", args)
