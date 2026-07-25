"""Form 3/4/5 ownership lookback (default 2 years)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from edgar_warehouse.application import warehouse_orchestrator as orch
from edgar_warehouse.application.errors import WarehouseRuntimeError


class TestResolveOwnershipLookbackYears:
    def test_default_is_two_years(self, monkeypatch):
        monkeypatch.delenv("WAREHOUSE_OWNERSHIP_LOOKBACK_YEARS", raising=False)
        assert orch._resolve_ownership_lookback_years(None) == 2
        assert orch._resolve_ownership_lookback_years("") == 2

    def test_explicit_override(self, monkeypatch):
        monkeypatch.delenv("WAREHOUSE_OWNERSHIP_LOOKBACK_YEARS", raising=False)
        assert orch._resolve_ownership_lookback_years(0) == 0
        assert orch._resolve_ownership_lookback_years(5) == 5
        assert orch._resolve_ownership_lookback_years("3") == 3

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("WAREHOUSE_OWNERSHIP_LOOKBACK_YEARS", "0")
        assert orch._resolve_ownership_lookback_years(None) == 0

    def test_explicit_beats_env(self, monkeypatch):
        monkeypatch.setenv("WAREHOUSE_OWNERSHIP_LOOKBACK_YEARS", "0")
        assert orch._resolve_ownership_lookback_years(2) == 2

    def test_rejects_negative(self, monkeypatch):
        monkeypatch.delenv("WAREHOUSE_OWNERSHIP_LOOKBACK_YEARS", raising=False)
        with pytest.raises(WarehouseRuntimeError, match=">= 0"):
            orch._resolve_ownership_lookback_years(-1)


class TestOwnershipMinFilingDate:
    def test_two_year_window(self):
        assert orch._ownership_min_filing_date(2, as_of=date(2026, 7, 25)) == date(
            2024, 7, 25
        )

    def test_zero_disables(self):
        assert orch._ownership_min_filing_date(0, as_of=date(2026, 7, 25)) is None

    def test_leap_day_clamps(self):
        assert orch._ownership_min_filing_date(1, as_of=date(2024, 2, 29)) == date(
            2023, 2, 28
        )


class TestOwnershipFilingDate:
    def test_prefers_filing_date(self):
        assert orch._ownership_filing_date(
            {"filing_date": "2025-01-15", "report_date": "2024-12-01"}
        ) == date(2025, 1, 15)

    def test_falls_back_to_report_date(self):
        assert orch._ownership_filing_date({"report_date": date(2024, 6, 1)}) == date(
            2024, 6, 1
        )

    def test_none_when_missing(self):
        assert orch._ownership_filing_date({}) is None
        assert orch._ownership_filing_date(None) is None


class TestConfiguredParserAccessionsLookback:
    def _db(self, filings: dict[str, dict]) -> MagicMock:
        db = MagicMock()
        db.get_filing.side_effect = lambda acc: filings.get(acc)
        return db

    def test_filters_old_ownership_keeps_recent_and_non_ownership(self, monkeypatch):
        monkeypatch.delenv("WAREHOUSE_OWNERSHIP_LOOKBACK_YEARS", raising=False)
        monkeypatch.delenv("WAREHOUSE_ITEM_502_LOOKBACK_YEARS", raising=False)
        as_of = date(2026, 7, 25)
        filings = {
            "old-form4": {
                "form": "4",
                "filing_date": date(2023, 1, 1),
                "items": None,
            },
            "recent-form4": {
                "form": "4",
                "filing_date": date(2025, 6, 1),
                "items": None,
            },
            "boundary-form3": {
                "form": "3",
                "filing_date": date(2024, 7, 25),
                "items": None,
            },
            "adv": {"form": "ADV", "filing_date": date(2010, 1, 1), "items": None},
            "undated-form4": {"form": "4", "filing_date": None, "report_date": None},
            "old-item502": {
                "form": "8-K",
                "filing_date": date(2023, 1, 1),
                "items": "5.02",
            },
            "recent-item502": {
                "form": "8-K",
                "filing_date": date(2025, 6, 1),
                "items": "5.02",
            },
            "unrelated-8k": {
                "form": "8-K",
                "filing_date": date(2025, 6, 1),
                "items": "2.02",
            },
        }
        db = self._db(filings)
        selected = orch._configured_parser_accessions(
            db,
            list(filings),
            ownership_lookback_years=2,
            as_of=as_of,
        )
        assert selected == [
            "recent-form4",
            "boundary-form3",
            "adv",
            "undated-form4",
            "recent-item502",
        ]
        assert "old-form4" not in selected
        assert "old-item502" not in selected
        assert "unrelated-8k" not in selected

    def test_zero_lookback_keeps_all_ownership(self):
        filings = {
            "old-form4": {
                "form": "4",
                "filing_date": date(2010, 1, 1),
                "items": None,
            },
            "recent-form4": {
                "form": "4",
                "filing_date": date(2025, 6, 1),
                "items": None,
            },
        }
        db = self._db(filings)
        selected = orch._configured_parser_accessions(
            db,
            list(filings),
            ownership_lookback_years=0,
            item_502_lookback_years=0,
            as_of=date(2026, 7, 25),
        )
        assert selected == ["old-form4", "recent-form4"]

    def test_item_502_lookback_independent_of_ownership(self, monkeypatch):
        monkeypatch.delenv("WAREHOUSE_OWNERSHIP_LOOKBACK_YEARS", raising=False)
        monkeypatch.delenv("WAREHOUSE_ITEM_502_LOOKBACK_YEARS", raising=False)
        as_of = date(2026, 7, 25)
        filings = {
            "old-form4": {
                "form": "4",
                "filing_date": date(2023, 1, 1),
                "items": None,
            },
            "old-item502": {
                "form": "8-K",
                "filing_date": date(2023, 1, 1),
                "items": "5.02",
            },
            "recent-item502": {
                "form": "8-K",
                "filing_date": date(2025, 1, 1),
                "items": "5.02",
            },
        }
        db = self._db(filings)
        selected = orch._configured_parser_accessions(
            db,
            list(filings),
            ownership_lookback_years=0,
            item_502_lookback_years=2,
            as_of=as_of,
        )
        assert selected == ["old-form4", "recent-item502"]


class TestParseOwnershipBronzeLookback:
    def test_skips_old_filings_by_default(self, monkeypatch, tmp_path):
        monkeypatch.delenv("WAREHOUSE_OWNERSHIP_LOOKBACK_YEARS", raising=False)
        from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
        from edgar_warehouse.infrastructure.object_storage import StorageLocation

        context = WarehouseCommandContext(
            bronze_root=StorageLocation(str(tmp_path / "bronze")),
            storage_root=StorageLocation(str(tmp_path / "silver_root")),
            silver_root=StorageLocation(str(tmp_path / "silver")),
            snowflake_export_root=None,
            environment_name="test",
            identity="test@example.com",
            runtime_mode="bronze_capture",
        )

        as_of = date.today()
        old = (as_of.replace(year=as_of.year - 3)).isoformat()
        recent = (as_of.replace(year=as_of.year - 1)).isoformat()
        filings = [
            {
                "accession_number": "old-acc",
                "cik": 1,
                "form": "4",
                "filing_date": old,
                "report_date": old,
            },
            {
                "accession_number": "recent-acc",
                "cik": 1,
                "form": "4",
                "filing_date": recent,
                "report_date": recent,
            },
        ]

        class FakeDB:
            def __init__(self) -> None:
                self.seen: list[str] = []

            def fetch(self, sql: str, params=None):
                if "sec_company_filing" in sql:
                    return list(filings)
                if "sec_ownership_reporting_owner" in sql:
                    return []
                return []

            def get_filing_attachments(self, accession_number: str):
                return []

            def get_raw_object(self, raw_object_id: str):
                return None

            def merge_ownership_reporting_owners(self, rows, sync_run_id):
                return 0

            def merge_ownership_non_derivative_txns(self, rows, sync_run_id):
                return 0

            def merge_ownership_derivative_txns(self, rows, sync_run_id):
                return 0

        db = FakeDB()

        def fake_read(db_arg, accession):
            db.seen.append(accession)
            raise orch.WarehouseRuntimeError("no artifact")

        monkeypatch.setattr(orch, "_read_primary_artifact_bytes", fake_read)
        metrics: dict = {}
        orch._run_parse_ownership_bronze(
            context=context,
            db=db,
            sync_run_id="run-test",
            metrics=metrics,
        )
        assert db.seen == ["recent-acc"]
        assert metrics["ownership_lookback_years"] == 2
        assert metrics["ownership_lookback_skipped"] == 1
        assert metrics["ownership_min_filing_date"] is not None

    def test_zero_lookback_includes_old(self, monkeypatch, tmp_path):
        from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
        from edgar_warehouse.infrastructure.object_storage import StorageLocation

        context = WarehouseCommandContext(
            bronze_root=StorageLocation(str(tmp_path / "bronze")),
            storage_root=StorageLocation(str(tmp_path / "silver_root")),
            silver_root=StorageLocation(str(tmp_path / "silver")),
            snowflake_export_root=None,
            environment_name="test",
            identity="test@example.com",
            runtime_mode="bronze_capture",
        )
        as_of = date.today()
        old = (as_of.replace(year=as_of.year - 5)).isoformat()
        filings = [
            {
                "accession_number": "old-acc",
                "cik": 1,
                "form": "4",
                "filing_date": old,
                "report_date": old,
            },
        ]

        class FakeDB:
            def fetch(self, sql: str, params=None):
                if "sec_company_filing" in sql:
                    return list(filings)
                if "sec_ownership_reporting_owner" in sql:
                    return []
                return []

            def get_filing_attachments(self, accession_number: str):
                return []

            def get_raw_object(self, raw_object_id: str):
                return None

            def merge_ownership_reporting_owners(self, rows, sync_run_id):
                return 0

            def merge_ownership_non_derivative_txns(self, rows, sync_run_id):
                return 0

            def merge_ownership_derivative_txns(self, rows, sync_run_id):
                return 0

        seen: list[str] = []

        def fake_read(db_arg, accession):
            seen.append(accession)
            raise orch.WarehouseRuntimeError("no artifact")

        monkeypatch.setattr(orch, "_read_primary_artifact_bytes", fake_read)
        metrics: dict = {}
        orch._run_parse_ownership_bronze(
            context=context,
            db=FakeDB(),
            sync_run_id="run-test",
            metrics=metrics,
            ownership_lookback_years=0,
        )
        assert seen == ["old-acc"]
        assert metrics["ownership_lookback_years"] == 0
        assert metrics["ownership_lookback_skipped"] == 0
        assert metrics["ownership_min_filing_date"] is None
