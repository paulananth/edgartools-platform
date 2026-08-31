"""Ticket 46 (change-propagation map): filing_artifact's gated discovery/
capture, run in-process from daily-incremental's own per-date loop.

Unlike tests/unit/test_daily_incremental_gated_capture.py (which mocks the
dispatcher entirely to prove daily-incremental's own gating/isolation
behavior), this exercises the real capture path end-to-end -- real SQLite
acquisition ledger, real SilverDatabase, mocked-only-at-the-network-edge --
mirroring tests/application/test_drive_adv_filing_discovery_command.py's
own fixture shape, since Ticket 46's wrapper is a thin dispatcher onto the
exact same shared core that command already proves live.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest

from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.acquisition.registry_ledger import CoverageSpec, SourceRegistryLedger


@pytest.fixture()
def _acquisition_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    from sqlalchemy import create_engine

    db_path = tmp_path / "mdm.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    AcquisitionBase.metadata.create_all(engine)
    monkeypatch.setenv("MDM_DATABASE_URL", url)

    ledger = SourceRegistryLedger(engine)
    version = ledger.open_draft(
        [
            CoverageSpec(
                source_family="filing_artifact",
                coverage_action="add",
                in_scope_forms=("3", "3/A", "4", "4/A", "5", "5/A"),
                acquisition_mode="on_demand_fetch",
                completeness_policy="non_empty_payload",
                discovery_policy="daily_index_driven",
                required_producers=("sec_raw_object",),
                coverage_start_date=date(2026, 1, 1),
                catchup_required_through_date=date(2026, 1, 1),
            )
        ],
        operator_authorization_reference="test-bootstrap",
    )
    ledger.record_catchup_progress("filing_artifact", date(2026, 1, 1))
    activated = ledger.activate(version.version_id)
    assert activated.status == "active"
    return url


def _set_warehouse_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("EDGAR_IDENTITY", "EdgarTools Platform test@example.com")
    monkeypatch.setenv("WAREHOUSE_ENVIRONMENT", "test")
    monkeypatch.setenv("WAREHOUSE_RUNTIME_MODE", "infrastructure_validation")
    monkeypatch.setenv("WAREHOUSE_BRONZE_ROOT", str(tmp_path / "bronze"))
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", str(tmp_path / "warehouse"))
    monkeypatch.setenv("WAREHOUSE_SILVER_ROOT", str(tmp_path / "silver"))
    monkeypatch.setenv("SERVING_EXPORT_ROOT", str(tmp_path / "snowflake_export"))
    monkeypatch.delenv("SNOWFLAKE_EXPORT_ROOT", raising=False)
    monkeypatch.delenv("SILVER_LANDING_EXPORT_ROOT", raising=False)


def _seed_daily_index(bookkeeping, *, business_date: str) -> None:
    # DuckDB Retirement Cutover Ticket 15: stg_daily_index_filing/
    # sec_daily_index_checkpoint now live in the bookkeeping store, not
    # SilverDatabase -- seed there, matching what
    # run_filing_artifact_gated_capture_for_business_date now reads from.
    business_date_value = date.fromisoformat(business_date)
    bookkeeping.merge_daily_index_filings(
        [
            {
                "business_date": business_date_value,
                "source_year": business_date_value.year,
                "source_quarter": ((business_date_value.month - 1) // 3) + 1,
                "row_ordinal": 1,
                "form": "4",
                "company_name": "Widget Corp.",
                "cik": 999999,
                "filing_date": business_date_value,
                "file_name": "edgar/data/999999/0001140361-26-000002.txt",
                "accession_number": "0001140361-26-000002",
                "filing_txt_url": (
                    "https://www.sec.gov/Archives/edgar/data/999999/"
                    "0001140361-26-000002.txt"
                ),
                "record_hash": "hash-2",
            }
        ],
        sync_run_id="seed-run",
    )
    bookkeeping.upsert_daily_index_checkpoint(
        {
            "business_date": business_date_value,
            "source_key": f"date:{business_date}",
            "source_url": "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/form.idx",
            "expected_available_at": datetime.now(UTC),
            "first_attempt_at": datetime.now(UTC),
            "last_attempt_at": datetime.now(UTC),
            "status": "succeeded",
            "row_count": 1,
            "distinct_cik_count": 1,
            "distinct_accession_count": 1,
        }
    )


def test_gated_capture_reuses_already_open_db_and_captures_real_filing(
    tmp_path, monkeypatch: pytest.MonkeyPatch, _acquisition_db: str
) -> None:
    from edgar_warehouse.application.warehouse_orchestrator import _build_warehouse_context
    from edgar_warehouse.application.workflows.drive_filing_discovery import (
        run_filing_artifact_gated_capture_for_business_date,
    )
    from edgar_warehouse.infrastructure.object_storage import StorageLocation
    from edgar_warehouse.silver_support.session import open_silver_database
    from tests.support.bookkeeping_fixtures import bookkeeping_fixture

    _set_warehouse_env(monkeypatch, tmp_path)
    bookkeeping = bookkeeping_fixture()
    _seed_daily_index(bookkeeping, business_date="2026-08-27")

    context = _build_warehouse_context("daily-incremental")
    silver_root = StorageLocation(str(tmp_path / "silver"))
    db = open_silver_database(silver_root)
    payload = b"<ownershipDocument>form4 bytes</ownershipDocument>"
    try:
        with patch(
            "edgar_warehouse.acquisition.source_family_registry.download_filing_content_bytes",
            return_value=payload,
        ) as mocked_fetch:
            # The whole point: this call does NOT hydrate or publish itself
            # (daily-incremental's own already-open db is passed straight
            # through) -- it is a bare capture call against a db the caller
            # opened and will close/publish on its own.
            outcome = run_filing_artifact_gated_capture_for_business_date(
                context=context, db=db, bookkeeping=bookkeeping, business_date="2026-08-27", run_id="daily-run-1",
            )
    finally:
        db.close()

    mocked_fetch.assert_called_once_with(
        "https://www.sec.gov/Archives/edgar/data/999999/0001140361-26-000002.txt",
        "EdgarTools Platform test@example.com",
    )
    assert outcome.interval_complete is True
    assert outcome.silver_result.interval_complete is True

    # Diffability (Ticket 10 Decision 2's requirement): the acquisition
    # ledger row this run produced is queryable by business_date + family via
    # its deterministic candidate_id -- filing_artifact keeps its legacy,
    # family-less format (see discovery_candidate_id's own backward-
    # compatibility note).
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from edgar_warehouse.acquisition.models import SourceFetchDecisionRecord
    from edgar_warehouse.mdm.database import get_engine

    with Session(get_engine()) as session:
        rows = session.execute(
            select(SourceFetchDecisionRecord).where(
                SourceFetchDecisionRecord.candidate_id.like("filing-discovery/2026-08-27/%")
            )
        ).scalars().all()
    assert [row.candidate_id for row in rows] == [
        "filing-discovery/2026-08-27/0001140361-26-000002"
    ]
