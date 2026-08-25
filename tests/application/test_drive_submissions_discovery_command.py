from __future__ import annotations

import hashlib
import json
from argparse import Namespace
from datetime import date
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
    _activate_submissions_registry(engine)
    return url


def _activate_submissions_registry(engine) -> None:
    """Ticket 21: no acquisition command runs without an active Source
    Family Registry version covering it -- mirrors
    test_drive_filing_discovery_command.py's own
    _activate_filing_artifact_registry helper exactly, for the submissions
    family instead.
    """

    ledger = SourceRegistryLedger(engine)
    version = ledger.open_draft(
        [
            CoverageSpec(
                source_family="submissions",
                coverage_action="add",
                acquisition_mode="on_demand_fetch",
                completeness_policy="valid_json_object",
                discovery_policy="cik_universe_driven",
                required_producers=("sec_company", "sec_company_filing"),
                coverage_start_date=date(2026, 1, 1),
                catchup_required_through_date=date(2026, 1, 1),
            )
        ],
        operator_authorization_reference="test-bootstrap",
    )
    ledger.record_catchup_progress("submissions", date(2026, 1, 1))
    activated = ledger.activate(version.version_id)
    assert activated.status == "active"


def _set_warehouse_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("EDGAR_IDENTITY", "EdgarTools Platform test@example.com")
    monkeypatch.setenv("WAREHOUSE_ENVIRONMENT", "test")
    monkeypatch.setenv("WAREHOUSE_RUNTIME_MODE", "infrastructure_validation")
    monkeypatch.setenv("WAREHOUSE_BRONZE_ROOT", str(tmp_path / "bronze"))
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", str(tmp_path / "warehouse"))
    monkeypatch.setenv("WAREHOUSE_SILVER_ROOT", str(tmp_path / "silver"))
    for variable in ("SERVING_EXPORT_ROOT", "SNOWFLAKE_EXPORT_ROOT", "SILVER_LANDING_EXPORT_ROOT"):
        monkeypatch.delenv(variable, raising=False)


def _main_payload(*, files: list[str] | None = None) -> dict[str, object]:
    return {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "filings": {
            "recent": {
                "accessionNumber": ["0000320193-26-000001"],
                "filingDate": ["2026-08-01"],
                "reportDate": [""],
                "acceptanceDateTime": ["2026-08-01T00:00:00.000Z"],
                "act": ["34"],
                "form": ["4"],
                "fileNumber": [""],
                "filmNumber": [""],
                "items": [""],
                "size": [1000],
                "isXBRL": [0],
                "isInlineXBRL": [0],
                "primaryDocument": ["doc.xml"],
                "primaryDocDescription": [""],
            },
            "files": [{"name": name} for name in (files or [])],
        },
    }


def _pagination_payload(*, accession: str) -> dict[str, object]:
    return {
        "filings": {
            "accessionNumber": [accession],
            "filingDate": ["2020-01-01"],
            "reportDate": [""],
            "acceptanceDateTime": ["2020-01-01T00:00:00.000Z"],
            "act": ["34"],
            "form": ["4"],
            "fileNumber": [""],
            "filmNumber": [""],
            "items": [""],
            "size": [500],
            "isXBRL": [0],
            "isInlineXBRL": [0],
            "primaryDocument": ["doc.xml"],
            "primaryDocDescription": [""],
        }
    }


def test_drive_submissions_discovery_captures_main_and_pagination_end_to_end(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], _acquisition_db: str
) -> None:
    from edgar_warehouse.application.command_router import run_command
    from edgar_warehouse.infrastructure.sec_client import build_submission_pagination_url

    _set_warehouse_env(monkeypatch, tmp_path)

    main_payload = _main_payload(files=["CIK0000320193-submissions-001.json"])
    pagination_payload = _pagination_payload(accession="0000320193-19-000042")
    main_bytes = json.dumps(main_payload).encode("utf-8")
    pagination_bytes = json.dumps(pagination_payload).encode("utf-8")

    main_url = "https://data.sec.gov/submissions/CIK0000320193.json"
    pagination_url = build_submission_pagination_url("CIK0000320193-submissions-001.json")

    def _fake_download(url: str, identity: str) -> bytes:
        if url == main_url:
            return main_bytes
        if url == pagination_url:
            return pagination_bytes
        raise AssertionError(f"unexpected URL: {url}")

    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_sec_catalog_bytes",
        side_effect=_fake_download,
    ) as mocked_fetch:
        exit_code = run_command(
            "drive-submissions-discovery",
            Namespace(
                cik_list=[320193],
                tracking_status_filter="active",
                limit=None,
                worker_id="submissions-worker-1",
                lease_seconds=None,
                registry_version=None,
                run_id="run-submissions-1",
            ),
        )

    assert exit_code == 0
    assert mocked_fetch.call_count == 2

    result = json.loads(capsys.readouterr().out)
    assert result["cik_count"] == 1
    assert result["interval_complete"] is True
    assert result["silver_interval_complete"] is True
    assert result["unsettled_ciks"] == []

    outcome = result["outcomes"][0]
    assert outcome["cik"] == 320193
    assert outcome["fetch_state"] == "CAPTURED"
    assert outcome["network_fetched"] is True
    assert outcome["pagination_file_count"] == 1
    assert outcome["pagination_complete"] is True
    assert outcome["silver_outcome"] == "PUBLISHED"
    assert outcome["silver_error"] is None

    main_hash = hashlib.sha256(main_bytes).hexdigest()
    pagination_hash = hashlib.sha256(pagination_bytes).hexdigest()
    assert (tmp_path / "bronze" / "submissions" / main_hash).read_bytes() == main_bytes
    assert (tmp_path / "bronze" / "submissions" / pagination_hash).read_bytes() == pagination_bytes

    from edgar_warehouse.infrastructure.object_storage import StorageLocation
    from edgar_warehouse.silver_support.session import open_silver_database

    silver_root = StorageLocation(str(tmp_path / "silver"))
    verify_db = open_silver_database(silver_root)
    try:
        company = verify_db.get_company(320193)
        assert company is not None
        assert company["entity_name"] == "Apple Inc."
        recent_filing = verify_db.get_filing("0000320193-26-000001")
        assert recent_filing is not None
        pagination_filing = verify_db.get_filing("0000320193-19-000042")
        assert pagination_filing is not None
    finally:
        verify_db.close()

    run_manifest_path = (
        tmp_path
        / "bronze"
        / "runs"
        / "drive-submissions-discovery"
        / "run-submissions-1"
        / "run_manifest.json"
    )
    assert run_manifest_path.exists()


def test_drive_submissions_discovery_replay_performs_no_second_network_fetch(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], _acquisition_db: str
) -> None:
    from edgar_warehouse.application.command_router import run_command
    from edgar_warehouse.infrastructure.sec_client import build_submission_pagination_url

    _set_warehouse_env(monkeypatch, tmp_path)

    main_payload = _main_payload(files=["CIK0000320193-submissions-001.json"])
    pagination_payload = _pagination_payload(accession="0000320193-19-000042")
    main_bytes = json.dumps(main_payload).encode("utf-8")
    pagination_bytes = json.dumps(pagination_payload).encode("utf-8")
    main_url = "https://data.sec.gov/submissions/CIK0000320193.json"
    pagination_url = build_submission_pagination_url("CIK0000320193-submissions-001.json")

    def _fake_download(url: str, identity: str) -> bytes:
        if url == main_url:
            return main_bytes
        if url == pagination_url:
            return pagination_bytes
        raise AssertionError(f"unexpected URL: {url}")

    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_sec_catalog_bytes",
        side_effect=_fake_download,
    ) as mocked_fetch:
        for run_id in ("run-submissions-1", "run-submissions-2"):
            exit_code = run_command(
                "drive-submissions-discovery",
                Namespace(
                    cik_list=[320193],
                    tracking_status_filter="active",
                    limit=None,
                    worker_id=f"submissions-worker-{run_id}",
                    lease_seconds=None,
                    registry_version=None,
                    run_id=run_id,
                ),
            )
            assert exit_code == 0

    # Two total network calls (main + pagination) across BOTH runs -- the
    # second run performs zero additional network fetches.
    assert mocked_fetch.call_count == 2


def test_drive_submissions_discovery_fails_closed_on_an_unsupported_required_producers_set(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ticket 32 bullet 1's pattern, ported: required_producers is a real
    gate threaded from the registry through to submissions_silver_
    acceptance -- a covered family declaring a producer set this Strategy's
    write bodies cannot serve must fail closed, not silently ignore the
    undeclared producer.
    """

    from sqlalchemy import create_engine

    from edgar_warehouse.acquisition.models import AcquisitionBase
    from edgar_warehouse.acquisition.registry_ledger import CoverageSpec, SourceRegistryLedger
    from edgar_warehouse.acquisition.submissions_silver_acceptance import (
        UnsupportedRequiredProducers,
    )
    from edgar_warehouse.application.command_router import run_command

    db_path = tmp_path / "mdm.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    AcquisitionBase.metadata.create_all(engine)
    monkeypatch.setenv("MDM_DATABASE_URL", url)

    ledger = SourceRegistryLedger(engine)
    version = ledger.open_draft(
        [
            CoverageSpec(
                source_family="submissions",
                coverage_action="add",
                acquisition_mode="on_demand_fetch",
                completeness_policy="valid_json_object",
                discovery_policy="cik_universe_driven",
                required_producers=("some_other_table",),
                coverage_start_date=date(2026, 1, 1),
                catchup_required_through_date=date(2026, 1, 1),
            )
        ],
        operator_authorization_reference="test-bootstrap",
    )
    ledger.record_catchup_progress("submissions", date(2026, 1, 1))
    ledger.activate(version.version_id)

    _set_warehouse_env(monkeypatch, tmp_path)

    # The upfront required_producers check happens before any candidate is
    # attempted, so it must raise even with zero real network activity --
    # mock the fetch anyway so this test never depends on live network
    # access, regardless of that ordering.
    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_sec_catalog_bytes",
        return_value=b'{"cik": "0000320193", "filings": {"recent": {"accessionNumber": []}, "files": []}}',
    ), pytest.raises(UnsupportedRequiredProducers):
        run_command(
            "drive-submissions-discovery",
            Namespace(
                cik_list=[320193],
                tracking_status_filter="active",
                limit=None,
                worker_id="submissions-worker-1",
                lease_seconds=None,
                registry_version=None,
                run_id="run-submissions-1",
            ),
        )
