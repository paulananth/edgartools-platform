from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from edgar_warehouse.mdm.publication import HARD_ALERT_AGE_SECONDS, WARNING_AGE_SECONDS
from edgar_warehouse.serving.watermark_aggregator import (
    JsonAlignmentStore,
    MemoryAlignmentStore,
    StageObservation,
    compute_alignment_freshness,
    reconcile_cause_reference,
    rollup_business_date,
)


def _complete(identity: str = "id-1") -> StageObservation:
    return StageObservation(complete=True, identity=identity)


def _incomplete() -> StageObservation:
    return StageObservation(complete=False)


def test_reconcile_writes_aligned_row_when_all_four_stages_complete() -> None:
    store = MemoryAlignmentStore()
    now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    row = reconcile_cause_reference(
        "discovery-manifest:abc",
        business_date="2026-08-29",
        silver=lambda _: _complete(),
        mdm=lambda _: _complete(),
        gold=lambda _: _complete("2026-08-29T15:23:28Z"),
        graph=lambda _: _complete("gen-1"),
        store=store,
        now=now,
    )
    assert row.aligned is True
    assert row.stuck_stage is None
    assert row.gold_run_id == "2026-08-29T15:23:28Z"
    assert row.graph_generation_id == "gen-1"
    assert row.aligned_at == now


def test_reconcile_names_the_stuck_stage_and_is_not_aligned() -> None:
    store = MemoryAlignmentStore()
    row = reconcile_cause_reference(
        "discovery-manifest:abc",
        business_date="2026-08-29",
        silver=lambda _: _complete(),
        mdm=lambda _: _incomplete(),
        gold=lambda _: _complete("g"),
        graph=lambda _: _complete("gen-1"),
        store=store,
    )
    assert row.aligned is False
    assert row.stuck_stage == "mdm"
    assert row.aligned_at is None


def test_watchdog_warning_and_hard_alert_name_stuck_stage() -> None:
    store = MemoryAlignmentStore()
    start = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    reconcile_cause_reference(
        "discovery-manifest:abc",
        business_date="2026-08-29",
        silver=lambda _: _incomplete(),
        mdm=lambda _: _complete(),
        gold=lambda _: _complete("g"),
        graph=lambda _: _complete("gen-1"),
        store=store,
        now=start,
    )
    warning = compute_alignment_freshness(
        store, now=start + timedelta(seconds=WARNING_AGE_SECONDS)
    )
    assert warning.status == "warning"
    assert warning.stuck_stage == "silver"
    assert warning.oldest_unaligned_cause_reference == "discovery-manifest:abc"

    hard = compute_alignment_freshness(
        store, now=start + timedelta(seconds=HARD_ALERT_AGE_SECONDS)
    )
    assert hard.status == "hard_alert"
    assert hard.stuck_stage == "silver"


def test_stuck_cause_repairs_through_the_stage_then_next_pass_aligns() -> None:
    """No aggregator repair API — the stage reader starts returning complete."""

    store = MemoryAlignmentStore()
    start = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    silver_ok = False

    def silver(_cause: str) -> StageObservation:
        return _complete() if silver_ok else _incomplete()

    first = reconcile_cause_reference(
        "discovery-manifest:abc",
        business_date="2026-08-29",
        silver=silver,
        mdm=lambda _: _complete(),
        gold=lambda _: _complete("g"),
        graph=lambda _: _complete("gen-1"),
        store=store,
        now=start,
    )
    assert first.aligned is False
    assert first.stuck_stage == "silver"

    silver_ok = True
    second = reconcile_cause_reference(
        "discovery-manifest:abc",
        business_date="2026-08-29",
        silver=silver,
        mdm=lambda _: _complete(),
        gold=lambda _: _complete("g"),
        graph=lambda _: _complete("gen-1"),
        store=store,
        now=start + timedelta(minutes=20),
    )
    assert second.aligned is True
    assert second.stuck_stage is None
    assert second.first_seen_at == start
    freshness = compute_alignment_freshness(
        store, now=start + timedelta(minutes=20)
    )
    assert freshness.status == "normal"


def test_daily_rollup_is_not_agent_grade_until_every_cause_on_the_date_aligns() -> None:
    store = MemoryAlignmentStore()
    now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    complete = dict(
        silver=lambda _: _complete(),
        mdm=lambda _: _complete(),
        gold=lambda _: _complete("g-1"),
        graph=lambda _: _complete("gen-1"),
    )
    reconcile_cause_reference(
        "cause-a",
        business_date="2026-08-29",
        store=store,
        now=now,
        **complete,
    )
    reconcile_cause_reference(
        "cause-b",
        business_date="2026-08-29",
        silver=lambda _: _incomplete(),
        mdm=lambda _: _complete(),
        gold=lambda _: _complete("g-1"),
        graph=lambda _: _complete("gen-1"),
        store=store,
        now=now,
    )
    blocked = rollup_business_date(store, "2026-08-29")
    assert blocked.agent_grade is False
    assert "silver_completeness_ok is false" in blocked.reasons

    reconcile_cause_reference(
        "cause-b",
        business_date="2026-08-29",
        store=store,
        now=now,
        **complete,
    )
    ready = rollup_business_date(store, "2026-08-29")
    assert ready.agent_grade is True
    assert ready.watermark is not None
    assert ready.watermark.business_date == "2026-08-29"
    assert ready.watermark.gold_run_id == "g-1"
    assert ready.watermark.graph_generation_id == "gen-1"


def test_json_alignment_store_keeps_first_seen_across_process_reload(
    tmp_path: Path,
) -> None:
    path = tmp_path / "alignment.json"
    start = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    first = JsonAlignmentStore(path)
    reconcile_cause_reference(
        "cause-a",
        business_date="2026-08-29",
        silver=lambda _: _incomplete(),
        mdm=lambda _: _complete(),
        gold=lambda _: _complete("g"),
        graph=lambda _: _complete("gen-1"),
        store=first,
        now=start,
    )
    reloaded = JsonAlignmentStore(path)
    row = reloaded.get("cause-a")
    assert row is not None
    assert row.first_seen_at == start
    assert row.aligned is False


def test_cli_reconcile_decision_watermark_is_observe_only() -> None:
    from argparse import Namespace

    from edgar_warehouse.cli import _handle_reconcile_decision_watermark

    args = Namespace(
        business_date="2026-08-29",
        cause_reference=["cause-a"],
        silver_complete=True,
        mdm_complete=True,
        gold_complete=True,
        graph_parity_ok=True,
        gold_run_id="g-1",
        graph_generation_id="gen-1",
        state_file=None,
    )
    assert _handle_reconcile_decision_watermark(args) == 0


def test_decision_contract_sql_uses_mdm_company_entity_universe() -> None:
    from pathlib import Path

    sql = Path("infra/snowflake/sql/decision_contract/01_subject_feature_screen.sql").read_text()
    assert "MDM_COMPANY_ENTITY" in sql
    assert "tracking_status" in sql


def test_bundle_auditor_reads_source_auditor_evidence_not_gold() -> None:
    from pathlib import Path

    sql = Path("infra/snowflake/sql/decision_contract/02_subject_bundle_read_issuer.sql").read_text()
    assert "EDGARTOOLS_SOURCE.SEC_AUDITOR_REPORT_EVIDENCE" in sql
    assert "EDGARTOOLS_GOLD.SEC_AUDITOR_REPORT_EVIDENCE" not in sql
    assert "principal_firm_name" in sql
    assert "pcaob_firm_id" in sql
