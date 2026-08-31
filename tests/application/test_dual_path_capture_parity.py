"""Ticket 53: real dual-path Decision 2 proof.

Hits SEC for both legacy fetch_filing_artifacts and gated discovery.
Skipped unless WAREHOUSE_LIVE_SEC=1 and EDGAR_IDENTITY contains an email.
CI does not run this — Decision 2 is a live 1-CIK (Apple) capture, not a
Mock-payload fixture.
"""
from __future__ import annotations

import os
from datetime import UTC, date, datetime

import pytest

from edgar_warehouse.acquisition.capture_parity import APPLE_CIK
from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.acquisition.registry_ledger import CoverageSpec, SourceRegistryLedger


def _require_live_sec() -> str:
    identity = os.environ.get("EDGAR_IDENTITY", "").strip()
    if os.environ.get("WAREHOUSE_LIVE_SEC") != "1":
        pytest.skip("Set WAREHOUSE_LIVE_SEC=1 to run the real SEC dual-path test")
    if "@" not in identity:
        pytest.skip("EDGAR_IDENTITY must include an email (SEC User-Agent)")
    return identity


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


def test_dual_path_live_sec_apple(
    tmp_path, monkeypatch: pytest.MonkeyPatch, _acquisition_db: str
) -> None:
    identity = _require_live_sec()
    from edgar_warehouse.acquisition.capture_parity import run_dual_path_filing_artifact_parity
    from edgar_warehouse.application.warehouse_orchestrator import (
        _build_warehouse_context,
        _load_daily_index_for_date,
    )
    from edgar_warehouse.infrastructure.object_storage import StorageLocation
    from edgar_warehouse.silver_support.session import open_silver_database

    monkeypatch.setenv("EDGAR_IDENTITY", identity)
    monkeypatch.setenv("WAREHOUSE_ENVIRONMENT", "test")
    monkeypatch.setenv("WAREHOUSE_RUNTIME_MODE", "bronze_capture")
    monkeypatch.setenv("WAREHOUSE_BRONZE_ROOT", str(tmp_path / "bronze"))
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", str(tmp_path / "warehouse"))
    monkeypatch.setenv("WAREHOUSE_SILVER_ROOT", str(tmp_path / "silver"))
    monkeypatch.setenv("SERVING_EXPORT_ROOT", str(tmp_path / "snowflake_export"))
    monkeypatch.delenv("SNOWFLAKE_EXPORT_ROOT", raising=False)
    monkeypatch.delenv("SILVER_LANDING_EXPORT_ROOT", raising=False)

    business_date = os.environ.get("WAREHOUSE_LIVE_SEC_DATE", "2026-08-27")
    context = _build_warehouse_context("daily-incremental")
    db = open_silver_database(StorageLocation(str(tmp_path / "silver")))

    # DuckDB Retirement Cutover Ticket 14: _load_daily_index_for_date now
    # reads/writes the bookkeeping store, not this SilverDatabase -- an
    # in-memory SQLite stand-in, same pattern as the _acquisition_db fixture
    # above (this test has no live Postgres bookkeeping instance available).
    from tests.support.bookkeeping_fixtures import bookkeeping_fixture

    bookkeeping = bookkeeping_fixture()
    try:
        index_result = _load_daily_index_for_date(
            context=context,
            bookkeeping=bookkeeping,
            target_date=date.fromisoformat(business_date),
            sync_run_id="parity-live-index",
            now=datetime.now(UTC),
            force=False,
        )
        assert index_result["status"] == "succeeded", index_result
        # Form 4 daily-index lists issuer and reporting owner as two lines that
        # share one accession. Silver's PK last-write-wins keeps the owner
        # CIK. Re-apply the issuer lines so a CIK-scoped Apple run still sees
        # the filing (real SEC bytes, not a fixture).
        from edgar_warehouse.infrastructure.filing_content_gateway import (
            download_filing_content_bytes,
        )
        from edgar_warehouse.loaders.bronze_daily_index_extractors import (
            stage_daily_index_filing_loader,
        )

        target_date = date.fromisoformat(business_date)
        quarter = ((target_date.month - 1) // 3) + 1
        idx_url = (
            "https://www.sec.gov/Archives/edgar/daily-index/"
            f"{target_date.year}/QTR{quarter}/form.{target_date.strftime('%Y%m%d')}.idx"
        )
        idx_bytes = download_filing_content_bytes(idx_url, identity)
        parsed = stage_daily_index_filing_loader(
            idx_bytes,
            target_date,
            "issuer-restore",
            "issuer-restore",
            idx_url,
        )
        issuer_rows = [row for row in parsed if int(row["cik"]) == APPLE_CIK]
        assert issuer_rows, f"Apple CIK {APPLE_CIK} missing from raw SEC daily index {business_date}"
        db.merge_daily_index_filings(issuer_rows, "issuer-restore")
        result = run_dual_path_filing_artifact_parity(
            context=context,
            db=db,
            business_date=business_date,
            cik_list=(APPLE_CIK,),
            limit=1,
            sync_run_id="parity-live-apple",
        )
    finally:
        db.close()

    assert result.legacy.path == "legacy"
    assert result.gated.path == "gated"
    assert result.legacy.cause_reference != result.gated.cause_reference
    assert result.verdict.scope.cik_list == (APPLE_CIK,)
    assert result.verdict.out_of_scope_ciks == frozenset()
    assert result.verdict.logical_source_keys.shared, (
        "Apple produced no shared captured keys on "
        f"{business_date}; pick another WAREHOUSE_LIVE_SEC_DATE"
    )
    assert result.verdict.passed is True
    assert any(artifact.decision_id is None for artifact in result.legacy.artifacts)
    assert any(artifact.decision_id for artifact in result.gated.artifacts)
