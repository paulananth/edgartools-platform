"""drive-reference-catalog-discovery command module."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.drive_reference_catalog_discovery import (
    run_drive_reference_catalog_discovery,
)


def execute(args: Any) -> int:
    return run_drive_reference_catalog_discovery(args)
