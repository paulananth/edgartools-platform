"""Release relationship-source import command."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.command_runner import execute_standard_command


def execute(args: Any) -> int:
    return execute_standard_command("ingest-relationship-sources", args)
