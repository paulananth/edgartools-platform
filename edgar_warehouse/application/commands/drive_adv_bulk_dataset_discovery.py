"""drive-adv-bulk-dataset-discovery command module."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.application.workflows.drive_adv_bulk_dataset_discovery import (
    run_drive_adv_bulk_dataset_discovery,
)


def execute(args: Any) -> int:
    return run_drive_adv_bulk_dataset_discovery(args)
