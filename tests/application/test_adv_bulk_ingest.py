from __future__ import annotations

import io
import zipfile
from dataclasses import replace

from edgar_warehouse.application.adv_bulk_ingest import (
    AdvBulkParseResult,
    parse_adv_bulk_archive,
    reconstruct_effective_adv_set,
)


def _archive(files: dict[str, str]) -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
    return payload.getvalue()


def _archive_with_encoding(files: dict[str, str], encoding: str) -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as bundle:
        for name, content in files.items():
            bundle.writestr(name, content.encode(encoding))
    return payload.getvalue()


def test_adv_bulk_archive_uses_crd_and_pfid_for_both_schedule_sections() -> None:
    archive = _archive({
        "IA_ADV_Base_A_20260601_20260630.csv": (
            '"FilingID","DateSubmitted","1A","1D","1E1","7B"\n'
            '2115188,"06/24/2026 10:37:17 AM","PNC WEALTH","801-66195",129052,"Y"\n'
        ),
        "IA_Schedule_D_7B1_20260601_20260630.csv": (
            '"FilingID","Fund Name","Fund ID","ReferenceID","State","Country",'
            '"Fund Type","Gross Asset Value"\n'
            '2115188,"ALPHA FUND",805-123,518607,"Delaware","United States",'
            '"Private Equity Fund",321687148\n'
        ),
        "IA_Schedule_D_7B2_20260601_20260630.csv": (
            '"FilingID","Fund Name","Fund ID","Adviser Name","Adviser SEC Number",'
            '"Clients Solicited?"\n'
            '2115188,"BETA FUND",805-456,"REPORTING ADVISER","801-99999","N"\n'
        ),
        "ADV_Filing_Types_20260601_20260630.csv": (
            'FilingID,Annual Updating Amendment for Registered Adviser,Final SEC ERA Report\n'
            '2115188,Y,\n'
        ),
    })

    parsed = parse_adv_bulk_archive(
        archive,
        dataset_period="2026-06",
        source_sha256="abc123",
    )

    assert parsed.filings[0].accession_number == "iapd-adv:2115188"
    assert parsed.filings[0].adviser_crd_number == "129052"
    assert parsed.filings[0].filing_action == "annual_updating_amendment_for_registered_adviser"
    assert [(row.private_fund_id, row.schedule_section) for row in parsed.funds] == [
        ("805-123", "7B1"),
        ("805-456", "7B2"),
    ]
    assert {row.adviser_crd_number for row in parsed.funds} == {"129052"}
    assert all(row.source_sha256 == "abc123" for row in parsed.funds)

    newer_filing = replace(
        parsed.filings[0], filing_id="2116000", accession_number="iapd-adv:2116000"
    )
    newer_fund = replace(
        parsed.funds[0], filing_id="2116000", accession_number="iapd-adv:2116000",
        private_fund_id="805-999",
    )
    effective = reconstruct_effective_adv_set([
        parsed, AdvBulkParseResult((newer_filing,), (newer_fund,)),
    ])
    assert [row.filing_id for row in effective.filings] == ["2116000"]
    assert [row.private_fund_id for row in effective.funds] == ["805-999"]


def test_filing_type_columns_only_treat_yes_as_selected_action() -> None:
    parsed = parse_adv_bulk_archive(
        _archive({
            "IA_ADV_Base_A_20260601_20260630.csv": (
                '"FilingID","DateSubmitted","1A","1D","1E1","7B"\n'
                '2115188,"06/24/2026","PNC WEALTH","801-66195",129052,"N"\n'
            ),
            "ADV_Filing_Types_20260601_20260630.csv": (
                "FilingID,Annual Updating Amendment for Registered Adviser,Final SEC ERA Report\n"
                "2115188,N,Y\n"
            ),
        }),
        dataset_period="2026-06",
        source_sha256="abc123",
    )

    assert parsed.filings[0].filing_action == "final_sec_era_report"


def test_parses_cp1252_encoded_archive_without_raising() -> None:
    """Real SEC/FINRA monthly advFilingData archives are not consistently UTF-8.

    2025-06 and 2025-07's official archives contain cp1252-encoded accented
    characters (e.g. 0xC9 'E acute') in fund names that raised
    UnicodeDecodeError under the prior utf-8-sig-only decoding -- discovered
    running the real archive in production, not from a synthetic fixture.
    """
    archive = _archive_with_encoding(
        {
            "IA_ADV_Base_A_20250601_20250630.csv": (
                '"FilingID","DateSubmitted","1A","1D","1E1","7B"\n'
                '2115188,"06/24/2025 10:37:17 AM","ÉTUDE CAPITAL","801-66195",129052,"Y"\n'
            ),
            "IA_Schedule_D_7B1_20250601_20250630.csv": (
                '"FilingID","Fund Name","Fund ID","ReferenceID","State","Country",'
                '"Fund Type","Gross Asset Value"\n'
                '2115188,"CRÉDIT FUND",805-123,518607,"Delaware","United States",'
                '"Private Equity Fund",321687148\n'
            ),
        },
        encoding="cp1252",
    )

    parsed = parse_adv_bulk_archive(
        archive,
        dataset_period="2025-06",
        source_sha256="abc123",
    )

    assert parsed.filings[0].adviser_name == "ÉTUDE CAPITAL"
    assert parsed.funds[0].fund_name == "CRÉDIT FUND"


def test_parses_24_hour_date_submitted_with_no_seconds_or_am_pm() -> None:
    """Real advFilingData archives mix DateSubmitted shapes across months.

    Scanning every IA_ADV_Base_A/B file across the full 2025-06..2026-06
    rolling window found three distinct shapes; this covers the one not
    already exercised by the other fixtures: 24-hour, no seconds, no AM/PM
    (e.g. "6/24/2025 7:44"), discovered running the real archive in
    production.
    """
    from datetime import date

    parsed = parse_adv_bulk_archive(
        _archive({
            "IA_ADV_Base_A_20250601_20250630.csv": (
                '"FilingID","DateSubmitted","1A","1D","1E1","7B"\n'
                '2115188,"6/24/2025 7:44","PNC WEALTH","801-66195",129052,"N"\n'
            ),
        }),
        dataset_period="2025-06",
        source_sha256="abc123",
    )

    assert parsed.filings[0].effective_date == date(2025, 6, 24)


def test_ignores_iaadv_base_b_item2_rows_with_no_crd_column() -> None:
    """IA_ADV_Base_B carries only Item 2 fields and has no CRD ("1E1") column.

    The prior _rows() pattern's optional "(?:_A)?" did not actually exclude
    "_B" filenames, silently merging IA_ADV_Base_B's Item-2-only rows into
    base_rows and tripping "IAPD base row is missing FilingID or adviser CRD"
    on every real IA_ADV_Base_B row -- discovered running the real 13-month
    archive window in production, not from a synthetic fixture.
    """
    archive = _archive({
        "IA_ADV_Base_A_20260601_20260630.csv": (
            '"FilingID","DateSubmitted","1A","1D","1E1","7B"\n'
            '2115188,"06/24/2026 10:37:17 AM","PNC WEALTH","801-66195",129052,"N"\n'
        ),
        "IA_ADV_Base_B_20260601_20260630.csv": (
            '"FilingID","2A1","2A2","2A3"\n'
            '2115188,"Y","N","N"\n'
        ),
    })

    parsed = parse_adv_bulk_archive(
        archive,
        dataset_period="2026-06",
        source_sha256="abc123",
    )

    assert parsed.filings[0].adviser_crd_number == "129052"
