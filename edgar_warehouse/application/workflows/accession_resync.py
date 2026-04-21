"""Targeted accession and scope resync entrypoints."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.command_execution import execute_standard_command


def run_targeted_resync(args: Any) -> int:
    return execute_standard_command("targeted-resync", args)
