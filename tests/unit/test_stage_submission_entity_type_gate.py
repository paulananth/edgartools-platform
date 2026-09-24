"""individual-filer-company-misclassification map, Ticket 03/04: SEC's own
entityType='other' marks an individual/insider filer (Form 3/4/5/144/13D/13G
filer), not a reporting company. stage_submission must not write these rows
into sec_company/sec_company_address/sec_company_former_name -- their real
filing history in sec_company_filing is untouched (that table is a plain
per-CIK filing log, not a company-universe claim).

The company tables are landing-only (silver-merge-engine-migration Ticket
06b), so these tests assert on the rows recorded for landing."""

from __future__ import annotations

import pytest

from edgar_warehouse.loaders.bronze_submission_extractors import is_individual_filer
from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer
from edgar_warehouse.silver_landing_store import SilverLandingStore


def _payload(entity_type, forms, *, sic="", tickers=()):
    return {
        "entityType": entity_type,
        "sic": sic,
        "tickers": list(tickers),
        "filings": {"recent": {"form": list(forms)}},
    }


@pytest.mark.parametrize(
    ("payload", "individual"),
    [
        # Shaped on real bronze filers (2026-09-24 scan of all 76,230).
        (_payload("other", ["4", "4", "3", "144"]), True),  # COOK TIMOTHY D
        (_payload("other", ["SC 13G/A", "4"]), True),
        (_payload("other", ["20-F", "6-K"], sic="1311", tickers=["SHEL"]), False),
        (_payload("other", ["20-F", "6-K"], sic="3559", tickers=["ASML"]), False),
        (_payload("other", ["10-K", "10-Q", "8-K"]), False),
        (_payload("other", ["N-CSR", "485BPOS"]), False),  # a fund
        (_payload("other", ["13F-HR"]), False),  # a 13F manager
        (_payload("other", ["D", "D/A"]), False),  # a Form D issuer
        # Ownership forms only, but an industry code or a ticker says entity.
        (_payload("other", ["SC 13D"], sic="6799"), False),
        (_payload("other", ["4"], tickers=["XYZ"]), False),
        (_payload("operating", ["4"]), False),
        (_payload("investment", ["4"]), False),
        # Fail open, as before: never guess a CIK out of the universe.
        (_payload(None, ["4"]), False),
        (_payload("", ["4"]), False),
        (_payload("other", []), False),
    ],
)
def test_an_individual_is_decided_by_what_it_files_not_by_entity_type_alone(
    payload, individual
):
    assert is_individual_filer(payload) is individual


def _filing_entry(accession_number, form):
    return {
        "accessionNumber": accession_number,
        "filingDate": "2025-01-01",
        "reportDate": "2024-12-31",
        "acceptanceDateTime": "2025-01-01T12:00:00",
        "act": "34",
        "form": form,
        "fileNumber": "001-12345",
        "filmNumber": "25000001",
        "items": "",
        "size": 1000,
        "isXBRL": 1,
        "isInlineXBRL": 1,
        "primaryDocument": "doc.htm",
        "primaryDocDescription": form,
    }


_COLUMNS = [
    "accessionNumber", "filingDate", "reportDate", "acceptanceDateTime",
    "act", "form", "fileNumber", "filmNumber", "items", "size", "isXBRL",
    "isInlineXBRL", "primaryDocument", "primaryDocDescription",
]


def _columns(entries: list[dict]) -> dict:
    columns: dict[str, list] = {col: [] for col in _COLUMNS}
    for entry in entries:
        for col in _COLUMNS:
            columns[col].append(entry[col])
    return columns


def test_stage_submission_skips_company_rows_for_individual_filer(tmp_path):
    landing = LandingExportBuffer()
    db = SilverLandingStore(landing_export=landing)
    try:
        main_payload = {
            "name": "Zuckerberg Mark",
            "entityType": "other",
            "formerNames": [{"name": "Old Name Inc", "date": "2020-01-01T00:00:00"}],
            "addresses": {
                "business": {
                    "street1": "1 Hacker Way",
                    "city": "Menlo Park",
                    "stateOrCountry": "CA",
                    "zipCode": "94025",
                },
            },
            "filings": {"recent": _columns([_filing_entry("acc-1", "4")])},
        }

        result = db.stage_submission(
            cik=1548760,
            main_payload=main_payload,
            pagination_payloads=[],
            sync_run_id="run-1",
            raw_object_id="raw-1",
            load_mode="daily_incremental",
        )

        recorded = landing.tables()
        assert "sec_company" not in recorded
        assert "sec_company_address" not in recorded
        assert "sec_company_former_name" not in recorded
        assert result["company_rows_written"] == 0

        # Real filing history (Form 4, an ownership filing) is untouched --
        # this is a plain per-CIK filing log, not a company-universe claim.
        assert [row["accession_number"] for row in recorded["sec_company_filing"]] == ["acc-1"]
        filing = db.get_filing("acc-1")
        assert (filing["cik"], filing["form"]) == (1548760, "4")
        assert result["rows_written"] >= 1
    finally:
        db.close()


def test_stage_submission_still_writes_company_rows_for_real_company(tmp_path):
    landing = LandingExportBuffer()
    db = SilverLandingStore(landing_export=landing)
    try:
        main_payload = {
            "name": "Test Co",
            "entityType": "operating",
            "addresses": {
                "business": {
                    "street1": "1 Infinite Loop",
                    "city": "Cupertino",
                    "stateOrCountry": "CA",
                    "zipCode": "95014",
                },
            },
            "filings": {"recent": _columns([_filing_entry("acc-2", "10-K")])},
        }

        result = db.stage_submission(
            cik=320193,
            main_payload=main_payload,
            pagination_payloads=[],
            sync_run_id="run-1",
            raw_object_id="raw-1",
            load_mode="daily_incremental",
        )

        recorded = landing.tables()
        assert [row["entity_type"] for row in recorded["sec_company"]] == ["operating"]
        assert len(recorded["sec_company_address"]) == 1
        assert result["company_rows_written"] == 1
    finally:
        db.close()


def test_stage_submission_writes_company_rows_for_a_foreign_issuer_sec_marks_other():
    """Shell plc: SEC says 'other', files 20-F, carries SIC 1311 and a ticker.

    The old gate dropped it from sec_company; it is an entity (2026-09-24).
    """
    landing = LandingExportBuffer()
    db = SilverLandingStore(landing_export=landing)
    try:
        result = db.stage_submission(
            cik=1306965,
            main_payload={
                "name": "Shell plc",
                "entityType": "other",
                "sic": "1311",
                "tickers": ["SHEL"],
                "addresses": {
                    "business": {
                        "street1": "Shell Centre",
                        "city": "London",
                        "zipCode": "SE1 7NA",
                    },
                },
                "filings": {"recent": _columns([_filing_entry("acc-3", "20-F")])},
            },
            pagination_payloads=[],
            sync_run_id="run-1",
            raw_object_id="raw-1",
            load_mode="daily_incremental",
        )
        recorded = landing.tables()
        assert [row["cik"] for row in recorded["sec_company"]] == [1306965]
        assert result["company_rows_written"] == 1
    finally:
        db.close()
