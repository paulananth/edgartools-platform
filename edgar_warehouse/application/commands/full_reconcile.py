"""full-reconcile command module."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.reconcile_pipeline import run_full_reconcile


def execute(args: Any) -> int:
    return run_full_reconcile(args)
