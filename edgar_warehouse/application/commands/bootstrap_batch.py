"""bootstrap-batch command module."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.submissions_sync import run_bootstrap_batch


def execute(args: Any) -> int:
    return run_bootstrap_batch(args)
