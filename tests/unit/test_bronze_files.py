from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from edgar_warehouse.application.runtime_legacy import _write_cik_universe_batches
from edgar_warehouse.domain.models.run_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.manifest_service import planned_writes
from edgar_warehouse.infrastructure.storage import StorageLocation


class BronzeFileContractTests(unittest.TestCase):
    def test_planned_writes_for_bootstrap_recent_10_use_expected_bronze_manifest_path(self) -> None:
        writes = planned_writes(
            command_name="bootstrap-recent-10",
            command_path="bootstrap-recent-10",
            run_id="run-123",
            scope={},
        )

        self.assertEqual(
            writes,
            {
                "bronze": "runs/bootstrap-recent-10/run-123/manifest.json",
                "staging": "staging/runs/bootstrap-recent-10/run-123/manifest.json",
                "silver": "silver/sec/runs/bootstrap-recent-10/run-123/manifest.json",
                "gold": "gold/runs/bootstrap-recent-10/run-123/manifest.json",
                "artifacts": "artifacts/runs/bootstrap-recent-10/run-123/manifest.json",
            },
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
                fetch_date=None,  # not used by the writer
                sync_run_id="run-123",
                batch_size=2,
            )

            batch_file = Path(tmp) / "bronze" / "reference" / "cik_universe" / "runs" / "run-123" / "cik_batches.jsonl"
            self.assertEqual(
                destination,
                str(batch_file),
            )
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
