from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

import pytest

from edgar_warehouse.application.command_context_factory import build_warehouse_context
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.application import warehouse_orchestrator


class TrackingStateDb:
    def __init__(self, ciks: list[int]) -> None:
        self.ciks = ciks

    def get_tracked_ciks(self, tracking_status_filter: str = "active") -> list[int]:
        self.tracking_status_filter = tracking_status_filter
        return self.ciks


class PipelineTrackingStateTests(unittest.TestCase):
    def test_gold_refresh_context_does_not_require_mdm_database_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "EDGAR_IDENTITY": "dev@example.com",
                "WAREHOUSE_RUNTIME_MODE": "bronze_capture",
                "WAREHOUSE_BRONZE_ROOT": os.path.join(tmp, "bronze"),
                "WAREHOUSE_STORAGE_ROOT": os.path.join(tmp, "warehouse"),
                "SERVING_EXPORT_ROOT": os.path.join(tmp, "serving"),
            }
            with patch.dict(os.environ, env, clear=True):
                context = build_warehouse_context("gold-refresh")

            self.assertIsNotNone(context.serving_export_root)

    def test_bootstrap_target_resolution_reads_silver_tracking_state(self) -> None:
        db = TrackingStateDb([100, 200, 300])

        with patch.object(warehouse_orchestrator, "_get_mdm_tracked_ciks") as mdm:
            result = warehouse_orchestrator._resolve_bootstrap_target_ciks(
                db=db,
                raw_ciks=None,
                command_name="bootstrap-next",
                tracking_status_filter="bootstrap_pending",
                cik_limit=2,
                cik_offset=1,
            )

        mdm.assert_not_called()
        self.assertEqual(result, [200, 300])
        self.assertEqual(db.tracking_status_filter, "bootstrap_pending")

    def test_bootstrap_target_resolution_mentions_silver_when_empty(self) -> None:
        db = TrackingStateDb([])

        with pytest.raises(WarehouseRuntimeError, match="silver tracking state"):
            warehouse_orchestrator._resolve_bootstrap_target_ciks(
                db=db,
                raw_ciks=None,
                command_name="bootstrap-next",
                tracking_status_filter="bootstrap_pending",
            )

    def test_daily_incremental_filter_reads_silver_active_state(self) -> None:
        db = TrackingStateDb([100, 300])

        with patch.object(warehouse_orchestrator, "_get_mdm_tracked_ciks") as mdm:
            result = warehouse_orchestrator._filter_ciks_to_universe([100, 200, 300], db=db)

        mdm.assert_not_called()
        self.assertEqual(result, [100, 300])

    def test_daily_incremental_filter_cold_start_passes_all_impacted_ciks(self) -> None:
        db = TrackingStateDb([])

        result = warehouse_orchestrator._filter_ciks_to_universe([100, 200, 300], db=db)

        self.assertEqual(result, [100, 200, 300])

    def test_silver_database_get_tracked_ciks_supports_status_sets(self) -> None:
        from edgar_warehouse.silver_store import SilverDatabase

        with tempfile.TemporaryDirectory() as tmp:
            db = SilverDatabase(os.path.join(tmp, "silver.duckdb"))
            try:
                db.upsert_company_sync_state({"cik": 300, "tracking_status": "active"})
                db.upsert_company_sync_state({"cik": 100, "tracking_status": "bootstrap_pending"})
                db.upsert_company_sync_state({"cik": 200, "tracking_status": "paused"})

                self.assertEqual(db.get_tracked_ciks("active,bootstrap_pending"), [100, 300])
                self.assertEqual(db.get_tracked_ciks("all"), [100, 200, 300])
            finally:
                db.close()

    def test_ciks_filing_form15_matches_domestic_and_foreign_variants(self) -> None:
        """Seed-universe ticket 03: Form 15 (deregistration) demotes a CIK out
        of the active universe. Real EDGAR daily-index form strings confirmed
        live (2026-07-22): 15-12B/15-12G/15-15D (domestic), 15F-12B/15F-12G/
        15F-15D (foreign private issuer), amendments suffixed "/A"."""
        rows = [
            {"cik": 1, "form": "15-12G"},
            {"cik": 2, "form": "15-12G/A"},
            {"cik": 3, "form": "15-15D"},
            {"cik": 4, "form": "15F-12B"},
            {"cik": 5, "form": "10-K"},
            {"cik": 6, "form": "S-1"},
            {"cik": 7, "form": "25-NSE"},  # Form 25 deliberately excluded (ticket 03)
        ]

        result = warehouse_orchestrator._ciks_filing_form15(rows)

        self.assertEqual(result, [1, 2, 3, 4])

    def test_demote_deregistered_ciks_always_overwrites_active_status(self) -> None:
        """Unlike _seed_silver_tracking_status, demotion must overwrite an
        existing 'active' row -- a company filing Form 15 today was, by
        definition, already tracked."""
        from datetime import UTC, datetime
        from edgar_warehouse.silver_store import SilverDatabase

        with tempfile.TemporaryDirectory() as tmp:
            db = SilverDatabase(os.path.join(tmp, "silver.duckdb"))
            try:
                db.upsert_company_sync_state({"cik": 500, "tracking_status": "active"})

                warehouse_orchestrator._demote_deregistered_ciks(db, [500], datetime.now(UTC))

                self.assertEqual(db.get_company_sync_state(500)["tracking_status"], "deregistered")
            finally:
                db.close()

    def test_daily_incremental_demotes_form15_ciks_and_excludes_from_universe(self) -> None:
        """End-to-end: a Form 15 filing seen in a daily-index batch demotes
        that CIK, and _filter_ciks_to_universe (run right after, in the real
        _capture_bronze_raw flow) then excludes it from this run's selected
        CIKs -- no wasted bootstrap call on a company that just deregistered."""
        from datetime import UTC, datetime
        from edgar_warehouse.silver_store import SilverDatabase

        with tempfile.TemporaryDirectory() as tmp:
            db = SilverDatabase(os.path.join(tmp, "silver.duckdb"))
            try:
                db.upsert_company_sync_state({"cik": 700, "tracking_status": "active"})
                db.upsert_company_sync_state({"cik": 800, "tracking_status": "active"})
                impacted_ciks = [700, 800]
                form_15_ciks = warehouse_orchestrator._ciks_filing_form15(
                    [{"cik": 700, "form": "15-12G"}, {"cik": 800, "form": "10-K"}]
                )

                warehouse_orchestrator._seed_silver_tracking_status(db, impacted_ciks, tracking_status="active")
                warehouse_orchestrator._demote_deregistered_ciks(db, form_15_ciks, datetime.now(UTC))
                selected = warehouse_orchestrator._filter_ciks_to_universe(impacted_ciks, db=db)

                self.assertEqual(selected, [800])
            finally:
                db.close()
