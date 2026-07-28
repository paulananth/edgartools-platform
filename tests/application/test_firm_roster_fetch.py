from __future__ import annotations

from edgar_warehouse.application.firm_roster_fetch import (
    FirmRosterManifestSource,
    build_source_manifest,
    fetch_firm_roster_sources,
    latest_available_period,
    parse_firm_roster_listing,
    period_to_fetch,
    select_downloadable_variants,
)

# Real anchors scraped live from SEC's Firm Roster listing page
# (https://www.sec.gov/data-research/sec-markets-data/information-about-
# registered-investment-advisers-exempt-reporting-advisers) on 2026-07-28.
# Deliberately includes every observed anomaly: two different path prefixes
# across eras, a stray "_0" suffix, an "-exemptzip" typo, and an inconsistent
# "Exempt Investment Advisers" vs. "Exempt Reporting Advisers" link-text
# label -- filename-based parsing breaks on these; link-text parsing does not.
_REAL_LISTING_HTML = """
<ul>
<li><a href="/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers/ia07012026-exempt.zip">Exempt Investment Advisers, July 2026</a></li>
<li><a href="/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers/ia07012026.zip">Registered Investment Advisers, July 2026</a></li>
<li><a href="/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers/ia06012026-exempt_0.zip">Exempt Investment Advisers, June 2026</a></li>
<li><a href="/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers/ia060126_0.zip">Registered Investment Advisers, June 2026</a></li>
<li><a href="/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers/ia050126-exempt.zip">Exempt Investment Advisers, May 2026</a></li>
<li><a href="/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers/ia050126.zip">Registered Investment Advisers, May 2026</a></li>
<li><a href="/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers/ia040126-exempt.zip">Exempt Reporting Advisers, April 2026</a></li>
<li><a href="/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers/ia040126.zip">Registered Investment Advisers, April 2026</a></li>
<li><a href="/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers/ia020226-exemptzip.zip">Exempt Investment Advisers, February 2026</a></li>
<li><a href="/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers/ia020226.zip">Registered Investment Advisers, February 2026</a></li>
<li><a href="/files/investment/data/information-about-registered-investment-advisers-exempt-reporting-advisers/ia122025-exempt.zip">Exempt Investment Advisers, December 2025</a></li>
<li><a href="/files/investment/data/information-about-registered-investment-advisers-exempt-reporting-advisers/ia122025.zip">Registered Investment Advisers, December 2025</a></li>
<li><a href="/files/investment/data/information-about-registered-investment-advisers-and-exempt-reporting-advisers/ia051023exempt.zip">Exempt Reporting Advisers, May 2023</a></li>
<li><a href="/files/investment/data/information-about-registered-investment-advisers-and-exempt-reporting-advisers/ia051023_1.zip">Registered Investment Advisers, May 2023</a></li>
</ul>
"""


def test_parse_firm_roster_listing_uses_link_text_not_filename() -> None:
    listing = parse_firm_roster_listing(_REAL_LISTING_HTML)

    assert listing["2026-07"]["registered"] == (
        "/files/investment/data/other/information-about-registered-investment-"
        "advisers-exempt-reporting-advisers/ia07012026.zip"
    )
    assert listing["2026-07"]["exempt"] == (
        "/files/investment/data/other/information-about-registered-investment-"
        "advisers-exempt-reporting-advisers/ia07012026-exempt.zip"
    )


def test_parse_firm_roster_listing_handles_stray_suffix_and_typo_filenames() -> None:
    listing = parse_firm_roster_listing(_REAL_LISTING_HTML)

    # ia060126_0.zip / ia06012026-exempt_0.zip -- stray "_0" suffix
    assert listing["2026-06"]["registered"].endswith("ia060126_0.zip")
    assert listing["2026-06"]["exempt"].endswith("ia06012026-exempt_0.zip")
    # ia020226-exemptzip.zip -- "-exemptzip" typo (missing the dot before zip)
    assert listing["2026-02"]["exempt"].endswith("ia020226-exemptzip.zip")


def test_parse_firm_roster_listing_handles_inconsistent_exempt_label() -> None:
    """'Exempt Investment Advisers' (most months) vs 'Exempt Reporting
    Advisers' (April 2026, May 2023) -- both must resolve to the same
    "exempt" variant key.
    """
    listing = parse_firm_roster_listing(_REAL_LISTING_HTML)

    assert "exempt" in listing["2026-04"]
    assert "exempt" in listing["2023-05"]


def test_parse_firm_roster_listing_spans_both_historical_path_prefixes() -> None:
    listing = parse_firm_roster_listing(_REAL_LISTING_HTML)

    assert listing["2025-12"]["registered"].startswith(
        "/files/investment/data/information-about-registered-investment-advisers-"
        "exempt-reporting-advisers/"
    )
    assert listing["2023-05"]["registered"].startswith(
        "/files/investment/data/information-about-registered-investment-advisers-"
        "and-exempt-reporting-advisers/"
    )


def test_latest_available_period_is_the_newest_yyyy_mm() -> None:
    listing = parse_firm_roster_listing(_REAL_LISTING_HTML)

    assert latest_available_period(listing) == "2026-07"


def test_latest_available_period_empty_listing_is_none() -> None:
    assert latest_available_period({}) is None


def test_select_downloadable_variants_returns_both_hrefs_for_a_period() -> None:
    listing = parse_firm_roster_listing(_REAL_LISTING_HTML)

    variants = select_downloadable_variants(listing, "2026-07")

    assert set(variants) == {"registered", "exempt"}
    assert variants["registered"].endswith("ia07012026.zip")


def test_select_downloadable_variants_missing_period_is_empty() -> None:
    listing = parse_firm_roster_listing(_REAL_LISTING_HTML)

    assert select_downloadable_variants(listing, "1999-01") == {}


def test_period_to_fetch_normal_path_skips_already_ingested() -> None:
    assert period_to_fetch("2026-07", already_ingested={"2026-07"}) is None
    assert period_to_fetch("2026-07", already_ingested={"2026-06"}) == "2026-07"
    assert period_to_fetch("2026-07", already_ingested=set()) == "2026-07"


def test_period_to_fetch_no_latest_period_is_none() -> None:
    assert period_to_fetch(None, already_ingested=set()) is None


def test_period_to_fetch_forced_period_bypasses_latest() -> None:
    assert period_to_fetch(
        "2026-07", already_ingested=set(), forced_period="2026-01"
    ) == "2026-01"


def test_period_to_fetch_force_without_forced_period_rejected() -> None:
    import pytest

    with pytest.raises(ValueError, match="forced_period"):
        period_to_fetch("2026-07", already_ingested={"2026-07"}, force=True)


def test_period_to_fetch_force_bypasses_already_ingested_skip() -> None:
    assert period_to_fetch(
        "2026-07", already_ingested={"2026-07"}, forced_period="2026-07", force=True
    ) == "2026-07"


def test_build_source_manifest_shape() -> None:
    manifest = build_source_manifest([
        FirmRosterManifestSource(
            dataset_period="2026-07", storage_path="s3://x/ia07012026.zip", sha256="abc",
        ),
        FirmRosterManifestSource(
            dataset_period="2026-07", storage_path="s3://x/ia07012026-exempt.zip", sha256="def",
        ),
    ])

    assert manifest == {
        "sources": [
            {"kind": "iapd_firm_roster", "storage_path": "s3://x/ia07012026.zip",
             "sha256": "abc", "dataset_period": "2026-07"},
            {"kind": "iapd_firm_roster", "storage_path": "s3://x/ia07012026-exempt.zip",
             "sha256": "def", "dataset_period": "2026-07"},
        ],
    }


def test_build_source_manifest_empty_is_valid() -> None:
    assert build_source_manifest([]) == {"sources": []}


class _Recorder:
    def __init__(self, listing_html: str, archive_bytes: dict[str, bytes]):
        self._listing_html = listing_html
        self._archive_bytes = archive_bytes
        self.listing_calls = 0
        self.archive_calls: list[str] = []
        self.uploads: list[tuple[str, bytes]] = []

    def fetch_listing(self) -> bytes:
        self.listing_calls += 1
        return self._listing_html.encode("utf-8")

    def fetch_archive(self, href: str) -> bytes:
        self.archive_calls.append(href)
        return self._archive_bytes[href]

    def upload(self, file_name: str, content: bytes) -> str:
        self.uploads.append((file_name, content))
        return f"s3://bucket/{file_name}"


def test_fetch_firm_roster_sources_no_op_when_already_ingested_makes_zero_archive_downloads() -> None:
    """Unlike advFilingData, the listing page itself must always be fetched
    once (there is no cheaper metadata-only endpoint) -- the no-op-day
    guarantee here is zero ARCHIVE downloads, the actual expensive resource.
    """
    recorder = _Recorder(_REAL_LISTING_HTML, {})

    sources, latest = fetch_firm_roster_sources(
        already_ingested={"2026-07"},
        forced_period=None,
        force=False,
        fetch_listing=recorder.fetch_listing,
        fetch_archive=recorder.fetch_archive,
        upload=recorder.upload,
    )

    assert sources == []
    assert latest == "2026-07"
    assert recorder.listing_calls == 1
    assert recorder.archive_calls == []


def test_fetch_firm_roster_sources_fetches_both_variants_for_missing_period() -> None:
    registered_href = (
        "/files/investment/data/other/information-about-registered-investment-"
        "advisers-exempt-reporting-advisers/ia07012026.zip"
    )
    exempt_href = (
        "/files/investment/data/other/information-about-registered-investment-"
        "advisers-exempt-reporting-advisers/ia07012026-exempt.zip"
    )
    recorder = _Recorder(_REAL_LISTING_HTML, {
        registered_href: b"registered-content",
        exempt_href: b"exempt-content",
    })

    sources, latest = fetch_firm_roster_sources(
        already_ingested=set(),
        forced_period=None,
        force=False,
        fetch_listing=recorder.fetch_listing,
        fetch_archive=recorder.fetch_archive,
        upload=recorder.upload,
    )

    assert latest == "2026-07"
    assert recorder.listing_calls == 1
    assert sorted(recorder.archive_calls) == sorted([registered_href, exempt_href])
    assert {source.dataset_period for source in sources} == {"2026-07"}
    assert len(sources) == 2
    assert len(recorder.uploads) == 2


def test_fetch_firm_roster_sources_forced_period_not_on_listing_returns_nothing() -> None:
    recorder = _Recorder(_REAL_LISTING_HTML, {})

    sources, latest = fetch_firm_roster_sources(
        already_ingested=set(),
        forced_period="1999-01",
        force=True,
        fetch_listing=recorder.fetch_listing,
        fetch_archive=recorder.fetch_archive,
        upload=recorder.upload,
    )

    assert sources == []
    assert latest == "2026-07"
    assert recorder.archive_calls == []
