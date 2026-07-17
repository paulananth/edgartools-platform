"""Tests for dual-mode capture contract (ticket 01)."""

from __future__ import annotations

import unittest

from edgar_warehouse.infrastructure.capture_mode import (
    CAPTURE_MODE_NORMAL,
    CAPTURE_MODE_STRICT_RELEASE,
    non_edgartools_source_requires_bronze,
    resolve_capture_mode,
    should_persist_bronze,
)


class CaptureModeTests(unittest.TestCase):
    def test_default_is_normal(self) -> None:
        self.assertEqual(resolve_capture_mode(environ={}), CAPTURE_MODE_NORMAL)

    def test_explicit_and_env_modes(self) -> None:
        self.assertEqual(
            resolve_capture_mode(explicit="strict_release", environ={}),
            CAPTURE_MODE_STRICT_RELEASE,
        )
        self.assertEqual(
            resolve_capture_mode(environ={"WAREHOUSE_CAPTURE_MODE": "strict_release"}),
            CAPTURE_MODE_STRICT_RELEASE,
        )
        self.assertEqual(
            resolve_capture_mode(environ={"WAREHOUSE_RELEASE_MODE": "true"}),
            CAPTURE_MODE_STRICT_RELEASE,
        )

    def test_invalid_mode_raises(self) -> None:
        with self.assertRaises(ValueError):
            resolve_capture_mode(explicit="turbo")

    def test_strict_release_always_persists_bronze(self) -> None:
        self.assertTrue(
            should_persist_bronze(
                capture_mode=CAPTURE_MODE_STRICT_RELEASE,
                source_is_edgartools=True,
                environ={},
            )
        )

    def test_normal_persists_only_when_requested(self) -> None:
        self.assertFalse(
            should_persist_bronze(
                capture_mode=CAPTURE_MODE_NORMAL,
                source_is_edgartools=True,
                environ={},
            )
        )
        self.assertTrue(
            should_persist_bronze(
                capture_mode=CAPTURE_MODE_NORMAL,
                explicit_persist=True,
                source_is_edgartools=True,
                environ={},
            )
        )
        self.assertTrue(
            should_persist_bronze(
                capture_mode=CAPTURE_MODE_NORMAL,
                source_is_edgartools=True,
                environ={"WAREHOUSE_PERSIST_BRONZE": "1"},
            )
        )

    def test_non_edgartools_always_requires_bronze(self) -> None:
        self.assertTrue(non_edgartools_source_requires_bronze())
        self.assertTrue(
            should_persist_bronze(
                capture_mode=CAPTURE_MODE_NORMAL,
                source_is_edgartools=False,
                environ={},
            )
        )


class CaptureNetworkMetricsTests(unittest.TestCase):
    def test_records_network_vs_silver_skip(self) -> None:
        from edgar_warehouse.infrastructure.capture_metrics import CaptureNetworkMetrics

        metrics = CaptureNetworkMetrics()
        metrics.record_artifact_result({"network_fetches": 0})
        metrics.record_artifact_result({"network_fetches": 2})
        metrics.record_artifact_result({"network_fetches": 0})
        out = metrics.as_dict()
        self.assertEqual(out["network_fetches"], 2)
        self.assertEqual(out["silver_skips"], 2)
        self.assertEqual(out["accessions_with_network"], 1)
        self.assertEqual(out["accessions_silver_skip"], 2)

    def test_merge_into_orchestrator_metrics(self) -> None:
        from edgar_warehouse.infrastructure.capture_metrics import CaptureNetworkMetrics

        bag: dict = {"rows_inserted": 3}
        m = CaptureNetworkMetrics()
        m.record_artifact_result({"network_fetches": 1})
        m.merge_into(bag)
        self.assertEqual(bag["network_fetches"], 1)
        self.assertEqual(bag["silver_skips"], 0)
        self.assertEqual(bag["rows_inserted"], 3)


if __name__ == "__main__":
    unittest.main()
