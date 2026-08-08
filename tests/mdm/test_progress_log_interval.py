"""Progress-log cadence for MDM's per-row resolve loops.

Covers edgar_warehouse.mdm.pipeline._progress_log_interval: scales with
domain size (max(floor, total // 8)) instead of a fixed hardcoded interval,
and the floor is overridable via MDM_PROGRESS_LOG_INTERVAL.
"""
import importlib

import pytest

from edgar_warehouse.mdm import pipeline as pipeline_module


class TestProgressLogInterval:
    def test_small_domain_uses_default_floor(self):
        # 7,911-row person domain: total // 8 (~988) is below the 1000
        # floor, so the floor wins.
        assert pipeline_module._progress_log_interval(7_911) == 1_000

    def test_large_domain_scales_with_total(self):
        # 62,190-row company domain: total // 8 (~7,773) exceeds the floor,
        # so roughly 8 progress lines are emitted for the whole run instead
        # of the old fixed-500 interval's 124.
        assert pipeline_module._progress_log_interval(62_190) == 62_190 // 8

    def test_zero_rows_returns_floor_without_dividing(self):
        assert pipeline_module._progress_log_interval(0) == 1_000

    def test_floor_is_configurable_via_env_var(self, monkeypatch):
        monkeypatch.setenv("MDM_PROGRESS_LOG_INTERVAL", "1500")
        reloaded = importlib.reload(pipeline_module)
        try:
            assert reloaded._progress_log_interval(7_911) == 1_500
            assert reloaded._progress_log_interval(62_190) == 62_190 // 8
        finally:
            monkeypatch.delenv("MDM_PROGRESS_LOG_INTERVAL", raising=False)
            importlib.reload(pipeline_module)
