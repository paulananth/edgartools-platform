from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from edgar_warehouse.application.warehouse_orchestrator import _write_cik_universe_batches
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.dataset_path_catalog import default_capture_spec_factory, default_path_resolver
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.infrastructure.run_manifest_builder import planned_writes


class BronzeFileContractTests(unittest.TestCase):
    def test_planned_writes_for_bootstrap_recent_10_use_expected_bronze_manifest_path(self) -> None:
        self.assertEqual(
            planned_writes(
                command_name="bootstrap-recent-10",
                command_path="bootstrap-recent-10",
                run_id="run-123",
                scope={},
            ),
            default_path_resolver().planned_manifest_paths(
                command_name="bootstrap-recent-10",
                command_path="bootstrap-recent-10",
                run_id="run-123",
                scope={},
            ),
        )

    def test_special_daily_index_manifest_paths_remain_unchanged(self) -> None:
        resolver = default_path_resolver()
        self.assertEqual(
            resolver.planned_manifest_paths(
                command_name="load-daily-form-index-for-date",
                command_path="load-daily-form-index-for-date",
                run_id="run-123",
                scope={"target_date": "2026-04-22"},
            )["bronze"],
            "daily-index/date=2026-04-22/run-123/manifest.json",
        )
        self.assertEqual(
            resolver.planned_manifest_paths(
                command_name="catch-up-daily-form-index",
                command_path="catch-up-daily-form-index",
                run_id="run-123",
                scope={"end_date": "2026-04-22"},
            )["bronze"],
            "daily-index/catch-up/end-date=2026-04-22/run-123/manifest.json",
        )

    def test_write_cik_universe_batches_writes_jsonl_batches_to_bronze_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bronze_root = StorageLocation(str(Path(tmp) / "bronze"))
            context = WarehouseCommandContext(
                bronze_root=bronze_root,
                storage_root=StorageLocation(str(Path(tmp) / "warehouse")),
                silver_root=StorageLocation(str(Path(tmp) / "silver")),
                snowflake_export_root=None,
                environment_name="test",
                identity="tester@example.com",
                runtime_mode="bronze_capture",
            )

            destination = _write_cik_universe_batches(
                context=context,
                rows=[{"cik": 1}, {"cik": 2}, {"cik": 3}],
                fetch_date=None,
                sync_run_id="run-123",
                batch_size=2,
            )

            batch_file = (
                Path(tmp)
                / "bronze"
                / "reference"
                / "cik_universe"
                / "runs"
                / "run-123"
                / "cik_batches.jsonl"
            )
            expected_relative_path = default_capture_spec_factory().cik_universe_batches("run-123").relative_path
            self.assertEqual(destination, str(batch_file))
            self.assertTrue(destination.endswith(expected_relative_path))
            self.assertTrue(batch_file.exists())
            self.assertEqual(
                batch_file.read_text().splitlines(),
                [
                    json.dumps({"cik_list": "1,2"}),
                    json.dumps({"cik_list": "3"}),
                ],
            )


if __name__ == "__main__":
    unittest.main()
