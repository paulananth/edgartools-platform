"""Determine which SEC/IAPD advFilingData monthly archives need fetching,
and build the source manifest ingest_adv_bulk_archive (via
ingest-relationship-sources) consumes.

Fetch and ingest are deliberately separate steps (ticket 06, adv-pipeline
map): this module only decides *what* to fetch and records *where it was
staged*; edgar_warehouse.application.adv_bulk_ingest owns parsing and
silver writes. The resulting manifest is the reviewable artifact connecting
them, mirroring the existing mdm build-relationship-release-manifest
precedent of treating a manifest as evidence rather than a throwaway.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

# fullmatch (not search): the whole fileName field must be exactly this
# shape. search() only anchors the end ($), so a SEC JSON payload with an
# adversarial fileName like ".../ADV_Filing_Data_20260601_20260630.zip"
# would still match and flow into a storage path -- fullmatch rejects
# anything but the bare expected filename.
_FILENAME_DATE_RE = re.compile(r"ADV_Filing_Data_(\d{4})(\d{2})\d{2}_\d{8}\.zip")


@dataclass(frozen=True)
class AdvBulkFetchTarget:
    dataset_period: str
    year: str
    file_name: str


@dataclass(frozen=True)
class AdvBulkManifestSource:
    dataset_period: str
    storage_path: str
    sha256: str


def parse_reports_metadata(payload: bytes) -> dict[str, tuple[str, str]]:
    """Parse reports.adviserinfo.sec.gov's reports_metadata.json.

    Returns {dataset_period: (year, file_name)}. dataset_period ("YYYY-MM")
    is derived from the file name's own embedded start date, not the
    "year"/"displayName" fields -- the file name is the single source of
    truth SEC actually publishes; the surrounding metadata fields are
    presentation redundant with it.
    """
    data = json.loads(payload)
    adv = data.get("advFilingData", {})
    result: dict[str, tuple[str, str]] = {}
    for key, value in adv.items():
        if not isinstance(value, dict):
            continue
        files = value.get("files")
        if not files:
            continue
        for entry in files:
            file_name = entry.get("fileName", "")
            match = _FILENAME_DATE_RE.fullmatch(file_name)
            if not match:
                continue
            year, month = match.group(1), match.group(2)
            dataset_period = f"{year}-{month}"
            result[dataset_period] = (entry.get("year", year), file_name)
    return result


def rolling_window_periods(as_of: date, window_months: int = 13) -> list[str]:
    """Trailing window_months of "YYYY-MM" periods ending at as_of's month, oldest first."""
    periods: list[str] = []
    year, month = as_of.year, as_of.month
    for offset in range(window_months - 1, -1, -1):
        total = (year * 12 + (month - 1)) - offset
        p_year, p_month = divmod(total, 12)
        periods.append(f"{p_year:04d}-{p_month + 1:02d}")
    return periods


def periods_to_fetch(
    window_periods: list[str],
    already_ingested: set[str],
    *,
    forced_period: str | None = None,
    force: bool = False,
) -> list[str]:
    """Decide which dataset_periods to actually fetch this run.

    Normal path (forced_period=None): the rolling window minus whatever is
    already ingested -- on ~29 of 30 days this is empty.

    forced_period targets a single period instead of the window (manual
    repair/backfill). It does not itself bypass the already-ingested skip;
    force does. Keeping these independent means "I want a different period"
    and "I want to re-ingest a period we already have" are two explicit
    choices, not one flag silently implying the other.

    force without forced_period is rejected rather than silently re-fetching
    the entire 13-month window -- the CLI's own --force help text already
    states it requires --dataset-period; this enforces that contract instead
    of leaving it as an unchecked claim.
    """
    if force and forced_period is None:
        raise ValueError("force requires forced_period (--force requires --dataset-period)")
    candidates = [forced_period] if forced_period is not None else window_periods
    if force:
        return list(candidates)
    return [period for period in candidates if period not in already_ingested]


def select_downloadable(
    metadata: dict[str, tuple[str, str]],
    periods: list[str],
) -> tuple[list[AdvBulkFetchTarget], list[str]]:
    """Split requested periods into (available now, not yet published by SEC)."""
    targets: list[AdvBulkFetchTarget] = []
    not_yet_published: list[str] = []
    for period in periods:
        entry = metadata.get(period)
        if entry is None:
            not_yet_published.append(period)
            continue
        year, file_name = entry
        targets.append(AdvBulkFetchTarget(dataset_period=period, year=year, file_name=file_name))
    return targets, not_yet_published


def build_source_manifest(sources: list[AdvBulkManifestSource]) -> dict:
    """Build the {"sources": [...]} manifest ingest-relationship-sources reads.

    An empty sources list is a valid manifest, not an error -- it is the
    expected shape on the common daily_incremental no-op path where nothing
    new needs fetching.
    """
    return {
        "sources": [
            {
                "kind": "iapd_adv_bulk",
                "storage_path": source.storage_path,
                "sha256": source.sha256,
                "dataset_period": source.dataset_period,
            }
            for source in sources
        ],
    }


_REPORTS_METADATA_URL = "https://reports.adviserinfo.sec.gov/reports/foia/reports_metadata.json"


def fetch_reports_metadata_bytes(identity: str) -> bytes:
    """Live network fetch of SEC/IAPD's advFilingData manifest.

    IAPD ADV bulk is a non-edgartools source (NON_EDGARTOOLS_OBJECT_CLASSES,
    edgartools_sec_gateway.py) -- it stays on sec_client's mandatory-archive
    HTTP path, not the edgartools gateway. That import is deliberately kept
    out of warehouse_orchestrator.py (tests/architecture/test_boundaries.py
    only permits it to route through a per-source module like this one).
    """
    from edgar_warehouse.infrastructure.sec_client import download_sec_bytes

    return download_sec_bytes(_REPORTS_METADATA_URL, identity)


def fetch_archive_bytes(identity: str, year: str, file_name: str) -> bytes:
    """Live network fetch of one monthly advFilingData archive. See
    fetch_reports_metadata_bytes for why this imports sec_client here."""
    from edgar_warehouse.infrastructure.sec_client import download_sec_bytes

    url = f"https://reports.adviserinfo.sec.gov/reports/foia/advFilingData/{year}/{file_name}"
    return download_sec_bytes(url, identity)


def fetch_adv_bulk_sources(
    *,
    already_ingested: set[str],
    as_of: date,
    forced_period: str | None,
    force: bool,
    window_months: int = 13,
    fetch_metadata: Callable[[], bytes],
    fetch_archive: Callable[[str, str], bytes],
    upload: Callable[[str, bytes], str],
) -> tuple[list[AdvBulkManifestSource], list[str]]:
    """Decide what's needed, fetch and stage it, return (sources, not_yet_published).

    HTTP fetch and storage upload are injected rather than performed here so
    this stays testable with fakes -- the orchestrator wires real SEC/S3
    calls; tests wire recording stand-ins. fetch_metadata/fetch_archive are
    only called when there is at least one period to consider, so the common
    daily_incremental no-op path (nothing in the window is missing) makes
    zero network calls at all -- not even the metadata poll.
    """
    window = rolling_window_periods(as_of, window_months=window_months)
    needed = periods_to_fetch(window, already_ingested, forced_period=forced_period, force=force)
    if not needed:
        return [], []

    metadata = parse_reports_metadata(fetch_metadata())
    targets, not_yet_published = select_downloadable(metadata, needed)

    sources: list[AdvBulkManifestSource] = []
    for target in targets:
        content = fetch_archive(target.year, target.file_name)
        sha256 = hashlib.sha256(content).hexdigest()
        storage_path = upload(target.file_name, content)
        sources.append(
            AdvBulkManifestSource(
                dataset_period=target.dataset_period,
                storage_path=storage_path,
                sha256=sha256,
            )
        )
    return sources, not_yet_published
