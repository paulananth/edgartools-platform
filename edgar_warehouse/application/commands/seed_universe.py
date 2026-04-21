"""seed-universe command module."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.reference_sync import run_seed_universe


def execute(args: Any) -> int:
    return run_seed_universe(args)
