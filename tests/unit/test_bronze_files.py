from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from edgar_warehouse.application.warehouse_orchestrator import (
    _execute_warehouse_infrastructure_validation,
    _gold_publication_enabled,
    _interleave_round_robin,
    _snowflake_publication_enabled,
    _write_cik_universe_batches,
)
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.dataset_path_catalog import (
    default_capture_spec_factory,
    default_path_resolver,
)
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.infrastructure.run_manifest_builder import planned_writes


class BronzeFileContractTests(unittest.TestCase):
    def test_bootstrap_next_silver_only_disables_gold_publication(self) -> None:
        self.assertTrue(_gold_publication_enabled("bootstrap-next", {}))
        self.assertFalse(
            _gold_publication_enabled("bootstrap-next", {"silver_only": True})
        )
        self.assertTrue(_gold_publication_enabled("gold-refresh", {"silver_only": True}))
        self.assertTrue(_snowflake_publication_enabled("seed-universe", {}))
        self.assertFalse(
            _snowflake_publication_enabled(
                "bootstrap-next", {"silver_only": True}
            )
        )

    def test_infrastructure_validation_silver_only_omits_gold_and_exports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = WarehouseCommandContext(
                bronze_root=StorageLocation(str(root / "bronze")),
                storage_root=StorageLocation(str(root / "warehouse")),
                silver_root=StorageLocation(str(root / "silver")),
                snowflake_export_root=StorageLocation(str(root / "snowflake")),
                environment_name="test",
                identity="tester@example.com",
                runtime_mode="infrastructure_validation",
            )

            payload = _execute_warehouse_infrastructure_validation(
                context=context,
                command_name="bootstrap-next",
                arguments={
                    "limit": 100,
                    "run_id": "silver-only-run",
                    "silver_only": True,
                    "tracking_status_filter": "bootstrap_pending",
                },
            )
            default_payload = _execute_warehouse_infrastructure_validation(
                context=context,
                command_name="bootstrap-next",
                arguments={
                    "limit": 100,
                    "run_id": "default-publication-run",
                    "tracking_status_filter": "bootstrap_pending",
                },
            )

        layers = {write["layer"] for write in payload["writes"]}
        self.assertNotIn("gold", layers)
        self.assertNotIn("snowflake_export", layers)
        self.assertIn("silver", layers)

        default_layers = {write["layer"] for write in default_payload["writes"]}
        self.assertIn("gold", default_layers)
        self.assertIn("snowflake_export", default_layers)

    def test_planned_writes_for_bootstrap_next_use_expected_manifest_paths(self) -> None:
        self.assertEqual(
            planned_writes(
                command_name="bootstrap-next",
                command_path="bootstrap-next",
                run_id="run-123",
                scope={"cik_limit": 100, "tracking_status_filter": "bootstrap_pending"},
            ),
            {
                "bronze": "runs/bootstrap-next/run-123/manifest.json",
                "staging": "staging/runs/bootstrap-next/run-123/manifest.json",
                "silver": "silver/sec/runs/bootstrap-next/run-123/manifest.json",
                "gold": "gold/runs/bootstrap-next/run-123/manifest.json",
                "artifacts": "artifacts/runs/bootstrap-next/run-123/manifest.json",
            },
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
            self.assertTrue(destination.replace("\\", "/").endswith(expected_relative_path))
            self.assertTrue(batch_file.exists())
            self.assertEqual(
                batch_file.read_text().splitlines(),
                [
                    json.dumps({"cik_list": "1,2"}),
                    json.dumps({"cik_list": "3"}),
                ],
            )

    def test_interleave_round_robin_cycles_across_shards_and_skips_exhausted(self) -> None:
        """Ticket 12: round-robin flatten cycles shard0/1/2 per round, skipping
        exhausted shards (shard3 has none, shard0 has an extra 2nd-round batch)."""
        per_shard_batches = [
            [["10", "20"], ["30"]],  # shard 0: 2 batches
            [["110", "120"]],  # shard 1: 1 batch
            [["210"]],  # shard 2: 1 batch
            [],  # shard 3: no batches
        ]

        result = _interleave_round_robin(per_shard_batches)

        self.assertEqual(
            result,
            [["10", "20"], ["110", "120"], ["210"], ["30"]],
        )

    def test_write_cik_universe_batches_shard_aware_interleaves_across_shards(self) -> None:
        """Ticket 12: shard_aware=True splits by shard band first, then
        round-robin interleaves each shard's batches into cik_batches.jsonl."""
        manifest = {
            "shard_count": 4,
            "schema_version": "1",
            "created_at": "2026-08-08T00:00:00Z",
            "bands": [
                {"shard_index": 0, "cik_min": 0, "cik_max": 99},
                {"shard_index": 1, "cik_min": 100, "cik_max": 199},
                {"shard_index": 2, "cik_min": 200, "cik_max": 299},
                {"shard_index": 3, "cik_min": 300, "cik_max": 9999999},
            ],
            "checksums": {"0": "a", "1": "b", "2": "c", "3": "d"},
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            context = WarehouseCommandContext(
                bronze_root=StorageLocation(str(Path(tmp) / "bronze")),
                storage_root=StorageLocation("s3://fake-bucket/warehouse"),
                silver_root=StorageLocation(str(Path(tmp) / "silver")),
                snowflake_export_root=None,
                environment_name="test",
                identity="tester@example.com",
                runtime_mode="bronze_capture",
            )

            # ascending CIK order, as _list_bronze_submission_ciks produces:
            # shard0: 10, 20, 30 / shard1: 110, 120 / shard2: 210
            ciks = [10, 20, 30, 110, 120, 210]
            rows = [{"cik": cik} for cik in ciks]

            with patch(
                "edgar_warehouse.application.warehouse_orchestrator.read_bytes",
                return_value=manifest_bytes,
            ) as mock_read_bytes:
                destination = _write_cik_universe_batches(
                    context=context,
                    rows=rows,
                    fetch_date=None,
                    sync_run_id="run-shard-aware",
                    batch_size=2,
                    shard_aware=True,
                )

            mock_read_bytes.assert_called_once()
            called_path: str = mock_read_bytes.call_args[0][0]
            self.assertIn("shard-manifest.json", called_path)

            lines = Path(destination).read_text().splitlines()
            self.assertEqual(
                lines,
                [
                    json.dumps({"cik_list": "10,20"}),  # shard0 batch0
                    json.dumps({"cik_list": "110,120"}),  # shard1 batch0
                    json.dumps({"cik_list": "210"}),  # shard2 batch0
                    json.dumps({"cik_list": "30"}),  # shard0 batch1 (round 2)
                ],
            )

    def test_write_cik_universe_batches_shard_aware_falls_back_when_manifest_missing(
        self,
    ) -> None:
        """Ticket 12: mirrors the read-side shard_manifest_missing_monolith_fallback
        pattern -- no manifest yet falls back to plain ascending batching rather
        than failing the whole seed-bronze-batches step."""
        with tempfile.TemporaryDirectory() as tmp:
            context = WarehouseCommandContext(
                bronze_root=StorageLocation(str(Path(tmp) / "bronze")),
                storage_root=StorageLocation("s3://fake-bucket/warehouse"),
                silver_root=StorageLocation(str(Path(tmp) / "silver")),
                snowflake_export_root=None,
                environment_name="test",
                identity="tester@example.com",
                runtime_mode="bronze_capture",
            )

            with (
                patch(
                    "edgar_warehouse.application.warehouse_orchestrator.read_bytes",
                    side_effect=FileNotFoundError("no manifest yet"),
                ),
                patch(
                    "edgar_warehouse.application.warehouse_orchestrator._emit_pipeline_event"
                ) as mock_emit,
            ):
                destination = _write_cik_universe_batches(
                    context=context,
                    rows=[{"cik": 1}, {"cik": 2}, {"cik": 3}],
                    fetch_date=None,
                    sync_run_id="run-no-manifest",
                    batch_size=2,
                    shard_aware=True,
                )

            emitted_events = [call.args[0] for call in mock_emit.call_args_list]
            self.assertIn("shard_manifest_missing_monolith_fallback", emitted_events)

            lines = Path(destination).read_text().splitlines()
            self.assertEqual(
                lines,
                [
                    json.dumps({"cik_list": "1,2"}),
                    json.dumps({"cik_list": "3"}),
                ],
            )

    def test_write_cik_universe_batches_shard_aware_falls_back_when_storage_not_remote(
        self,
    ) -> None:
        """Ticket 12: shard_aware=True is a no-op (plain ascending batching,
        identical to shard_aware=False) when storage_root is local -- no
        shard-manifest.json read is attempted at all."""
        with tempfile.TemporaryDirectory() as tmp:
            context = WarehouseCommandContext(
                bronze_root=StorageLocation(str(Path(tmp) / "bronze")),
                storage_root=StorageLocation(str(Path(tmp) / "warehouse")),
                silver_root=StorageLocation(str(Path(tmp) / "silver")),
                snowflake_export_root=None,
                environment_name="test",
                identity="tester@example.com",
                runtime_mode="bronze_capture",
            )

            with patch(
                "edgar_warehouse.application.warehouse_orchestrator.read_bytes"
            ) as mock_read_bytes:
                destination = _write_cik_universe_batches(
                    context=context,
                    rows=[{"cik": 1}, {"cik": 2}, {"cik": 3}],
                    fetch_date=None,
                    sync_run_id="run-local-storage",
                    batch_size=2,
                    shard_aware=True,
                )

            mock_read_bytes.assert_not_called()

            lines = Path(destination).read_text().splitlines()
            self.assertEqual(
                lines,
                [
                    json.dumps({"cik_list": "1,2"}),
                    json.dumps({"cik_list": "3"}),
                ],
            )


if __name__ == "__main__":
    unittest.main()
