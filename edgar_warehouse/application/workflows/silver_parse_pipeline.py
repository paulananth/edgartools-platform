"""Silver parse-pipeline helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from edgar_warehouse.application import warehouse_orchestrator

if TYPE_CHECKING:
    from edgar_warehouse.silver_store import SilverDatabase


def run_parse_pipeline(*, db: "SilverDatabase", accession_number: str, sync_run_id: str) -> int:
    return warehouse_orchestrator._run_parse_pipeline(
        db=db,
        accession_number=accession_number,
        sync_run_id=sync_run_id,
    )
