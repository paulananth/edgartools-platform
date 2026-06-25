"""stage_submission must merge recent + ALL pagination-file rows in one
merge_filings call instead of one call per pagination file -- a well-filed
company can have 50+ pagination files, and each merge_filings call used to
pay its own staging-table overhead. This also exercises the cross-call dedup
path: the same accession_number appearing in two different pagination files
must end up with the later file's values, matching the old sequential
per-file merge order."""

from __future__ import annotations

from edgar_warehouse.silver_store import SilverDatabase


def _filing_entry(accession_number, form, **overrides):
    entry = {
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
    entry.update(overrides)
    return entry


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


def _recent_payload(entries: list[dict]) -> dict:
    """Shape stage_recent_filing_loader expects: filings.recent.<column>."""
    return {"filings": {"recent": _columns(entries)}}


def _pagination_payload(entries: list[dict]) -> dict:
    """Shape stage_pagination_filing_loader expects: filings.<column> (no nesting)."""
    return {"filings": _columns(entries)}


def test_stage_submission_merges_recent_and_pagination_in_one_call(tmp_path, monkeypatch):
    merge_calls: list[int] = []
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        original_merge_filings = db.merge_filings

        def _counting_merge_filings(rows, sync_run_id):
            merge_calls.append(len(rows))
            return original_merge_filings(rows, sync_run_id)

        monkeypatch.setattr(db, "merge_filings", _counting_merge_filings)

        main_payload = {
            "name": "Test Co",
            **_recent_payload([_filing_entry("acc-recent-1", "10-K")]),
        }
        pagination_payloads = [
            ("page-1.json", _pagination_payload([_filing_entry("acc-page-1", "10-Q")])),
            (
                "page-2.json",
                _pagination_payload(
                    [
                        _filing_entry("acc-page-2", "8-K"),
                        # Same accession as page-1's row, with different form --
                        # later file (page-2) must win, matching old sequential
                        # per-file merge order.
                        _filing_entry("acc-page-1", "10-Q/A"),
                    ]
                ),
            ),
        ]

        result = db.stage_submission(
            cik=320193,
            main_payload=main_payload,
            pagination_payloads=pagination_payloads,
            sync_run_id="run-1",
            raw_object_id="raw-1",
            load_mode="bootstrap_full",
        )

        # Exactly ONE merge_filings call covering recent + both pagination
        # files combined (not one call per pagination file).
        assert merge_calls == [4]
        assert result["rows_written"] >= 4

        stored = db.fetch(
            "SELECT accession_number, form FROM sec_company_filing ORDER BY accession_number"
        )
        by_accession = {row["accession_number"]: row["form"] for row in stored}
        assert by_accession["acc-recent-1"] == "10-K"
        assert by_accession["acc-page-2"] == "8-K"
        assert by_accession["acc-page-1"] == "10-Q/A"
    finally:
        db.close()
