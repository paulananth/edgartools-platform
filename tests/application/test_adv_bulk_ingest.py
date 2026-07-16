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
