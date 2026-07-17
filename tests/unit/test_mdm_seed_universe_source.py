"""Ticket 14: MDM seed-universe defaults to silver source of truth."""

from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb

from edgar_warehouse.mdm import cli as mdm_cli


class MdmSeedUniverseSourceTests(unittest.TestCase):
    def test_seed_from_silver_helper_reads_tracked_universe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "silver.duckdb"
            conn = duckdb.connect(str(db_path))
            conn.execute(
                """
                CREATE TABLE sec_tracked_universe (
                    cik BIGINT, current_ticker TEXT, tracking_status TEXT
                );
                INSERT INTO sec_tracked_universe VALUES
                  (320193, 'AAPL', 'active'),
                  (789019, 'MSFT', 'bootstrap_pending');
                """
            )
            conn.close()

            with patch.object(mdm_cli, "bulk_upsert_universe", create=True) as bulk:
                # Patch import path used inside helper
                with patch(
                    "edgar_warehouse.mdm.universe.bulk_upsert_universe",
                    return_value=2,
                ) as bulk2:
                    with patch.object(mdm_cli, "_get_mdm_engine", return_value=object()):
                        result = mdm_cli._seed_mdm_from_silver(
                            silver_path=str(db_path),
                            tracking_status_filter=None,
                            dry_run=False,
                        )
            self.assertEqual(result["rows_found"], 2)
            # bulk_upsert_universe mocked to return 2 per status group (active + bootstrap_pending)
            self.assertEqual(result["rows_migrated"], 4)
            self.assertIn("active", result["by_status"])
            self.assertEqual(bulk2.call_count, 2)

    def test_seed_universe_default_source_is_silver(self) -> None:
        args = argparse.Namespace(
            source="silver",
            silver_path=None,
            limit=None,
            tracking_status="active",
        )
        with patch.object(
            mdm_cli,
            "_seed_mdm_from_silver",
            return_value={"status": "ok", "rows_found": 1, "rows_migrated": 1},
        ) as seed:
            with patch("builtins.print") as pr:
                code = mdm_cli._handle_seed_universe(args)
            self.assertEqual(code, 0)
            seed.assert_called_once()
            printed = " ".join(str(c) for c in pr.call_args_list)
            self.assertIn("silver", printed)


if __name__ == "__main__":
    unittest.main()
