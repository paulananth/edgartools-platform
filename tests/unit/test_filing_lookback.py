"""General filing-discovery lookback (10-K/10-Q/8-K/DEF 14A/13F/ADV/etc).

Unlike --ownership-lookback-years/--item-502-lookback-years (which only
bound which already-discovered filings get artifact-fetched/parsed), this
bounds sec_company_filing itself -- filings older than the window are never
written into bronze/silver discovery at all. Default 0 (disabled, full
history) so no existing caller's behavior changes unless
--filing-lookback-years is passed explicitly.
"""

from __future__ import annotations

from datetime import date

import pytest

from edgar_warehouse.application import warehouse_orchestrator as orch
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.loaders.bronze_submission_extractors import filter_rows_by_min_filing_date
from edgar_warehouse.silver_store import SilverDatabase


class TestResolveFilingLookbackYears:
    def test_default_is_zero_disabled(self, monkeypatch):
        monkeypatch.delenv("WAREHOUSE_FILING_LOOKBACK_YEARS", raising=False)
        assert orch._resolve_filing_lookback_years(None) == 0
        assert orch._resolve_filing_lookback_years("") == 0

    def test_explicit_override(self, monkeypatch):
        monkeypatch.delenv("WAREHOUSE_FILING_LOOKBACK_YEARS", raising=False)
        assert orch._resolve_filing_lookback_years(5) == 5
        assert orch._resolve_filing_lookback_years("3") == 3

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("WAREHOUSE_FILING_LOOKBACK_YEARS", "4")
        assert orch._resolve_filing_lookback_years(None) == 4

    def test_explicit_beats_env(self, monkeypatch):
        monkeypatch.setenv("WAREHOUSE_FILING_LOOKBACK_YEARS", "4")
        assert orch._resolve_filing_lookback_years(2) == 2

    def test_rejects_negative(self, monkeypatch):
        monkeypatch.delenv("WAREHOUSE_FILING_LOOKBACK_YEARS", raising=False)
        with pytest.raises(WarehouseRuntimeError, match=">= 0"):
            orch._resolve_filing_lookback_years(-1)


class TestFilterRowsByMinFilingDate:
    def test_none_min_date_is_a_no_op(self):
        rows = [{"filing_date": date(2020, 1, 1)}, {"filing_date": date(2026, 1, 1)}]
        assert filter_rows_by_min_filing_date(rows, None) == rows

    def test_drops_rows_older_than_min_date(self):
        rows = [
            {"accession_number": "old", "filing_date": date(2020, 1, 1)},
            {"accession_number": "boundary", "filing_date": date(2024, 1, 1)},
            {"accession_number": "recent", "filing_date": date(2025, 6, 1)},
        ]
        result = filter_rows_by_min_filing_date(rows, date(2024, 1, 1))
        assert [r["accession_number"] for r in result] == ["boundary", "recent"]

    def test_keeps_rows_with_missing_filing_date(self):
        # An unknown date is not evidence a filing is out of range.
        rows = [{"accession_number": "undated", "filing_date": None}]
        assert filter_rows_by_min_filing_date(rows, date(2024, 1, 1)) == rows


class TestStageSubmissionFilingMinDate:
    """Integration-level: SilverDatabase.stage_submission is the actual
    bronze-discovery write path -- prove filing_min_date controls what lands
    in sec_company_filing, not just what a pure helper returns."""

    def _payload(self, *, accessions_and_dates: list[tuple[str, str, str]]) -> dict:
        return {
            "filings": {
                "recent": {
                    "accessionNumber": [a for a, _, _ in accessions_and_dates],
                    "filingDate": [d for _, d, _ in accessions_and_dates],
                    "reportDate": [d for _, d, _ in accessions_and_dates],
                    "acceptanceDateTime": [""] * len(accessions_and_dates),
                    "act": [""] * len(accessions_and_dates),
                    "form": [f for _, _, f in accessions_and_dates],
                    "fileNumber": [""] * len(accessions_and_dates),
                    "filmNumber": [""] * len(accessions_and_dates),
                    "items": [""] * len(accessions_and_dates),
                    "size": [0] * len(accessions_and_dates),
                    "isXBRL": [0] * len(accessions_and_dates),
                    "isInlineXBRL": [0] * len(accessions_and_dates),
                    "primaryDocument": [""] * len(accessions_and_dates),
                    "primaryDocDescription": [""] * len(accessions_and_dates),
                },
            },
        }

    def test_filing_min_date_excludes_old_filings_from_sec_company_filing(self, tmp_path):
        db = SilverDatabase(str(tmp_path / "silver.duckdb"))
        try:
            payload = self._payload(accessions_and_dates=[
                ("old-10k", "2020-03-01", "10-K"),
                ("recent-8k", "2026-06-01", "8-K"),
            ])
            result = db.stage_submission(
                cik=1800,
                main_payload=payload,
                pagination_payloads=[],
                sync_run_id="run-1",
                raw_object_id="hash-1",
                load_mode="bootstrap_full",
                filing_min_date=date(2024, 1, 1),
            )
            assert result["recent_accessions"] == ["recent-8k"]
            rows = db._conn.execute(
                "SELECT accession_number FROM sec_company_filing WHERE cik = ?", [1800]
            ).fetchall()
            written = {r[0] for r in rows}
            assert written == {"recent-8k"}
        finally:
            db.close()

    def test_filing_min_date_none_keeps_full_history(self, tmp_path):
        db = SilverDatabase(str(tmp_path / "silver.duckdb"))
        try:
            payload = self._payload(accessions_and_dates=[
                ("old-10k", "2020-03-01", "10-K"),
                ("recent-8k", "2026-06-01", "8-K"),
            ])
            result = db.stage_submission(
                cik=1800,
                main_payload=payload,
                pagination_payloads=[],
                sync_run_id="run-1",
                raw_object_id="hash-1",
                load_mode="bootstrap_full",
                filing_min_date=None,
            )
            assert set(result["recent_accessions"]) == {"old-10k", "recent-8k"}
            rows = db._conn.execute(
                "SELECT accession_number FROM sec_company_filing WHERE cik = ?", [1800]
            ).fetchall()
            written = {r[0] for r in rows}
            assert written == {"old-10k", "recent-8k"}
        finally:
            db.close()


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
