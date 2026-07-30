from __future__ import annotations

import hashlib
import json
from datetime import date

import pytest

from edgar_warehouse.application.adv_bulk_fetch import (
    AdvBulkFetchTarget,
    AdvBulkManifestSource,
    build_source_manifest,
    fetch_adv_bulk_sources,
    parse_reports_metadata,
    periods_to_fetch,
    rolling_window_periods,
    select_downloadable,
)

_SAMPLE_METADATA = json.dumps({
    "advFilingData": {
        "sectionDisplayName": "Form ADV Part 1 Data Files",
        "sectionDisplayOrder": 1,
        "2025": {
            "files": [
                {
                    "displayName": "June",
                    "fileName": "ADV_Filing_Data_20250601_20250630.zip",
                    "size": 7400681,
                    "year": "2025",
                    "fileType": "advFilingData",
                    "uploadedOn": "2026-05-04 16:32:01",
                },
            ]
        },
        "2026": {
            "files": [
                {
                    "displayName": "June",
                    "fileName": "ADV_Filing_Data_20260601_20260630.zip",
                    "size": 9057014,
                    "year": "2026",
                    "fileType": "advFilingData",
                    "uploadedOn": "2026-07-01 21:13:14",
                },
            ]
        },
        # 2024 key present but empty, as seen live -- must not error.
        "2024": {},
    },
}).encode("utf-8")


def test_parse_reports_metadata_derives_dataset_period_from_filename() -> None:
    result = parse_reports_metadata(_SAMPLE_METADATA)

    assert result == {
        "2025-06": ("2025", "ADV_Filing_Data_20250601_20250630.zip"),
        "2026-06": ("2026", "ADV_Filing_Data_20260601_20260630.zip"),
    }


def test_parse_reports_metadata_ignores_empty_year_entries() -> None:
    # 2024's empty dict must not raise or produce a spurious entry.
    result = parse_reports_metadata(_SAMPLE_METADATA)
    assert not any(period.startswith("2024") for period in result)


def test_parse_reports_metadata_rejects_filename_with_extra_path_segments() -> None:
    # fullmatch (not search) -- a fileName that embeds the valid pattern as a
    # suffix of something larger (e.g. a path-traversal attempt) must not
    # produce a manifest entry, since select_downloadable/_upload later use
    # this string directly in a storage path.
    payload = json.dumps({
        "advFilingData": {
            "2026": {
                "files": [
                    {
                        "fileName": "../evil/ADV_Filing_Data_20260601_20260630.zip",
                        "year": "2026",
                    },
                ]
            },
        }
    }).encode()

    result = parse_reports_metadata(payload)

    assert result == {}


def test_rolling_window_periods_returns_13_months_oldest_first() -> None:
    periods = rolling_window_periods(date(2026, 6, 15), window_months=13)

    assert periods == [
        "2025-06", "2025-07", "2025-08", "2025-09", "2025-10", "2025-11",
        "2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05",
        "2026-06",
    ]


def test_rolling_window_periods_crosses_year_boundary_correctly() -> None:
    periods = rolling_window_periods(date(2026, 1, 5), window_months=3)
    assert periods == ["2025-11", "2025-12", "2026-01"]


def test_periods_to_fetch_skips_already_ingested() -> None:
    window = ["2026-04", "2026-05", "2026-06"]
    already = {"2026-04", "2026-05"}

    needed = periods_to_fetch(window, already)

    assert needed == ["2026-06"]


def test_periods_to_fetch_normal_path_is_empty_when_fully_covered() -> None:
    window = ["2026-05", "2026-06"]
    already = {"2026-05", "2026-06"}

    assert periods_to_fetch(window, already) == []


def test_periods_to_fetch_forced_period_overrides_window() -> None:
    window = ["2026-05", "2026-06"]
    already = {"2026-05", "2026-06"}

    needed = periods_to_fetch(window, already, forced_period="2025-03")

    assert needed == ["2025-03"]


def test_periods_to_fetch_force_allows_reingesting_already_ingested_period() -> None:
    window = ["2026-06"]
    already = {"2026-06"}

    needed = periods_to_fetch(window, already, forced_period="2026-06", force=True)

    assert needed == ["2026-06"]


def test_periods_to_fetch_force_without_forced_period_is_rejected() -> None:
    # force=True with no forced_period would otherwise silently re-fetch the
    # entire 13-month window -- --force's documented contract is that it
    # requires --dataset-period, so this enforces that rather than leaving
    # it as an unchecked claim.
    with pytest.raises(ValueError, match="force requires forced_period"):
        periods_to_fetch(["2026-06", "2026-05"], set(), forced_period=None, force=True)


def test_periods_to_fetch_forced_period_without_force_still_skips_if_already_ingested() -> None:
    # A forced period is only a *target* override; it does not itself bypass
    # the already-ingested skip -- that is what --force is for. This keeps
    # "operator wants March instead of the auto window" and "operator wants
    # to re-ingest a period we already have" as two independent, explicit
    # choices rather than one flag silently implying the other.
    window = ["2026-06"]
    already = {"2025-03"}

    needed = periods_to_fetch(window, already, forced_period="2025-03", force=False)

    assert needed == []


def test_select_downloadable_splits_available_from_not_yet_published() -> None:
    metadata = {
        "2026-05": ("2026", "ADV_Filing_Data_20260501_20260531.zip"),
        "2026-06": ("2026", "ADV_Filing_Data_20260601_20260630.zip"),
    }
    periods = ["2026-05", "2026-06", "2026-07"]

    targets, not_yet_published = select_downloadable(metadata, periods)

    assert targets == [
        AdvBulkFetchTarget(dataset_period="2026-05", year="2026", file_name="ADV_Filing_Data_20260501_20260531.zip"),
        AdvBulkFetchTarget(dataset_period="2026-06", year="2026", file_name="ADV_Filing_Data_20260601_20260630.zip"),
    ]
    assert not_yet_published == ["2026-07"]


def test_select_downloadable_handles_all_not_yet_published() -> None:
    targets, not_yet_published = select_downloadable({}, ["2026-07"])
    assert targets == []
    assert not_yet_published == ["2026-07"]


def test_build_source_manifest_matches_ingest_relationship_sources_shape() -> None:
    sources = [
        AdvBulkManifestSource(
            dataset_period="2026-06",
            storage_path="s3://bucket/warehouse/bronze/runs/fetch-adv-bulk/run-1/ADV_Filing_Data_20260601_20260630.zip",
            sha256="a" * 64,
        ),
    ]

    manifest = build_source_manifest(sources)

    assert manifest == {
        "sources": [
            {
                "kind": "iapd_adv_bulk",
                "storage_path": "s3://bucket/warehouse/bronze/runs/fetch-adv-bulk/run-1/ADV_Filing_Data_20260601_20260630.zip",
                "sha256": "a" * 64,
                "dataset_period": "2026-06",
            },
        ],
    }


def test_build_source_manifest_empty_sources_is_a_valid_empty_manifest() -> None:
    # The common daily_incremental no-op path: nothing new this run.
    assert build_source_manifest([]) == {"sources": []}


class _Recorder:
    def __init__(self) -> None:
        self.metadata_calls = 0
        self.archive_calls: list[tuple[str, str]] = []
        self.uploads: list[tuple[str, bytes]] = []

    def fetch_metadata(self) -> bytes:
        self.metadata_calls += 1
        return _SAMPLE_METADATA

    def fetch_archive(self, year: str, file_name: str) -> bytes:
        self.archive_calls.append((year, file_name))
        return f"content-for-{file_name}".encode()

    def upload(self, file_name: str, content: bytes) -> str:
        self.uploads.append((file_name, content))
        return f"s3://bucket/runs/fetch-adv-bulk/run-1/{file_name}"


def test_fetch_adv_bulk_sources_no_op_when_window_fully_covered_makes_zero_network_calls() -> None:
    # The daily_incremental common case: nothing missing locally, so not even
    # the metadata poll should fire.
    recorder = _Recorder()
    window = rolling_window_periods(date(2026, 6, 15), window_months=1)  # just "2026-06"

    sources, not_yet_published = fetch_adv_bulk_sources(
        already_ingested={"2026-06"},
        as_of=date(2026, 6, 15),
        forced_period=None,
        force=False,
        window_months=1,
        fetch_metadata=recorder.fetch_metadata,
        fetch_archive=recorder.fetch_archive,
        upload=recorder.upload,
    )

    assert sources == []
    assert not_yet_published == []
    assert recorder.metadata_calls == 0
    assert recorder.archive_calls == []


def test_fetch_adv_bulk_sources_fetches_and_stages_missing_period() -> None:
    recorder = _Recorder()

    sources, not_yet_published = fetch_adv_bulk_sources(
        already_ingested=set(),
        as_of=date(2026, 6, 15),
        forced_period=None,
        force=False,
        window_months=1,
        fetch_metadata=recorder.fetch_metadata,
        fetch_archive=recorder.fetch_archive,
        upload=recorder.upload,
    )

    assert recorder.metadata_calls == 1
    assert recorder.archive_calls == [("2026", "ADV_Filing_Data_20260601_20260630.zip")]
    assert not_yet_published == []
    assert len(sources) == 1
    source = sources[0]
    assert source.dataset_period == "2026-06"
    assert source.storage_path == "s3://bucket/runs/fetch-adv-bulk/run-1/ADV_Filing_Data_20260601_20260630.zip"
    assert source.sha256 == hashlib.sha256(b"content-for-ADV_Filing_Data_20260601_20260630.zip").hexdigest()


def test_fetch_adv_bulk_sources_reports_not_yet_published_without_erroring() -> None:
    recorder = _Recorder()

    sources, not_yet_published = fetch_adv_bulk_sources(
        already_ingested=set(),
        as_of=date(2026, 7, 15),
        forced_period="2026-07",
        force=False,
        window_months=1,
        fetch_metadata=recorder.fetch_metadata,
        fetch_archive=recorder.fetch_archive,
        upload=recorder.upload,
    )

    assert sources == []
    assert not_yet_published == ["2026-07"]
    assert recorder.metadata_calls == 1
    assert recorder.archive_calls == []
