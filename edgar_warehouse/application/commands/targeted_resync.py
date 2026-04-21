"""targeted-resync command module."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.accession_resync import run_targeted_resync


def execute(args: Any) -> int:
    return run_targeted_resync(args)
