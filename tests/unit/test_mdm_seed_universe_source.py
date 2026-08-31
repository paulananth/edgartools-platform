"""Ticket 14: MDM seed-universe defaults to silver source of truth.

DuckDB Retirement Cutover Ticket 05: _seed_mdm_from_silver connects via
SnowflakeSilverReader now, not a real local DuckDB file -- the fixture
below is a minimal .fetch()-based fake satisfying that same seam.
"""

from __future__ import annotations

import argparse
import unittest
from unittest.mock import MagicMock, patch

from edgar_warehouse.mdm import cli as mdm_cli


class _FakeSnowflakeSilverReader:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.closed = False

    def fetch(self, sql: str, params: list | None = None) -> list[dict]:
        assert "sec_tracked_universe" in sql
        return list(self._rows)

    def close(self) -> None:
        self.closed = True


class MdmSeedUniverseSourceTests(unittest.TestCase):
    def test_seed_from_silver_helper_reads_tracked_universe(self) -> None:
        reader = _FakeSnowflakeSilverReader(
            [
                {"cik": 320193, "current_ticker": "AAPL", "exchange": None, "tracking_status": "active"},
                {"cik": 789019, "current_ticker": "MSFT", "exchange": None, "tracking_status": "bootstrap_pending"},
            ]
        )

        with patch.object(mdm_cli, "bulk_upsert_universe", create=True) as bulk:
            # Patch import path used inside helper
            with patch(
                "edgar_warehouse.mdm.universe.bulk_upsert_universe",
                return_value=2,
            ) as bulk2:
                with patch.object(mdm_cli, "_get_mdm_engine", return_value=object()):
                    with patch(
                        "edgar_warehouse.silver_support.snowflake_reader.SnowflakeSilverReader.connect",
                        return_value=reader,
                    ):
                        result = mdm_cli._seed_mdm_from_silver(
                            tracking_status_filter=None,
                            dry_run=False,
                            bookkeeping=MagicMock(),
                        )
        self.assertEqual(result["rows_found"], 2)
        # bulk_upsert_universe mocked to return 2 per status group (active + bootstrap_pending)
        self.assertEqual(result["rows_migrated"], 4)
        self.assertIn("active", result["by_status"])
        self.assertEqual(bulk2.call_count, 2)
        self.assertTrue(reader.closed)

    def test_seed_universe_default_source_is_silver(self) -> None:
        args = argparse.Namespace(
            source="silver",
            limit=None,
            tracking_status="active",
        )
        with patch.object(
            mdm_cli,
            "_seed_mdm_from_silver",
            return_value={"status": "ok", "rows_found": 1, "rows_migrated": 1},
        ) as seed:
            with patch.object(mdm_cli, "_bookkeeping_store", return_value=MagicMock()):
                with patch("builtins.print") as pr:
                    code = mdm_cli._handle_seed_universe(args)
            self.assertEqual(code, 0)
            seed.assert_called_once()
            printed = " ".join(str(c) for c in pr.call_args_list)
            self.assertIn("silver", printed)


if __name__ == "__main__":
    unittest.main()
