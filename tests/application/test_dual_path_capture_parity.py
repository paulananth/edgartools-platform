"""Ticket 53: drive legacy fetch_filing_artifacts and gated discovery
for the same CIK window, then feed both captured sets to Ticket 51's
compare_capture_snapshots.

Network is mocked at the SEC edge. Silver and the acquisition ledger are
real. The legacy side is not a second gated run relabeled "legacy".
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from edgar_warehouse.acquisition.capture_parity import APPLE_CIK
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


def _index_row(*, business_date: date, ordinal: int, cik: int, accession: str, form: str = "4") -> dict:
    return {
        "business_date": business_date,
        "source_year": business_date.year,
        "source_quarter": ((business_date.month - 1) // 3) + 1,
        "row_ordinal": ordinal,
        "form": form,
        "company_name": f"CIK {cik}",
        "cik": cik,
        "filing_date": business_date,
        "file_name": f"edgar/data/{cik}/{accession}.txt",
        "accession_number": accession,
        "filing_txt_url": (
            f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}.txt"
        ),
        "record_hash": f"hash-{accession}",
    }


def _seed_daily_index(tmp_path, *, business_date: str, rows: list[dict]) -> None:
    from edgar_warehouse.infrastructure.object_storage import StorageLocation
    from edgar_warehouse.silver_support.session import open_silver_database

    silver_root = StorageLocation(str(tmp_path / "silver"))
    db = open_silver_database(silver_root)
    try:
        db.merge_daily_index_filings(rows, sync_run_id="seed-run")
        db.upsert_daily_index_checkpoint(
            {
                "business_date": rows[0]["business_date"],
                "source_key": f"date:{business_date}",
                "source_url": "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/form.idx",
                "expected_available_at": datetime.now(UTC),
                "first_attempt_at": datetime.now(UTC),
                "last_attempt_at": datetime.now(UTC),
                "status": "succeeded",
                "row_count": len(rows),
                "distinct_cik_count": len({int(row["cik"]) for row in rows}),
                "distinct_accession_count": len(rows),
            }
        )
    finally:
        db.close()


class _FakeAttachment:
    def __init__(self, *, document: str, document_type: str, url: str) -> None:
        self.sequence_number = "1"
        self.document = document
        self.document_type = document_type
        self.description = "Primary document"
        self.url = url

    @property
    def content(self) -> bytes:
        raise AssertionError("legacy path must download raw SEC bytes, not edgartools content")


class _FakeAttachments:
    def __init__(self, items: list[_FakeAttachment]) -> None:
        self._items = items
        self.primary_documents = list(items)

    def __iter__(self):
        return iter(self._items)


def _get_filing_for_index_rows(rows: list[dict]):
    by_accession = {
        str(row["accession_number"]): _FakeAttachment(
            document="primary.xml",
            document_type=str(row["form"]),
            url=str(row["filing_txt_url"]),
        )
        for row in rows
    }

    def get_filing(accession_number: str):
        attachment = by_accession[accession_number]
        return SimpleNamespace(attachments=_FakeAttachments([attachment]))

    return get_filing


def test_dual_path_stage_one_apple_compare_passes(
    tmp_path, monkeypatch: pytest.MonkeyPatch, _acquisition_db: str
) -> None:
    from edgar_warehouse.acquisition.capture_parity import run_dual_path_filing_artifact_parity
    from edgar_warehouse.application.warehouse_orchestrator import _build_warehouse_context
    from edgar_warehouse.infrastructure.object_storage import StorageLocation
    from edgar_warehouse.silver_support.session import open_silver_database

    _set_warehouse_env(monkeypatch, tmp_path)
    business_date = "2026-08-26"
    business_date_value = date.fromisoformat(business_date)
    apple_accession = "0001140361-26-000001"
    rows = [
        _index_row(
            business_date=business_date_value,
            ordinal=1,
            cik=APPLE_CIK,
            accession=apple_accession,
        )
    ]
    _seed_daily_index(tmp_path, business_date=business_date, rows=rows)

    context = _build_warehouse_context("daily-incremental")
    db = open_silver_database(StorageLocation(str(tmp_path / "silver")))
    payload = b"<ownershipDocument>apple form 4</ownershipDocument>"
    download_bytes = Mock(return_value=payload)
    try:
        with patch(
            "edgar_warehouse.acquisition.source_family_registry.download_filing_content_bytes",
            download_bytes,
        ):
            result = run_dual_path_filing_artifact_parity(
                context=context,
                db=db,
                business_date=business_date,
                cik_list=(APPLE_CIK,),
                limit=1,
                sync_run_id="parity-run-1",
                download_bytes=download_bytes,
                get_filing=_get_filing_for_index_rows(rows),
            )
    finally:
        db.close()

    assert result.verdict.passed is True
    assert result.verdict.scope.cik_list == (APPLE_CIK,)
    assert result.verdict.out_of_scope_ciks == frozenset()
    apple_key = f"{APPLE_CIK}/{apple_accession}/full-submission-text"
    assert apple_key in result.verdict.logical_source_keys.shared
    assert result.legacy.cause_reference != result.gated.cause_reference
    assert result.legacy.path == "legacy"
    assert result.gated.path == "gated"
    assert any(artifact.decision_id is None for artifact in result.legacy.artifacts)
    assert any(artifact.decision_id for artifact in result.gated.artifacts)


def test_dual_path_does_not_process_unrelated_cik(
    tmp_path, monkeypatch: pytest.MonkeyPatch, _acquisition_db: str
) -> None:
    from edgar_warehouse.acquisition.capture_parity import run_dual_path_filing_artifact_parity
    from edgar_warehouse.application.warehouse_orchestrator import _build_warehouse_context
    from edgar_warehouse.infrastructure.object_storage import StorageLocation
    from edgar_warehouse.silver_support.session import open_silver_database

    _set_warehouse_env(monkeypatch, tmp_path)
    business_date = "2026-08-26"
    business_date_value = date.fromisoformat(business_date)
    other_cik = 789019
    universe = [APPLE_CIK] + [cik for cik in range(1, 200) if cik != APPLE_CIK]
    scoped = tuple(universe[:100])
    assert other_cik not in scoped
    rows = [
        _index_row(
            business_date=business_date_value,
            ordinal=1,
            cik=APPLE_CIK,
            accession="0001140361-26-000001",
        ),
        _index_row(
            business_date=business_date_value,
            ordinal=2,
            cik=other_cik,
            accession="0001140361-26-000009",
        ),
    ]
    _seed_daily_index(tmp_path, business_date=business_date, rows=rows)

    context = _build_warehouse_context("daily-incremental")
    db = open_silver_database(StorageLocation(str(tmp_path / "silver")))
    payload = b"<ownershipDocument>apple form 4</ownershipDocument>"
    download_bytes = Mock(return_value=payload)
    try:
        with (
            patch(
                "edgar_warehouse.acquisition.source_family_registry.download_filing_content_bytes",
                download_bytes,
            ),
            patch(
                "edgar_warehouse.application.workflows.drive_filing_discovery.SourceRegistryLedger.record_catchup_progress",
            ) as catchup,
        ):
            result = run_dual_path_filing_artifact_parity(
                context=context,
                db=db,
                business_date=business_date,
                cik_list=scoped + (other_cik,),
                limit=100,
                sync_run_id="parity-run-2",
                download_bytes=download_bytes,
                get_filing=_get_filing_for_index_rows(rows),
            )
    finally:
        db.close()

    assert result.verdict.scope.cik_list == scoped
    assert result.verdict.passed is True
    catchup.assert_not_called()
    assert other_cik not in {artifact.cik for artifact in result.legacy.artifacts}
    assert other_cik not in {artifact.cik for artifact in result.gated.artifacts}
    fetched_urls = [call.args[0] for call in download_bytes.call_args_list]
    assert fetched_urls
    assert all(f"/{other_cik}/" not in url for url in fetched_urls)
    assert any(f"/{APPLE_CIK}/" in url for url in fetched_urls)
