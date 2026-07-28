"""Determine which SEC Firm Roster CSV archive needs fetching, and build the
source manifest ingest_firm_roster_archive (via ingest-relationship-sources)
consumes.

Unlike advFilingData (edgar_warehouse.application.adv_bulk_fetch), the Firm
Roster has no reports_metadata.json manifest -- there is only an HTML
listing page. Real filenames on that page are NOT consistently shaped
(confirmed live 2026-07-28): MMDDYYYY vs MMDDYY, a stray "_0" suffix on
several June 2026 archives, an "-exemptzip" typo on the February 2026 exempt
archive, and two different URL path prefixes across eras. Each link's own
human-readable text ("Registered Investment Advisers, July 2026" / "Exempt
Investment Advisers, July 2026" -- though "Exempt Reporting Advisers"
appears interchangeably in some months) is consistently shaped back to at
least 2006, so parsing is done against link text, never the filename.

Fetch and ingest are deliberately separate steps, mirroring
edgar_warehouse.application.adv_bulk_fetch's own split: this module only
decides *what* to fetch and records *where it was staged*;
edgar_warehouse.application.adv_firm_roster_ingest owns parsing and silver
writes.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass

_LISTING_LINK_RE = re.compile(
    r'<a[^>]+href="([^"]*ia[^"]*\.zip[^"]*)"[^>]*>(.*?)</a>',
    re.I | re.S,
)
_LISTING_TEXT_RE = re.compile(r"(Registered|Exempt)[^,]*,\s*([A-Za-z]+)\s+(\d{4})", re.I)
_MONTH_NUMBERS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

_LISTING_URL = (
    "https://www.sec.gov/data-research/sec-markets-data/"
    "information-about-registered-investment-advisers-exempt-reporting-advisers"
)
_HOST = "https://www.sec.gov"


@dataclass(frozen=True)
class FirmRosterFetchTarget:
    dataset_period: str
    variant: str
    href: str


@dataclass(frozen=True)
class FirmRosterManifestSource:
    dataset_period: str
    storage_path: str
    sha256: str


def parse_firm_roster_listing(html: str) -> dict[str, dict[str, str]]:
    """Parse the SEC Firm Roster CSV bulk-data listing page.

    Returns {dataset_period: {"registered": href, "exempt": href}}, built
    from each link's own text, not its filename -- see module docstring.
    """
    result: dict[str, dict[str, str]] = {}
    for href, text in _LISTING_LINK_RE.findall(html):
        clean_text = re.sub(r"\s+", " ", text).strip()
        match = _LISTING_TEXT_RE.search(clean_text)
        if not match:
            continue
        variant_word, month_name, year = match.groups()
        month = _MONTH_NUMBERS.get(month_name.lower())
        if month is None:
            continue
        dataset_period = f"{year}-{month:02d}"
        variant = "registered" if variant_word.lower() == "registered" else "exempt"
        result.setdefault(dataset_period, {})[variant] = href
    return result


def latest_available_period(listing: dict[str, dict[str, str]]) -> str | None:
    """The newest dataset_period actually published on the listing page, or
    None if the listing is empty. "YYYY-MM" strings sort correctly as text.
    """
    return max(listing) if listing else None


def select_downloadable_variants(
    listing: dict[str, dict[str, str]], period: str
) -> dict[str, str]:
    """{"registered": href, "exempt": href} for one period, or {} if absent."""
    return dict(listing.get(period, {}))


def period_to_fetch(
    latest_period: str | None,
    already_ingested: set[str],
    *,
    forced_period: str | None = None,
    force: bool = False,
) -> str | None:
    """Decide which single dataset_period to fetch this run, or None.

    Unlike advFilingData's rolling 13-month window, the Firm Roster is a
    full-universe snapshot each month and historical backfill is explicitly
    out of scope -- only the single latest published period is ever a
    candidate. forced_period/force follow the same independent-choice
    contract as adv_bulk_fetch.periods_to_fetch: forced_period alone targets
    a different period without bypassing the already-ingested skip; force
    without forced_period is rejected rather than silently re-fetching.
    """
    if force and forced_period is None:
        raise ValueError("force requires forced_period (--force requires --dataset-period)")
    candidate = forced_period if forced_period is not None else latest_period
    if candidate is None:
        return None
    if force:
        return candidate
    return None if candidate in already_ingested else candidate


def build_source_manifest(sources: list[FirmRosterManifestSource]) -> dict:
    """Build the {"sources": [...]} manifest ingest-relationship-sources reads.

    An empty sources list is a valid manifest -- the expected shape on the
    common no-op path where the latest period is already ingested.
    """
    return {
        "sources": [
            {
                "kind": "iapd_firm_roster",
                "storage_path": source.storage_path,
                "sha256": source.sha256,
                "dataset_period": source.dataset_period,
            }
            for source in sources
        ],
    }


def fetch_listing_bytes(identity: str) -> bytes:
    """Live network fetch of the Firm Roster listing page. See
    fetch_archive_bytes for why this imports sec_client here."""
    from edgar_warehouse.infrastructure.sec_client import download_sec_bytes

    return download_sec_bytes(_LISTING_URL, identity)


def fetch_archive_bytes(identity: str, href: str) -> bytes:
    """Live network fetch of one Firm Roster archive.

    IAPD Firm Roster is a non-edgartools source (NON_EDGARTOOLS_OBJECT_CLASSES,
    edgartools_sec_gateway.py) -- it stays on sec_client's mandatory-archive
    HTTP path, not the edgartools gateway. That import is deliberately kept
    out of warehouse_orchestrator.py (tests/architecture/test_boundaries.py
    only permits it to route through a per-source module like this one).
    """
    from edgar_warehouse.infrastructure.sec_client import download_sec_bytes

    return download_sec_bytes(f"{_HOST}{href}", identity)


def fetch_firm_roster_sources(
    *,
    already_ingested: set[str],
    forced_period: str | None,
    force: bool,
    fetch_listing: Callable[[], bytes],
    fetch_archive: Callable[[str], bytes],
    upload: Callable[[str, bytes], str],
) -> tuple[list[FirmRosterManifestSource], str | None]:
    """Decide what's needed, fetch and stage it, return (sources, latest_period).

    Unlike advFilingData (which can determine "nothing needed" from a pure
    date computation and skip its metadata poll entirely on ~29 of 30 days),
    the Firm Roster has no metadata-only endpoint separate from the listing
    page itself -- there is no way to learn the latest published period, or
    resolve a period's real download href (filenames are not reliably
    constructible, see module docstring), without fetching that page. So
    fetch_listing is always called exactly once per invocation; the
    no-op-day guarantee this makes instead is zero ARCHIVE downloads (the
    actual expensive, rate-limit-relevant resource) when the latest period
    is already ingested.

    latest_period is the newest period found on the listing page, returned
    regardless of whether anything was fetched -- callers use it to record
    the already-ingested watermark even on the common no-op day.
    """
    listing = parse_firm_roster_listing(fetch_listing().decode("utf-8"))
    latest_period = latest_available_period(listing)
    period = period_to_fetch(
        latest_period, already_ingested, forced_period=forced_period, force=force
    )
    if period is None:
        return [], latest_period

    variants = select_downloadable_variants(listing, period)
    sources: list[FirmRosterManifestSource] = []
    for href in variants.values():
        content = fetch_archive(href)
        sha256 = hashlib.sha256(content).hexdigest()
        file_name = href.rsplit("/", 1)[-1]
        storage_path = upload(file_name, content)
        sources.append(
            FirmRosterManifestSource(
                dataset_period=period, storage_path=storage_path, sha256=sha256
            )
        )
    return sources, latest_period
