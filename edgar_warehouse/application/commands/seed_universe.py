"""seed-universe command module."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.bronze_reference_ingest import run_seed_universe


def execute(args: Any) -> int:
    return run_seed_universe(args)
