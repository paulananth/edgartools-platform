"""capture-filing-artifact command module."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.capture_filing_artifact import (
    run_capture_filing_artifact,
)


def execute(args: Any) -> int:
    return run_capture_filing_artifact(args)
