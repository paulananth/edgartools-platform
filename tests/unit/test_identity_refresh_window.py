"""Tests for the bounded Daily Identity Refresh (release-readiness ticket 45/49):

- compute-identity-refresh-window: force-rechecks the trailing N calendar days,
  unions impacted CIKs, refreshes reference data once, writes a batched cik_list
  JSONL (reusing seed-universe's batch shape) instead of compute-windows' full
  tracked-universe scope.
- pipeline_run_lease: the atomic run-level lease shared by the Daily Identity
  Refresh and the Identity Backstop Sweep.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation


def _context(tmp_path: Path) -> WarehouseCommandContext:
    return WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "warehouse")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="tester@example.com",
        runtime_mode="bronze_capture",
    )


def _fake_index_result(impacted_ciks: list[int]) -> dict:
    return {
        "raw_writes": [],
        "rows_written": 0,
        "rows_skipped": 0,
        "impacted_ciks": impacted_ciks,
        "form_15_ciks": [],
        "status": "succeeded",
        "network_fetches": 1,
    }


def test_company_identity_universe_is_active_operating_or_current_sec_ticker(
    tmp_path,
) -> None:
    """The reusable scheduled-identity boundary includes active operating
    entities and active tracked CIKs in the canonical company_tickers snapshot,
    while excluding other and non-active entities."""
    from edgar_warehouse.silver_store import SilverDatabase

    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        for cik, status in (
            (100, "active"),
            (200, "active"),
            (300, "active"),
            (400, "paused"),
        ):
            db.upsert_company_sync_state({"cik": cik, "tracking_status": status})
        db.merge_company(
            [
                {"cik": 100, "entity_name": "Operating Co", "entity_type": "operating"},
                {"cik": 200, "entity_name": "Ticker Co", "entity_type": "other"},
                {"cik": 300, "entity_name": "Other Entity", "entity_type": "other"},
                {"cik": 400, "entity_name": "Paused Co", "entity_type": "operating"},
            ],
            "seed-run",
        )
        db.replace_company_tickers(
            [
                {"cik": 200, "ticker": "TICK", "exchange": "NYSE"},
                {"cik": 400, "ticker": "PAUS", "exchange": "NASDAQ"},
            ],
            "ticker-run",
            source_name="company_tickers",
        )

        assert db.get_company_identity_ciks("active") == [100, 200]
    finally:
        db.close()


def test_reference_sync_returns_canonical_ticker_snapshot_identity(tmp_path) -> None:
    """Scheduled identity evidence can bind eligibility to the exact captured
    company_tickers object instead of an untracked refetch or mutable count."""
    from edgar_warehouse.silver_store import SilverDatabase

    company_tickers_payload = (
        b'{"0":{"cik_str":200,"ticker":"TICK","title":"Ticker Co"}}'
    )
    exchange_payload = (
        b'{"fields":["cik","name","ticker","exchange"],"data":[]}'
    )

    def fake_download(*, url: str, identity: str) -> bytes:
        del identity
        if url.endswith("/company_tickers.json"):
            return company_tickers_payload
        if url.endswith("/company_tickers_exchange.json"):
            return exchange_payload
        raise AssertionError(f"unexpected reference URL: {url}")

    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        with patch.object(
            warehouse_orchestrator,
            "_download_sec_bytes",
            side_effect=fake_download,
        ):
            result = warehouse_orchestrator._sync_reference_data(
                context=_context(tmp_path),
                db=db,
                sync_run_id="reference-run",
                fetch_date=date(2026, 7, 30),
            )

        assert result["reference_snapshot_identity"] == {
            "source_name": "company_tickers",
            "sha256": (
                "bd52126ec45bde11a58b34c8af00cd2b7a38cc057626baf2b67d13b9482ced1a"
            ),
            "path": str(
                tmp_path
                / "bronze"
                / "reference/sec/company_tickers/2026/07/30/company_tickers.json"
            ),
        }
    finally:
        db.close()


def test_compute_identity_refresh_window_unions_trailing_days_and_force_rechecks(tmp_path) -> None:
    """Every one of the trailing lookback_days is passed force=True (so a late SEC
    daily-index republish is still caught, per ticket 45's second accepted gap), and
    the impacted CIKs across all of them are unioned/deduped."""
    db = MagicMock()
    db.get_tracked_ciks.return_value = [100, 200, 300, 400, 500]
    db.get_company_identity_ciks.return_value = [100, 300, 400, 500]
    context = _context(tmp_path)
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)

    per_date_ciks = {
        date(2026, 7, 24): [100, 200],
        date(2026, 7, 25): [200, 300],  # 200 overlaps -- must dedupe
        date(2026, 7, 26): [],
        date(2026, 7, 27): [400],
        date(2026, 7, 28): [],
        date(2026, 7, 29): [],
        date(2026, 7, 30): [100],
    }
    calls: list[tuple[date, bool]] = []

    def fake_load(*, context, db, target_date, sync_run_id, now, force):
        calls.append((target_date, force))
        return _fake_index_result(per_date_ciks[target_date])

    with (
        patch.object(warehouse_orchestrator, "_load_daily_index_for_date", side_effect=fake_load),
        patch.object(
            warehouse_orchestrator,
            "_sync_reference_data",
            return_value={
                "raw_writes": [],
                "rows_written": 0,
                "rows_skipped": 0,
                "reference_snapshot_identity": {
                    "source_name": "company_tickers",
                    "sha256": "ticker-snapshot-sha",
                    "path": "reference/sec/company_tickers/2026/07/30/company_tickers.json",
                },
            },
        ) as sync_ref,
    ):
        _, metrics = warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="compute-identity-refresh-window",
            arguments={"lookback_days": 7, "batch_size": 500, "run_id": "identity-refresh-1"},
            scope={"lookback_days": 7, "batch_size": 500},
            now=now,
            sync_run_id="identity-refresh-1",
        )

    # All 7 trailing days force-rechecked, none skipped via a cached checkpoint.
    assert len(calls) == 7
    assert all(force is True for _, force in calls)
    assert {d for d, _ in calls} == set(per_date_ciks.keys())

    # Reference data refreshed exactly once per refresh, not once per day.
    sync_ref.assert_called_once()

    # Union across all days, deduped, then intersected with the reusable active
    # operating-or-current-ticker identity universe. CIK 200 is active but not
    # company eligible, so it must not enter the batch artifact.
    assert metrics["input_cik_count"] == 4
    assert metrics["tracked_active_cik_count"] == 5
    assert metrics["company_eligible_universe_cik_count"] == 4
    assert metrics["excluded_cik_count"] == 1
    assert metrics["cik_count"] == 3  # {100, 300, 400}
    assert metrics["selected_cik_digest"] == (
        "daa0d861fa51dec0b8b90f7c7a49536112bd7765a4ee0bb77042c25890a6b0ee"
    )
    assert metrics["reference_snapshot_identity"]["sha256"] == "ticker-snapshot-sha"
    assert metrics["prestage_duration_seconds"] >= 0

    from edgar_warehouse.infrastructure.dataset_path_catalog import (
        default_capture_spec_factory,
    )

    batches_rel = default_capture_spec_factory().cik_universe_batches("identity-refresh-1").relative_path
    written_path = Path(context.bronze_root.join(batches_rel))
    assert written_path.exists(), f"batches JSONL not written to {written_path}"
    lines = [json.loads(line) for line in written_path.read_text().splitlines() if line.strip()]
    all_ciks = sorted(int(c) for line in lines for c in line["cik_list"].split(","))
    assert all_ciks == [100, 300, 400]


def test_compute_identity_refresh_window_fails_closed_when_eligible_universe_empty(
    tmp_path,
) -> None:
    """Scheduled identity must never fall back to all impacted filers when the
    company-eligibility inputs are empty."""
    db = MagicMock()
    db.get_tracked_ciks.return_value = []
    db.get_company_identity_ciks.return_value = []
    context = _context(tmp_path)
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)

    with (
        patch.object(
            warehouse_orchestrator,
            "_load_daily_index_for_date",
            return_value=_fake_index_result([100]),
        ),
        patch.object(
            warehouse_orchestrator,
            "_sync_reference_data",
            return_value={"raw_writes": [], "rows_written": 0, "rows_skipped": 0},
        ),
    ):
        _, metrics = warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="compute-identity-refresh-window",
            arguments={"lookback_days": 2, "batch_size": 500, "run_id": "identity-refresh-2"},
            scope={"lookback_days": 2, "batch_size": 500},
            now=now,
            sync_run_id="identity-refresh-2",
        )

    assert metrics["input_cik_count"] == 1
    assert metrics["company_eligible_universe_cik_count"] == 0
    assert metrics["excluded_cik_count"] == 1
    assert metrics["cik_count"] == 0


def test_compute_identity_refresh_window_backstop_uses_complete_company_universe(
    tmp_path,
) -> None:
    """Backstop mode skips daily-index discovery and writes the complete
    company-eligible active universe through the explicit-CIK batch path."""
    db = MagicMock()
    db.get_tracked_ciks.return_value = [100, 200, 300]
    db.get_company_identity_ciks.return_value = [100, 300]
    context = _context(tmp_path)
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)

    with (
        patch.object(warehouse_orchestrator, "_load_daily_index_for_date") as load_index,
        patch.object(
            warehouse_orchestrator,
            "_sync_reference_data",
            return_value={
                "raw_writes": [],
                "rows_written": 0,
                "rows_skipped": 0,
                "reference_snapshot_identity": {
                    "source_name": "company_tickers",
                    "sha256": "ticker-snapshot-sha",
                    "path": "reference/sec/company_tickers/2026/07/30/company_tickers.json",
                },
            },
        ),
    ):
        _, metrics = warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="compute-identity-refresh-window",
            arguments={
                "mode": "backstop",
                "lookback_days": 7,
                "batch_size": 500,
                "run_id": "identity-backstop-1",
            },
            scope={"mode": "backstop", "lookback_days": 7, "batch_size": 500},
            now=now,
            sync_run_id="identity-backstop-1",
        )

    load_index.assert_not_called()
    assert metrics["refresh_mode"] == "backstop"
    assert metrics["input_cik_count"] == 3
    assert metrics["company_eligible_universe_cik_count"] == 2
    assert metrics["excluded_cik_count"] == 1
    assert metrics["cik_count"] == 2

    from edgar_warehouse.infrastructure.dataset_path_catalog import (
        default_capture_spec_factory,
    )

    batches_rel = default_capture_spec_factory().cik_universe_batches(
        "identity-backstop-1"
    ).relative_path
    lines = [
        json.loads(line)
        for line in Path(context.bronze_root.join(batches_rel)).read_text().splitlines()
        if line.strip()
    ]
    assert lines == [{"cik_list": "100,300"}]


def test_cli_accepts_identity_refresh_window_flags() -> None:
    from edgar_warehouse.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        ["compute-identity-refresh-window", "--lookback-days", "3", "--batch-size", "50", "--run-id", "r"]
    )
    assert args.lookback_days == 3
    assert args.batch_size == 50

    defaults = parser.parse_args(["compute-identity-refresh-window"])
    assert defaults.mode == "daily"
    assert defaults.lookback_days == 7
    assert defaults.batch_size == 500

    backstop = parser.parse_args(
        ["compute-identity-refresh-window", "--mode", "backstop"]
    )
    assert backstop.mode == "backstop"


# ---------------------------------------------------------------------------
# pipeline_run_lease
# ---------------------------------------------------------------------------


def test_pipeline_run_lease_acquire_is_exclusive(tmp_path) -> None:
    from edgar_warehouse.silver_store import SilverDatabase

    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    try:
        assert db.acquire_pipeline_run_lease(
            lease_name="daily_identity_refresh", run_id="run-a", mode="daily", acquired_at=now
        )
        # A second, competing run must not steal the lease.
        assert not db.acquire_pipeline_run_lease(
            lease_name="daily_identity_refresh", run_id="run-b", mode="backstop", acquired_at=now
        )
        held = db.get_pipeline_run_lease("daily_identity_refresh")
        assert held is not None
        assert held["run_id"] == "run-a"
        assert held["status"] == "held"

        # Releasing under the wrong run_id is a no-op.
        db.release_pipeline_run_lease(lease_name="daily_identity_refresh", run_id="run-b", released_at=now)
        assert db.get_pipeline_run_lease("daily_identity_refresh")["status"] == "held"

        # Releasing under the holder's own run_id frees it for the next acquirer.
        db.release_pipeline_run_lease(lease_name="daily_identity_refresh", run_id="run-a", released_at=now)
        assert db.get_pipeline_run_lease("daily_identity_refresh")["status"] == "idle"
        assert db.acquire_pipeline_run_lease(
            lease_name="daily_identity_refresh", run_id="run-b", mode="backstop", acquired_at=now
        )
    finally:
        db.close()


def test_pipeline_run_lease_reclaims_a_stale_hold(tmp_path) -> None:
    """A crashed run that never reached ReleaseLease can't wedge the
    schedule permanently -- a lease held past stale_after_seconds is
    reclaimable by a later acquire attempt (go-live follow-up to ticket 49;
    release-on-failure elsewhere is best-effort precisely because this
    reclaim rule is the actual safety net)."""
    from datetime import timedelta

    from edgar_warehouse.silver_store import SilverDatabase

    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        held_at = datetime(2026, 7, 30, 0, 0, tzinfo=UTC)
        assert db.acquire_pipeline_run_lease(
            lease_name="daily_identity_refresh", run_id="crashed-run", mode="daily", acquired_at=held_at
        )

        # Still within the 20h default stale window -- not reclaimable yet.
        still_fresh = held_at + timedelta(hours=10)
        assert not db.acquire_pipeline_run_lease(
            lease_name="daily_identity_refresh", run_id="new-run", mode="daily", acquired_at=still_fresh
        )

        # Past the 20h window -- reclaimable even though "crashed-run" never released it.
        past_stale = held_at + timedelta(hours=21)
        assert db.acquire_pipeline_run_lease(
            lease_name="daily_identity_refresh", run_id="new-run", mode="daily", acquired_at=past_stale
        )
        held = db.get_pipeline_run_lease("daily_identity_refresh")
        assert held["run_id"] == "new-run"
    finally:
        db.close()


def test_acquire_identity_refresh_lease_command_records_deferred_on_conflict(tmp_path) -> None:
    """The orchestrator command surfaces a deferred disposition (not an exception)
    when the lease is already held -- ticket 45's 'deferred, not an invisible skip'."""
    from edgar_warehouse.silver_store import SilverDatabase

    context = _context(tmp_path)
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        db.acquire_pipeline_run_lease(
            lease_name="daily_identity_refresh", run_id="already-running", mode="daily", acquired_at=now
        )

        _, metrics = warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="acquire-identity-refresh-lease",
            arguments={"mode": "backstop", "run_id": "backstop-run"},
            scope={"mode": "backstop"},
            now=now,
            sync_run_id="backstop-run",
        )
        assert metrics["lease_acquired"] is False

        # The S3 side-channel -- not the metric -- is the source of truth the
        # state machine actually reads (ecs:runTask.sync can't surface the
        # metric to a Choice state).
        from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver

        lease_result_rel = default_path_resolver().identity_refresh_lease_path("backstop-run")
        written_path = Path(context.bronze_root.join(lease_result_rel))
        assert written_path.exists()
        payload = json.loads(written_path.read_text())
        assert payload["lease_acquired"] is False
        assert payload["backstop_overdue"] is True
        assert payload["held_by_run_id"] == "already-running"
    finally:
        db.close()


def test_acquire_identity_refresh_lease_command_writes_success_to_s3(tmp_path) -> None:
    from edgar_warehouse.silver_store import SilverDatabase
    from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver

    context = _context(tmp_path)
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        _, metrics = warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="acquire-identity-refresh-lease",
            arguments={"mode": "daily", "run_id": "daily-run"},
            scope={"mode": "daily"},
            now=now,
            sync_run_id="daily-run",
        )
        assert metrics["lease_acquired"] is True

        lease_result_rel = default_path_resolver().identity_refresh_lease_path("daily-run")
        written_path = Path(context.bronze_root.join(lease_result_rel))
        payload = json.loads(written_path.read_text())
        assert payload == {
            "lease_acquired": True,
            "mode": "daily",
            "backstop_overdue": False,
            "held_by_run_id": "daily-run",
        }
    finally:
        db.close()


def test_pipeline_run_lease_backstop_overdue_persists_until_a_backstop_run_releases(tmp_path) -> None:
    """A deferred 'backstop' acquire marks backstop_overdue; only a subsequent
    'backstop'-mode release clears it -- an intervening 'daily' release must not
    silently drop the overdue backstop (release-readiness ticket 45's 'prioritize
    the next available slot' requirement)."""
    from edgar_warehouse.silver_store import SilverDatabase

    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    try:
        # Sunday's backstop can't run -- Saturday's daily run is still holding the lease.
        assert db.acquire_pipeline_run_lease(
            lease_name="daily_identity_refresh", run_id="sat-daily", mode="daily", acquired_at=now
        )
        assert not db.acquire_pipeline_run_lease(
            lease_name="daily_identity_refresh", run_id="sun-backstop", mode="backstop", acquired_at=now
        )
        db.mark_pipeline_run_lease_backstop_overdue(lease_name="daily_identity_refresh")
        assert db.get_pipeline_run_lease("daily_identity_refresh")["backstop_overdue"] is True

        # Saturday's run finishes and releases under mode='daily' -- the overdue flag
        # it had nothing to do with must survive this release.
        db.release_pipeline_run_lease(lease_name="daily_identity_refresh", run_id="sat-daily", released_at=now)
        assert db.get_pipeline_run_lease("daily_identity_refresh")["backstop_overdue"] is True

        # The next run acquires in 'backstop' mode (mirroring what the orchestrator's
        # effective-mode resolution would compute once overdue is set).
        assert db.acquire_pipeline_run_lease(
            lease_name="daily_identity_refresh", run_id="mon-run", mode="backstop", acquired_at=now
        )
        assert db.get_pipeline_run_lease("daily_identity_refresh")["backstop_overdue"] is True

        # Only this 'backstop'-mode release clears the flag.
        db.release_pipeline_run_lease(lease_name="daily_identity_refresh", run_id="mon-run", released_at=now)
        assert db.get_pipeline_run_lease("daily_identity_refresh")["backstop_overdue"] is False
    finally:
        db.close()


def test_acquire_identity_refresh_lease_resolves_overdue_backstop_over_requested_daily_mode(tmp_path) -> None:
    """Ticket 45's 'prioritize the next available slot': once backstop_overdue is set,
    an acquire attempt that *requests* 'daily' must actually run as 'backstop' -- the
    persisted flag overrides the caller's own --mode, and lease_result.json (the state
    machine's source of truth) carries the resolved value, not the raw request."""
    from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver
    from edgar_warehouse.silver_store import SilverDatabase

    context = _context(tmp_path)
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        db.acquire_pipeline_run_lease(
            lease_name="daily_identity_refresh", run_id="prior-holder", mode="daily", acquired_at=now
        )
        # A backstop attempt is deferred and marks the flag overdue.
        warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="acquire-identity-refresh-lease",
            arguments={"mode": "backstop", "run_id": "sun-backstop"},
            scope={"mode": "backstop"},
            now=now,
            sync_run_id="sun-backstop",
        )
        db.release_pipeline_run_lease(lease_name="daily_identity_refresh", run_id="prior-holder", released_at=now)

        # Monday's trigger requests 'daily' as usual -- but the overdue flag must win.
        _, metrics = warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="acquire-identity-refresh-lease",
            arguments={"mode": "daily", "run_id": "mon-run"},
            scope={"mode": "daily"},
            now=now,
            sync_run_id="mon-run",
        )
        assert metrics["lease_acquired"] is True
        assert metrics["effective_refresh_mode"] == "backstop"

        lease_result_rel = default_path_resolver().identity_refresh_lease_path("mon-run")
        payload = json.loads(Path(context.bronze_root.join(lease_result_rel)).read_text())
        assert payload["mode"] == "backstop"
    finally:
        db.close()


def test_acquire_identity_refresh_lease_resolves_overdue_backstop_across_two_consecutive_deferrals(
    tmp_path,
) -> None:
    """Ticket 45's carry-forward must survive more than one missed slot: if
    Monday's backstop-resolved attempt is *itself* deferred (something is
    still holding the lease), Tuesday's trigger must still resolve to
    'backstop' -- not fall back to 'daily' just because one retry already
    happened. Only a run that actually acquires and releases in 'backstop'
    mode clears the flag (code-review finding: the original coverage only
    exercised a single defer-then-succeed cycle)."""
    from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver
    from edgar_warehouse.silver_store import SilverDatabase

    context = _context(tmp_path)
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        db.acquire_pipeline_run_lease(
            lease_name="daily_identity_refresh", run_id="sat-daily", mode="daily", acquired_at=now
        )
        # Sunday's backstop is deferred -- marks overdue.
        warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="acquire-identity-refresh-lease",
            arguments={"mode": "backstop", "run_id": "sun-backstop"},
            scope={"mode": "backstop"},
            now=now,
            sync_run_id="sun-backstop",
        )
        # Saturday's holder is still running -- Monday's trigger (requesting
        # 'daily') resolves to 'backstop' per the overdue flag, but is ALSO
        # deferred, since the lease is still held.
        _, mon_metrics = warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="acquire-identity-refresh-lease",
            arguments={"mode": "daily", "run_id": "mon-run"},
            scope={"mode": "daily"},
            now=now,
            sync_run_id="mon-run",
        )
        assert mon_metrics["lease_acquired"] is False
        assert mon_metrics["effective_refresh_mode"] == "backstop"
        assert db.get_pipeline_run_lease("daily_identity_refresh")["backstop_overdue"] is True

        db.release_pipeline_run_lease(lease_name="daily_identity_refresh", run_id="sat-daily", released_at=now)

        # Tuesday's trigger (requesting 'daily' again) must STILL resolve to
        # 'backstop' -- one prior deferral does not exhaust the carry-forward.
        _, tue_metrics = warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="acquire-identity-refresh-lease",
            arguments={"mode": "daily", "run_id": "tue-run"},
            scope={"mode": "daily"},
            now=now,
            sync_run_id="tue-run",
        )
        assert tue_metrics["lease_acquired"] is True
        assert tue_metrics["effective_refresh_mode"] == "backstop"

        lease_result_rel = default_path_resolver().identity_refresh_lease_path("tue-run")
        payload = json.loads(Path(context.bronze_root.join(lease_result_rel)).read_text())
        assert payload["mode"] == "backstop"

        # Only Tuesday's successful 'backstop'-mode release finally clears it.
        db.release_pipeline_run_lease(lease_name="daily_identity_refresh", run_id="tue-run", released_at=now)
        assert db.get_pipeline_run_lease("daily_identity_refresh")["backstop_overdue"] is False
    finally:
        db.close()


def test_acquire_identity_refresh_lease_command_rejects_unknown_mode(tmp_path) -> None:
    from edgar_warehouse.application.errors import WarehouseRuntimeError

    context = _context(tmp_path)
    db = MagicMock()
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    try:
        warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="acquire-identity-refresh-lease",
            arguments={"mode": "weekly", "run_id": "r"},
            scope={"mode": "weekly"},
            now=now,
            sync_run_id="r",
        )
        raised = False
    except WarehouseRuntimeError:
        raised = True
    assert raised, "expected an invalid --mode to raise WarehouseRuntimeError"
