"""individual-filer-company-misclassification map, Ticket 03/04: SEC's own
entityType='other' marks an individual/insider filer (Form 3/4/5/144/13D/13G
filer), not a reporting company. stage_submission must not write these rows
into sec_company/sec_company_address/sec_company_former_name -- their real
filing history in sec_company_filing is untouched (that table is a plain
per-CIK filing log, not a company-universe claim)."""

from __future__ import annotations

from edgar_warehouse.loaders.bronze_submission_extractors import (
    is_reporting_company_entity_type,
)
from edgar_warehouse.silver_store import SilverDatabase


def test_is_reporting_company_entity_type_classifies_known_values():
    assert is_reporting_company_entity_type("operating") is True
    assert is_reporting_company_entity_type("investment") is True
    assert is_reporting_company_entity_type("other") is False
    # Missing/empty entityType fails open -- never observed live to
    # correlate with 'other', so treat as company rather than guess.
    assert is_reporting_company_entity_type(None) is True
    assert is_reporting_company_entity_type("") is True


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
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
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

        assert db.get_company(1548760) is None
        assert db.get_addresses(1548760) == []

        former_names = db.fetch(
            "SELECT * FROM sec_company_former_name WHERE cik = ?", [1548760]
        )
        assert former_names == []

        # Real filing history (Form 4, an ownership filing) is untouched --
        # this is a plain per-CIK filing log, not a company-universe claim.
        filings = db.fetch(
            "SELECT accession_number, form FROM sec_company_filing WHERE cik = ?",
            [1548760],
        )
        assert filings == [{"accession_number": "acc-1", "form": "4"}]
        assert result["rows_written"] >= 1
    finally:
        db.close()


def test_stage_submission_still_writes_company_rows_for_real_company(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
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

        db.stage_submission(
            cik=320193,
            main_payload=main_payload,
            pagination_payloads=[],
            sync_run_id="run-1",
            raw_object_id="raw-1",
            load_mode="daily_incremental",
        )

        company = db.get_company(320193)
        assert company is not None
        assert company["entity_type"] == "operating"
        assert len(db.get_addresses(320193)) == 1
    finally:
        db.close()
