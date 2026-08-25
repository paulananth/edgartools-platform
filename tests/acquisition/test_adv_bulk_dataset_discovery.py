from __future__ import annotations

import json
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from edgar_warehouse.acquisition.adv_bulk_dataset_discovery import (
    AdvBulkDatasetCandidate,
    adv_bulk_dataset_candidate_id,
    build_adv_bulk_dataset_manifest,
    drive_adv_bulk_dataset_manifest,
)
from edgar_warehouse.acquisition.ledger import AcquisitionLedger, FetchWorkState
from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.infrastructure.object_storage import StorageLocation


def _ledger() -> AcquisitionLedger:
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    AcquisitionBase.metadata.create_all(engine)
    return AcquisitionLedger(engine)


class _SpyPolicy:
    def __init__(self, payload: bytes = b"archive bytes", *, complete: bool = True) -> None:
        self.payload = payload
        self.complete = complete
        self.fetch_calls: list[str] = []

    def fetch(self, source_url: str) -> bytes:
        self.fetch_calls.append(source_url)
        return self.payload

    def is_complete(self, payload: bytes) -> bool:
        return self.complete


_METADATA_PAYLOAD = json.dumps(
    {
        "advFilingData": {
            "2026": {
                "files": [
                    {
                        "fileName": "ADV_Filing_Data_20260601_20260630.zip",
                        "year": "2026",
                    }
                ]
            }
        }
    }
).encode("utf-8")

_LISTING_HTML = (
    '<a href="/foia/ia2026-07-registered.zip">Registered Investment Advisers, July 2026</a>'
    '<a href="/foia/ia2026-07-exempt.zip">Exempt Investment Advisers, July 2026</a>'
)


# ---------------------------------------------------------------------------
# build_adv_bulk_dataset_manifest
# ---------------------------------------------------------------------------


def test_manifest_resolves_one_bulk_archive_and_both_roster_variants() -> None:
    manifest = build_adv_bulk_dataset_manifest(
        universe_label="test",
        as_of=date(2026, 6, 15),
        fetch_reports_metadata_bytes=lambda: _METADATA_PAYLOAD,
        fetch_listing_bytes=lambda: _LISTING_HTML.encode("utf-8"),
        window_months=1,
    )

    kinds = {(c.source_kind, c.dataset_period, c.variant) for c in manifest.candidates}
    assert ("adv_bulk", "2026-06", None) in kinds
    assert ("firm_roster", "2026-07", "registered") in kinds
    assert ("firm_roster", "2026-07", "exempt") in kinds
    assert manifest.candidate_count == 3


def test_manifest_records_unpublished_periods_without_erroring() -> None:
    """Bullet 3: a period the metadata doesn't (yet) publish is a normal,
    valid-empty outcome for that period, not an error."""

    manifest = build_adv_bulk_dataset_manifest(
        universe_label="test",
        as_of=date(2026, 7, 15),
        fetch_reports_metadata_bytes=lambda: _METADATA_PAYLOAD,
        fetch_listing_bytes=lambda: b"",
        window_months=2,
    )

    assert "2026-07" in manifest.unpublished_periods
    bulk_candidates = [c for c in manifest.candidates if c.source_kind == "adv_bulk"]
    assert [c.dataset_period for c in bulk_candidates] == ["2026-06"]


def test_manifest_is_valid_and_empty_when_nothing_is_published() -> None:
    manifest = build_adv_bulk_dataset_manifest(
        universe_label="test",
        as_of=date(2026, 6, 15),
        fetch_reports_metadata_bytes=lambda: json.dumps({"advFilingData": {}}).encode("utf-8"),
        fetch_listing_bytes=lambda: b"",
        window_months=1,
    )
    assert manifest.candidate_count == 0
    assert manifest.unpublished_periods == ("2026-06",)


def test_candidate_ids_are_deterministic_and_kind_scoped() -> None:
    bulk = AdvBulkDatasetCandidate(source_kind="adv_bulk", dataset_period="2026-06", source_url="x")
    roster_reg = AdvBulkDatasetCandidate(
        source_kind="firm_roster", dataset_period="2026-07", variant="registered", source_url="y"
    )
    roster_exempt = AdvBulkDatasetCandidate(
        source_kind="firm_roster", dataset_period="2026-07", variant="exempt", source_url="z"
    )
    assert adv_bulk_dataset_candidate_id(bulk) == adv_bulk_dataset_candidate_id(bulk)
    assert adv_bulk_dataset_candidate_id(roster_reg) != adv_bulk_dataset_candidate_id(roster_exempt)
    assert adv_bulk_dataset_candidate_id(bulk) != adv_bulk_dataset_candidate_id(roster_reg)


# ---------------------------------------------------------------------------
# drive_adv_bulk_dataset_manifest
# ---------------------------------------------------------------------------


def test_drive_captures_every_resolved_candidate(tmp_path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    manifest = build_adv_bulk_dataset_manifest(
        universe_label="test",
        as_of=date(2026, 6, 15),
        fetch_reports_metadata_bytes=lambda: _METADATA_PAYLOAD,
        fetch_listing_bytes=lambda: _LISTING_HTML.encode("utf-8"),
        window_months=1,
    )
    policy = _SpyPolicy()

    result = drive_adv_bulk_dataset_manifest(
        ledger, bronze_root, {"adv_bulk_dataset": policy}, manifest,
        worker_id="worker-1", registry_version="adv-bulk-dataset-v1",
    )

    assert result.interval_complete is True
    assert len(result.outcomes) == 3
    assert len(policy.fetch_calls) == 3
    assert all(o.fetch_state is FetchWorkState.CAPTURED for o in result.outcomes)


def test_drive_replay_performs_no_second_network_fetch(tmp_path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    manifest = build_adv_bulk_dataset_manifest(
        universe_label="test",
        as_of=date(2026, 6, 15),
        fetch_reports_metadata_bytes=lambda: _METADATA_PAYLOAD,
        fetch_listing_bytes=lambda: b"",
        window_months=1,
    )
    policy = _SpyPolicy()

    first = drive_adv_bulk_dataset_manifest(
        ledger, bronze_root, {"adv_bulk_dataset": policy}, manifest,
        worker_id="worker-1", registry_version="adv-bulk-dataset-v1",
    )
    assert first.interval_complete is True
    assert len(policy.fetch_calls) == 1

    second = drive_adv_bulk_dataset_manifest(
        ledger, bronze_root, {"adv_bulk_dataset": policy}, manifest,
        worker_id="worker-2", registry_version="adv-bulk-dataset-v1",
    )
    assert second.interval_complete is True
    assert len(policy.fetch_calls) == 1
    assert second.outcomes[0].network_fetched is False


def test_drive_stays_incomplete_when_capture_fails(tmp_path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    manifest = build_adv_bulk_dataset_manifest(
        universe_label="test",
        as_of=date(2026, 6, 15),
        fetch_reports_metadata_bytes=lambda: _METADATA_PAYLOAD,
        fetch_listing_bytes=lambda: b"",
        window_months=1,
    )
    policy = _SpyPolicy(complete=False)

    result = drive_adv_bulk_dataset_manifest(
        ledger, bronze_root, {"adv_bulk_dataset": policy}, manifest,
        worker_id="worker-1", registry_version="adv-bulk-dataset-v1",
    )

    assert result.interval_complete is False
