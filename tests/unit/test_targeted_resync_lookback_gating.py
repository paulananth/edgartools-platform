"""state-machine-consolidation wayfinder map, Ticket 10: targeted-resync's
cik-scoped accession selection now routes through the same
_configured_parser_accessions gate every bulk loader (daily-incremental,
bootstrap-next, etc.) already uses, instead of unconditionally processing
every accession submissions_orchestrator returns regardless of filing date.
Also covers targeted-resync's own CLI defaults, which deliberately differ
from every bulk loader's: full history (0) unless a family is explicitly
bounded, matching this command's single-company debug purpose.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

from edgar_warehouse import cli
from edgar_warehouse.application import warehouse_orchestrator

from tests.unit.test_targeted_resync_accession_conflict_isolation import (
    _context,
    _FakeDb,
    _submissions_result,
)


def _run_cik_resync(tmp_path: Path, db: _FakeDb, accessions: list[str], **extra_arguments):
    resynced: list[str] = []

    def fake_run_accession_resync(*, accession_number, **_kwargs):
        resynced.append(accession_number)
        return {"raw_writes": [], "rows_written": 1}

    with (
        patch.object(
            warehouse_orchestrator,
            "submissions_orchestrator",
            return_value=_submissions_result(accessions),
        ),
        patch.object(
            warehouse_orchestrator,
            "_run_accession_resync",
            side_effect=fake_run_accession_resync,
        ),
    ):
        warehouse_orchestrator._capture_bronze_raw(
            context=_context(tmp_path),
            db=db,
            bookkeeping=object(),
            command_name="targeted-resync",
            arguments={
                "scope_type": "cik",
                "scope_key": "320193",
                "include_artifacts": True,
                "include_text": False,
                "include_parsers": False,
                **extra_arguments,
            },
            scope={"scope_type": "cik", "scope_key": "320193"},
            now=datetime(2026, 8, 4, 12, tzinfo=UTC),
            sync_run_id="test-run",
        )
    return resynced


def test_cik_scoped_resync_excludes_out_of_window_accession_when_lookback_set(tmp_path) -> None:
    in_window = "0000320193-26-000073"
    out_of_window = "0000320193-20-000010"
    db = _FakeDb({in_window: date(2026, 1, 1), out_of_window: date(2018, 1, 1)})

    resynced = _run_cik_resync(
        tmp_path, db, [in_window, out_of_window], ownership_lookback_years=2
    )

    assert resynced == [in_window]


def test_cik_scoped_resync_full_history_override_resyncs_everything(tmp_path) -> None:
    recent = "0000320193-26-000073"
    old = "0000320193-20-000010"
    db = _FakeDb({recent: date(2026, 1, 1), old: date(2018, 1, 1)})

    resynced = _run_cik_resync(tmp_path, db, [recent, old], ownership_lookback_years=0)

    assert resynced == [recent, old]


def test_cik_scoped_resync_applies_default_lookback_when_arguments_omit_it(tmp_path) -> None:
    """Mirrors what the CLI actually sends when an operator omits every
    lookback flag on the real command: no lookback keys reach `arguments`
    at all only if the caller never threaded them through -- the CLI always
    threads an explicit 0 by default (see the CLI tests below), so this
    proves the underlying gate itself still defaults to 2 years when a
    caller genuinely omits the keys (e.g. a future non-CLI caller), not
    that targeted-resync's own CLI produces this shape."""
    recent = "0000320193-26-000073"
    old = "0000320193-20-000010"
    db = _FakeDb({recent: date(2026, 1, 1), old: date(2018, 1, 1)})

    resynced = _run_cik_resync(tmp_path, db, [recent, old])

    assert resynced == [recent]


def test_targeted_resync_cli_defaults_every_lookback_flag_to_full_history() -> None:
    args = cli.build_parser().parse_args(
        ["targeted-resync", "--scope-type", "cik", "--scope-key", "320193"]
    )

    assert args.ownership_lookback_years == 0
    assert args.item_502_lookback_years is None
    assert args.fundamentals_lookback_years == 0
    assert args.item_202_lookback_years is None
    assert args.proxy_lookback_years is None
    assert args.thirteenf_lookback_years is None
    assert args.adv_lookback_years is None


def test_targeted_resync_cli_accepts_explicit_per_family_override() -> None:
    args = cli.build_parser().parse_args(
        [
            "targeted-resync",
            "--scope-type", "cik",
            "--scope-key", "320193",
            "--adv-lookback-years", "3",
        ]
    )

    assert args.adv_lookback_years == 3
    # Every other family is unaffected -- still full history by default.
    assert args.ownership_lookback_years == 0
    assert args.fundamentals_lookback_years == 0


def test_bootstrap_full_cli_fundamentals_default_unaffected_by_targeted_resync_change() -> None:
    """Regression guard: parameterizing _add_fundamentals_lookback_args's
    default_years for targeted-resync must not change any existing caller's
    behavior -- bootstrap-full (and every other bulk loader) keeps its
    implicit 2-year default (None at the CLI layer, resolved to 2 downstream)."""
    args = cli.build_parser().parse_args(["bootstrap-full"])

    assert args.fundamentals_lookback_years is None
