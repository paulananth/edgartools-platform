"""Submission-oriented workflow entrypoints."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.command_execution import execute_standard_command


def run_bootstrap_full(args: Any) -> int:
    return execute_standard_command("bootstrap-full", args)


def run_bootstrap_recent_10(args: Any) -> int:
    return execute_standard_command("bootstrap-recent-10", args)


def run_bootstrap_batch(args: Any) -> int:
    return execute_standard_command("bootstrap-batch", args)
