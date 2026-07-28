"""Fetch new Firm Roster monthly archives and stage a source manifest."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.command_runner import execute_standard_command


def execute(args: Any) -> int:
    return execute_standard_command("fetch-firm-roster", args)
