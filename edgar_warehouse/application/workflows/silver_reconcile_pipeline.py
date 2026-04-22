"""Reconcile workflow entrypoints."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.command_runner import execute_standard_command


def run_full_reconcile(args: Any) -> int:
    return execute_standard_command("full-reconcile", args)
