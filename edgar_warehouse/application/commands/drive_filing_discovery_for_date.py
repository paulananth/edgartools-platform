"""drive-filing-discovery-for-date command module."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.drive_filing_discovery import (
    run_drive_filing_discovery_for_date,
)


def execute(args: Any) -> int:
    return run_drive_filing_discovery_for_date(args)
