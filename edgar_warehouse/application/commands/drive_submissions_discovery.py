"""drive-submissions-discovery command module."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.drive_submissions_discovery import (
    run_drive_submissions_discovery,
)


def execute(args: Any) -> int:
    return run_drive_submissions_discovery(args)
