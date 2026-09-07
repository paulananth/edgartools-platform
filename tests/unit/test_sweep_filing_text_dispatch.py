"""release-readiness Ticket 101: confirms sweep-filing-text is actually
wired into the shared warehouse dispatch (_resolve_scope, _capture_bronze_raw)
the same way backfill-mdm-entity-ids/backfill-silver-landing-historical are
-- a new command name that's missing from _resolve_scope's ladder raises
WarehouseRuntimeError before it ever reaches its own logic, so this is a
real regression seam, not a formality.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from edgar_warehouse.application.warehouse_orchestrator import (
    _capture_bronze_raw,
    _resolve_scope,
)


class TestSweepFilingTextDispatch:
    def test_resolve_scope_returns_empty_scope(self) -> None:
        scope = _resolve_scope(
            command_name="sweep-filing-text",
            arguments={},
            now=datetime.now(UTC),
            silver_root=None,
        )

        assert scope == {}

    def test_capture_bronze_raw_dispatches_to_the_sweep_module(self) -> None:
        fake_result = ([{"path": "s3://fake"}], {"rows_inserted": 3})
        with patch(
            "edgar_warehouse.filing_text_sweep.run_filing_text_sweep",
            return_value=fake_result,
        ) as sweep_mock:
            raw_writes, metrics = _capture_bronze_raw(
                context=MagicMock(),
                db=MagicMock(),
                bookkeeping=MagicMock(),
                command_name="sweep-filing-text",
                arguments={"limit": 50},
                scope={},
                now=datetime.now(UTC),
                sync_run_id="run-1",
            )

        assert (raw_writes, metrics) == fake_result
        sweep_mock.assert_called_once()
        assert sweep_mock.call_args.kwargs["limit"] == 50
        assert sweep_mock.call_args.kwargs["sync_run_id"] == "run-1"
