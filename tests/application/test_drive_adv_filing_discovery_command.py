"""Ticket 24 bullet 4: `drive-adv-filing-discovery-for-date` closes the last
gap the ticket left honestly partial -- ADV filing documents (Form ADV and
its siblings) now flow through the same ledger-gated daily-index-driven
capture path as ownership forms, instead of the pre-Ticket-14 legacy
`_run_parse_adv_bronze` path. Mirrors
`test_drive_filing_discovery_command.py`'s own shape closely, since this
command is the generalized `drive_filing_discovery` workflow parameterized
for the `adv_filing` source family rather than a new implementation.
"""

from __future__ import annotations

import hashlib
import json
from argparse import Namespace
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
    _activate_adv_filing_registry(engine)
    return url


def _activate_adv_filing_registry(engine) -> None:
    """Mirrors the real bootstrap's `adv_filing` coverage row
    (`infra/scripts/bootstrap-source-family-registry.sh`) -- own
    `in_scope_forms` (the 9 ADV form variants), reusing `FilingArtifactPolicy`
    under a distinct family so ADV accessions never overlap filing_artifact's
    own coverage.
    """

    ledger = SourceRegistryLedger(engine)
    version = ledger.open_draft(
        [
            CoverageSpec(
                source_family="adv_filing",
                coverage_action="add",
                in_scope_forms=(
                    "ADV",
                    "ADV/A",
                    "ADV-E",
                    "ADV-E/A",
                    "ADV-H",
                    "ADV-H/A",
                    "ADV-NR",
                    "ADV-W",
                    "ADV-W/A",
                ),
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
    ledger.record_catchup_progress("adv_filing", date(2026, 1, 1))
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
                "form": "ADV",
                "company_name": "Example Advisers LLC",
                "cik": 1234567,
                "filing_date": business_date_value,
                "file_name": "edgar/data/1234567/0001140361-26-000003.txt",
                "accession_number": "0001140361-26-000003",
                "filing_txt_url": (
                    "https://www.sec.gov/Archives/edgar/data/1234567/"
                    "0001140361-26-000003.txt"
                ),
                "record_hash": "hash-adv",
            },
            {
                # A same-day Form 4: must stay out of scope for adv_filing
                # even though it comes from the exact same sealed daily-index
                # observation -- proves the two families' in_scope_forms
                # partition the same rows without any cross-family leakage.
                "business_date": business_date_value,
                "source_year": business_date_value.year,
                "source_quarter": ((business_date_value.month - 1) // 3) + 1,
                "row_ordinal": 2,
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


def test_drive_adv_filing_discovery_captures_adv_form_and_excludes_ownership_form(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], _acquisition_db: str
) -> None:
    from edgar_warehouse.application.command_router import run_command

    _set_warehouse_env(monkeypatch, tmp_path)
    _seed_daily_index(tmp_path, business_date="2026-08-24", sealed=True)
    payload = b"<adv>real Form ADV bytes</adv>"

    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_filing_content_bytes",
        return_value=payload,
    ) as mocked_fetch:
        exit_code = run_command(
            "drive-adv-filing-discovery-for-date",
            Namespace(
                business_date="2026-08-24",
                worker_id="adv-discovery-worker-1",
                lease_seconds=None,
                registry_version=None,
                run_id="run-adv-discovery-1",
            ),
        )

    assert exit_code == 0
    # Exactly one network fetch: the in-scope Form ADV, never the Form 4 --
    # in_scope_forms partitions the shared sealed daily-index rows correctly.
    mocked_fetch.assert_called_once_with(
        "https://www.sec.gov/Archives/edgar/data/1234567/0001140361-26-000003.txt",
        "EdgarTools Platform test@example.com",
    )

    result = json.loads(capsys.readouterr().out)
    assert result["business_date"] == "2026-08-24"
    assert result["candidate_count"] == 2
    assert result["interval_complete"] is True
    assert result["silver_interval_complete"] is True

    outcomes = {o["accession_number"]: o for o in result["outcomes"]}
    captured = outcomes["0001140361-26-000003"]
    assert captured["in_scope"] is True
    assert captured["network_fetched"] is True
    assert captured["fetch_state"] == "CAPTURED"
    assert captured["silver_outcome"] == "PUBLISHED"

    excluded = outcomes["0001140361-26-000002"]
    assert excluded["in_scope"] is False
    assert excluded["network_fetched"] is False
    assert excluded["fetch_disposition"] == "OUT_OF_SCOPE"

    expected_hash = hashlib.sha256(payload).hexdigest()
    # Bronze is partitioned per source_family: adv_filing lands in its own
    # prefix, distinct from filing_artifact's -- confirms this new family
    # cannot collide with the existing driver's own evidence.
    stored = (tmp_path / "bronze" / "adv_filing" / expected_hash).read_bytes()
    assert stored == payload

    run_manifest_path = (
        tmp_path
        / "bronze"
        / "runs"
        / "drive-adv-filing-discovery-for-date"
        / "run-adv-discovery-1"
        / "run_manifest.json"
    )
    assert run_manifest_path.exists()
    run_manifest_doc = json.loads(run_manifest_path.read_text())
    assert run_manifest_doc["command"] == "drive-adv-filing-discovery-for-date"
    assert run_manifest_doc["scope"] == {"business_date": "2026-08-24"}


def test_drive_adv_filing_discovery_replay_performs_no_second_network_fetch(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], _acquisition_db: str
) -> None:
    from edgar_warehouse.application.command_router import run_command

    _set_warehouse_env(monkeypatch, tmp_path)
    _seed_daily_index(tmp_path, business_date="2026-08-24", sealed=True)
    payload = b"<adv>real Form ADV bytes</adv>"

    revision_ids: list[str] = []
    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_filing_content_bytes",
        return_value=payload,
    ) as mocked_fetch:
        for run_id in ("run-adv-discovery-1", "run-adv-discovery-2"):
            exit_code = run_command(
                "drive-adv-filing-discovery-for-date",
                Namespace(
                    business_date="2026-08-24",
                    worker_id=f"adv-discovery-worker-{run_id}",
                    lease_seconds=None,
                    registry_version=None,
                    run_id=run_id,
                ),
            )
            assert exit_code == 0
            result = json.loads(capsys.readouterr().out)
            assert result["silver_interval_complete"] is True
            captured = next(
                o for o in result["outcomes"] if o["accession_number"] == "0001140361-26-000003"
            )
            assert captured["silver_outcome"] == "PUBLISHED"
            revision_ids.append(captured["revision_id"])

    mocked_fetch.assert_called_once()
    assert revision_ids[0] == revision_ids[1]


def test_drive_adv_filing_discovery_fails_closed_when_discovery_is_not_sealed(
    tmp_path, monkeypatch: pytest.MonkeyPatch, _acquisition_db: str
) -> None:
    from edgar_warehouse.application.command_router import run_command
    from edgar_warehouse.application.errors import WarehouseRuntimeError

    _set_warehouse_env(monkeypatch, tmp_path)
    _seed_daily_index(tmp_path, business_date="2026-08-24", sealed=False)

    with pytest.raises(WarehouseRuntimeError, match="No sealed discovery observation"):
        run_command(
            "drive-adv-filing-discovery-for-date",
            Namespace(
                business_date="2026-08-24",
                worker_id="adv-discovery-worker-1",
                lease_seconds=None,
                registry_version=None,
                run_id="run-adv-discovery-1",
            ),
        )


def test_filing_and_adv_discovery_partition_the_same_sealed_daily_index_independently(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], _acquisition_db: str
) -> None:
    """The real proof this ticket needs: both families' drivers can run
    against the exact same sealed daily-index observation, each only ever
    touching its own in-scope forms, with no ledger key collision between
    them (family-partitioned `(source_family, logical_source_key)` keys).
    """

    from edgar_warehouse.acquisition.registry_ledger import CoverageSpec, SourceRegistryLedger
    from edgar_warehouse.application.command_router import run_command
    from edgar_warehouse.mdm.database import get_engine

    # This fixture only activated adv_filing -- also activate filing_artifact
    # so both drivers have real coverage in the same registry version.
    ledger = SourceRegistryLedger(get_engine())
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
        operator_authorization_reference="test-bootstrap-2",
    )
    ledger.record_catchup_progress("filing_artifact", date(2026, 1, 1))
    ledger.activate(version.version_id)

    _set_warehouse_env(monkeypatch, tmp_path)
    _seed_daily_index(tmp_path, business_date="2026-08-24", sealed=True)

    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_filing_content_bytes",
        side_effect=[b"<adv>adv bytes</adv>", b"<ownershipDocument>form4 bytes</ownershipDocument>"],
    ):
        adv_exit = run_command(
            "drive-adv-filing-discovery-for-date",
            Namespace(
                business_date="2026-08-24",
                worker_id="adv-worker",
                lease_seconds=None,
                registry_version=None,
                run_id="run-adv",
            ),
        )
        adv_result = json.loads(capsys.readouterr().out)

        filing_exit = run_command(
            "drive-filing-discovery-for-date",
            Namespace(
                business_date="2026-08-24",
                worker_id="filing-worker",
                lease_seconds=None,
                registry_version=None,
                run_id="run-filing",
            ),
        )
        filing_result = json.loads(capsys.readouterr().out)

    assert adv_exit == 0
    assert filing_exit == 0

    adv_outcomes = {o["accession_number"]: o for o in adv_result["outcomes"]}
    assert adv_outcomes["0001140361-26-000003"]["in_scope"] is True
    assert adv_outcomes["0001140361-26-000002"]["in_scope"] is False

    filing_outcomes = {o["accession_number"]: o for o in filing_result["outcomes"]}
    assert filing_outcomes["0001140361-26-000002"]["in_scope"] is True
    assert filing_outcomes["0001140361-26-000003"]["in_scope"] is False
