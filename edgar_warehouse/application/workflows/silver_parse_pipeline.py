"""Silver parse-pipeline helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from edgar_warehouse.application import warehouse_orchestrator

if TYPE_CHECKING:
    from edgar_warehouse.bookkeeping.store import BookkeepingStore
    from edgar_warehouse.silver_landing_store import SilverLandingStore


def run_parse_pipeline(
    *,
    db: "SilverLandingStore",
    bookkeeping: "BookkeepingStore",
    accession_number: str,
    sync_run_id: str,
    submissions_lookup: Callable[[int], dict[str, Any] | None],
) -> int:
    return warehouse_orchestrator._run_parse_pipeline(
        db=db,
        bookkeeping=bookkeeping,
        accession_number=accession_number,
        sync_run_id=sync_run_id,
        submissions_lookup=submissions_lookup,
    )
