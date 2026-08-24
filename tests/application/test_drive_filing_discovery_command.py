from __future__ import annotations

import hashlib
import json
from argparse import Namespace
from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest

from edgar_warehouse.acquisition.models import AcquisitionBase


@pytest.fixture()
def _acquisition_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    from sqlalchemy import create_engine

    db_path = tmp_path / "mdm.db"
    url = f"sqlite:///{db_path}"
    AcquisitionBase.metadata.create_all(create_engine(url))
    monkeypatch.setenv("MDM_DATABASE_URL", url)
    return url


def _set_warehouse_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("EDGAR_IDENTITY", "EdgarTools Platform test@example.com")
    monkeypatch.setenv("WAREHOUSE_ENVIRONMENT", "test")
    monkeypatch.setenv("WAREHOUSE_RUNTIME_MODE", "infrastructure_validation")
    monkeypatch.setenv("WAREHOUSE_BRONZE_ROOT", str(tmp_path / "bronze"))
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", str(tmp_path / "warehouse"))
    monkeypatch.setenv("WAREHOUSE_SILVER_ROOT", str(tmp_path / "silver"))
    for variable in ("SERVING_EXPORT_ROOT", "SNOWFLAKE_EXPORT_ROOT", "SILVER_LANDING_EXPORT_ROOT"):
        monkeypatch.delenv(variable, raising=False)


def _seed_daily_index(tmp_path, *, business_date: str, sealed: bool) -> None:
    from edgar_warehouse.infrastructure.object_storage import StorageLocation
    from edgar_warehouse.silver_support.session import open_silver_database

    silver_root = StorageLocation(str(tmp_path / "silver"))
    db = open_silver_database(silver_root)
    try:
        business_date_value = date.fromisoformat(business_date)
        rows = [
            {
                "business_date": business_date_value,
                "source_year": business_date_value.year,
                "source_quarter": ((business_date_value.month - 1) // 3) + 1,
                "row_ordinal": 1,
                "form": "4",
                "company_name": "Apple Inc.",
                "cik": 320193,
                "filing_date": business_date_value,
                "file_name": "edgar/data/320193/0001140361-26-000001.txt",
                "accession_number": "0001140361-26-000001",
                "filing_txt_url": (
                    "https://www.sec.gov/Archives/edgar/data/320193/"
                    "0001140361-26-000001.txt"
                ),
                "record_hash": "hash-1",
            },
            {
                "business_date": business_date_value,
                "source_year": business_date_value.year,
                "source_quarter": ((business_date_value.month - 1) // 3) + 1,
                "row_ordinal": 2,
                "form": "10-K",
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
            },
        ]
        db.merge_daily_index_filings(rows, sync_run_id="seed-run")
        db.upsert_daily_index_checkpoint(
            {
                "business_date": business_date_value,
                "source_key": f"date:{business_date}",
                "source_url": "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/form.idx",
                "expected_available_at": datetime.now(UTC),
                "first_attempt_at": datetime.now(UTC),
                "last_attempt_at": datetime.now(UTC),
                "status": "succeeded" if sealed else "waiting_for_publish",
                "row_count": 2,
                "distinct_cik_count": 2,
                "distinct_accession_count": 2,
            }
        )
    finally:
        db.close()


def test_drive_filing_discovery_captures_new_filing_and_excludes_out_of_scope_form(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], _acquisition_db: str
) -> None:
    from edgar_warehouse.application.command_router import run_command

    _set_warehouse_env(monkeypatch, tmp_path)
    _seed_daily_index(tmp_path, business_date="2026-08-24", sealed=True)
    payload = b"<ownershipDocument>real Form 4 bytes</ownershipDocument>"

    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_filing_content_bytes",
        return_value=payload,
    ) as mocked_fetch:
        exit_code = run_command(
            "drive-filing-discovery-for-date",
            Namespace(
                business_date="2026-08-24",
                worker_id="discovery-worker-1",
                lease_seconds=None,
                registry_version=None,
                run_id="run-discovery-1",
            ),
        )

    assert exit_code == 0
    # Exactly one network fetch: the in-scope Form 4, never the excluded 10-K.
    mocked_fetch.assert_called_once_with(
        "https://www.sec.gov/Archives/edgar/data/320193/0001140361-26-000001.txt",
        "EdgarTools Platform test@example.com",
    )

    result = json.loads(capsys.readouterr().out)
    assert result["business_date"] == "2026-08-24"
    assert result["candidate_count"] == 2
    assert result["interval_complete"] is True
    assert result["unsettled_candidate_ids"] == []
    # Ticket 29's wiring: capture completing isn't the whole story anymore --
    # the revision/processing/Silver chain must also settle.
    assert result["silver_interval_complete"] is True
    assert result["silver_unsettled_candidate_ids"] == []

    outcomes = {o["accession_number"]: o for o in result["outcomes"]}
    captured = outcomes["0001140361-26-000001"]
    assert captured["in_scope"] is True
    assert captured["network_fetched"] is True
    assert captured["fetch_state"] == "CAPTURED"
    assert captured["revision_id"] is not None
    assert captured["processing_disposition"] == "PROCESS_REQUIRED"
    assert captured["silver_outcome"] == "PUBLISHED"
    assert captured["silver_error"] is None

    excluded = outcomes["0001140361-26-000002"]
    assert excluded["in_scope"] is False
    assert excluded["network_fetched"] is False
    assert excluded["fetch_disposition"] == "OUT_OF_SCOPE"
    # Never carried forward -- nothing was ever captured for it.
    assert excluded["revision_id"] is None
    assert excluded["silver_outcome"] is None

    expected_hash = hashlib.sha256(payload).hexdigest()
    stored = (tmp_path / "bronze" / "filing_artifact" / expected_hash).read_bytes()
    assert stored == payload
    # The excluded candidate produced no Bronze object at all.
    assert len(list((tmp_path / "bronze" / "filing_artifact").iterdir())) == 1

    # Durable external evidence (Ticket 19 bullet 5): read sec_raw_object
    # back independently from the local Silver database this run wrote to,
    # not via anything the command's own JSON payload claimed.
    from edgar_warehouse.infrastructure.object_storage import StorageLocation
    from edgar_warehouse.silver_support.session import open_silver_database

    silver_root = StorageLocation(str(tmp_path / "silver"))
    verify_db = open_silver_database(silver_root)
    try:
        raw_object = verify_db.get_raw_object(expected_hash)
        assert raw_object is not None
        assert raw_object["sha256"] == expected_hash
        assert raw_object["accession_number"] == "0001140361-26-000001"
        assert raw_object["cik"] == 320193
    finally:
        verify_db.close()

    run_manifest_path = (
        tmp_path
        / "bronze"
        / "runs"
        / "drive-filing-discovery-for-date"
        / "run-discovery-1"
        / "run_manifest.json"
    )
    assert run_manifest_path.exists()
    run_manifest_doc = json.loads(run_manifest_path.read_text())
    assert run_manifest_doc["command"] == "drive-filing-discovery-for-date"
    assert run_manifest_doc["scope"] == {"business_date": "2026-08-24"}


def test_drive_filing_discovery_replay_performs_no_second_network_fetch(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], _acquisition_db: str
) -> None:
    from edgar_warehouse.application.command_router import run_command

    _set_warehouse_env(monkeypatch, tmp_path)
    _seed_daily_index(tmp_path, business_date="2026-08-24", sealed=True)
    payload = b"<ownershipDocument>real Form 4 bytes</ownershipDocument>"

    revision_ids: list[str] = []
    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_filing_content_bytes",
        return_value=payload,
    ) as mocked_fetch:
        for run_id in ("run-discovery-1", "run-discovery-2"):
            exit_code = run_command(
                "drive-filing-discovery-for-date",
                Namespace(
                    business_date="2026-08-24",
                    worker_id=f"discovery-worker-{run_id}",
                    lease_seconds=None,
                    registry_version=None,
                    run_id=run_id,
                ),
            )
            assert exit_code == 0
            result = json.loads(capsys.readouterr().out)
            # Ticket 29's own no-op-replay acceptance criterion, proven here
            # at the command level: both runs report the full chain settled,
            # and the second run reuses the exact same already-materialized
            # revision rather than creating a new one.
            assert result["silver_interval_complete"] is True
            captured = next(
                o for o in result["outcomes"] if o["accession_number"] == "0001140361-26-000001"
            )
            assert captured["silver_outcome"] == "PUBLISHED"
            revision_ids.append(captured["revision_id"])

    mocked_fetch.assert_called_once()
    assert revision_ids[0] == revision_ids[1]


def test_drive_filing_discovery_fails_closed_when_discovery_is_not_sealed(
    tmp_path, monkeypatch: pytest.MonkeyPatch, _acquisition_db: str
) -> None:
    from edgar_warehouse.application.command_router import run_command
    from edgar_warehouse.application.errors import WarehouseRuntimeError

    _set_warehouse_env(monkeypatch, tmp_path)
    _seed_daily_index(tmp_path, business_date="2026-08-24", sealed=False)

    with pytest.raises(WarehouseRuntimeError, match="No sealed discovery observation"):
        run_command(
            "drive-filing-discovery-for-date",
            Namespace(
                business_date="2026-08-24",
                worker_id="discovery-worker-1",
                lease_seconds=None,
                registry_version=None,
                run_id="run-discovery-1",
            ),
        )


def test_drive_filing_discovery_fails_closed_when_no_discovery_observation_exists(
    tmp_path, monkeypatch: pytest.MonkeyPatch, _acquisition_db: str
) -> None:
    from edgar_warehouse.application.command_router import run_command
    from edgar_warehouse.application.errors import WarehouseRuntimeError

    _set_warehouse_env(monkeypatch, tmp_path)

    with pytest.raises(WarehouseRuntimeError, match="No sealed discovery observation"):
        run_command(
            "drive-filing-discovery-for-date",
            Namespace(
                business_date="2026-08-24",
                worker_id="discovery-worker-1",
                lease_seconds=None,
                registry_version=None,
                run_id="run-discovery-1",
            ),
        )
