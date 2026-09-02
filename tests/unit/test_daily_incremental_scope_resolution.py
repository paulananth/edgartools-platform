"""_resolve_scope's daily-incremental date-range logic (bronze-capture-oom
Ticket 03, second finding, 2026-09-02).

Live prod incident: once BookkeepingStore.commit() started making
checkpoints actually durable (Ticket 03's own fix), daily_incremental hit
a previously-unreachable case -- a run starting again before SEC's next
daily index is published, right after a prior run had already caught up to
everything currently available. next_business_day(last_success) then lands
one business day *after* the latest eligible business date, and the old
code raised WarehouseRuntimeError("start_date must be on or before
end_date") instead of recognizing this as the normal "nothing new yet"
steady state.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.application.warehouse_orchestrator import _resolve_scope


def _resolve(*, last_success: str | None, now: datetime, arguments: dict | None = None) -> dict:
    fake_bookkeeping = MagicMock()
    fake_bookkeeping.get_last_successful_checkpoint_date.return_value = last_success
    with patch(
        "edgar_warehouse.application.warehouse_orchestrator._bookkeeping_store",
        return_value=fake_bookkeeping,
    ):
        return _resolve_scope(
            command_name="daily-incremental",
            arguments=arguments or {},
            now=now,
            silver_root=MagicMock(),
        )


class TestDailyIncrementalScopeResolution:
    def test_no_prior_success_falls_back_to_end_date(self) -> None:
        # Wednesday 2026-09-02 06:10 ET, well past 09-01's 06:00 ET publish
        # cutover -> latest_eligible_business_date resolves to 2026-09-01.
        now = datetime(2026, 9, 2, 10, 10, 0, tzinfo=UTC)
        scope = _resolve(last_success=None, now=now)
        assert scope["business_date_start"] == "2026-09-01"
        assert scope["business_date_end"] == "2026-09-01"

    def test_last_success_within_range_advances_normally(self) -> None:
        now = datetime(2026, 9, 2, 10, 10, 0, tzinfo=UTC)
        scope = _resolve(last_success="2026-08-27", now=now)
        assert scope["business_date_start"] == "2026-08-28"
        assert scope["business_date_end"] == "2026-09-01"

    def test_caught_up_clamps_instead_of_raising(self) -> None:
        """The exact live-reproduced bug: last_success is the most recent
        date SEC has published, so next_business_day(last_success) lands
        one business day past what's currently eligible. Must clamp, not
        raise."""
        now = datetime(2026, 9, 2, 10, 10, 0, tzinfo=UTC)
        scope = _resolve(last_success="2026-09-01", now=now)
        assert scope["business_date_start"] == "2026-09-01"
        assert scope["business_date_end"] == "2026-09-01"

    def test_explicit_start_after_end_still_raises(self) -> None:
        """An operator-supplied invalid range is a real error, not the
        auto-derived caught-up case -- must still fail loud."""
        now = datetime(2026, 9, 2, 10, 10, 0, tzinfo=UTC)
        try:
            _resolve(
                last_success=None,
                now=now,
                arguments={"start_date": "2026-09-05", "end_date": "2026-09-01"},
            )
            raise AssertionError("expected WarehouseRuntimeError")
        except WarehouseRuntimeError as exc:
            assert "start_date must be on or before end_date" in str(exc)

    def test_explicit_stale_end_date_still_raises_even_with_a_real_last_success(self) -> None:
        """Standards-review finding, 2026-09-02: an auto-derived start_date
        (from a real last_success) racing against an *explicitly passed*
        --end-date that predates it must not silently clamp to a
        misleadingly narrow single-day window -- the caller asked for a
        specific end_date, so a mismatch there is a real error, same as
        the fully-explicit case above. Only a fully-automatic invocation
        (neither bound passed) may self-clamp."""
        now = datetime(2026, 9, 2, 10, 10, 0, tzinfo=UTC)
        try:
            _resolve(
                last_success="2026-09-01",
                now=now,
                arguments={"end_date": "2026-08-15"},
            )
            raise AssertionError("expected WarehouseRuntimeError")
        except WarehouseRuntimeError as exc:
            assert "start_date must be on or before end_date" in str(exc)
