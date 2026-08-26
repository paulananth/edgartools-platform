"""Unit coverage for `mdm check-fence`'s CLI handler (Ticket 44).

The check logic itself (`check_ledger_fence`) needs a real Postgres role
graph and is covered by `tests/integration/test_fence_monitor_postgres.py`.
This file only exercises the handler's own responsibilities: turning a
`FenceCheckResult` into the right structured log events and the right exit
code -- a fast, SQLite/mock-friendly seam that doesn't need Docker.
"""

from __future__ import annotations

import json

import pytest

from edgar_warehouse.mdm import cli as mdm_cli
from edgar_warehouse.mdm.fence_monitor import FenceCheckResult, FenceLeak, OperationalAccessGap


def argparse_namespace_stub():
    class _Args:
        pass

    return _Args()


def test_clean_result_exits_zero(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(mdm_cli, "emit_mdm_event", lambda *a, **k: None)
    monkeypatch.setattr("edgar_warehouse.mdm.database.get_engine", lambda: object())
    result = FenceCheckResult(
        fenced_tables=("source_fetch_decision",),
        owner_roles=("edgartools_acquisition_owner",),
        leaks=(),
        access_gaps=(),
    )
    monkeypatch.setattr(
        "edgar_warehouse.mdm.fence_monitor.check_ledger_fence", lambda engine: result
    )

    exit_code = mdm_cli._handle_check_fence(argparse_namespace_stub())

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["is_clean"] is True
    assert payload["leaks"] == []
    assert payload["access_gaps"] == []


def test_leak_result_exits_nonzero_and_logs_each_finding(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        mdm_cli, "emit_mdm_event", lambda event, **payload: events.append((event, payload))
    )
    monkeypatch.setattr("edgar_warehouse.mdm.database.get_engine", lambda: object())
    result = FenceCheckResult(
        fenced_tables=("source_fetch_decision",),
        owner_roles=("edgartools_acquisition_owner",),
        leaks=(
            FenceLeak(role="snowflake_write", table="source_fetch_decision", privilege="SELECT"),
        ),
        access_gaps=(),
    )
    monkeypatch.setattr(
        "edgar_warehouse.mdm.fence_monitor.check_ledger_fence", lambda engine: result
    )

    exit_code = mdm_cli._handle_check_fence(argparse_namespace_stub())

    assert exit_code == 1
    leak_events = [e for e in events if e[0] == "mdm_fence_leak_detected"]
    assert leak_events == [
        (
            "mdm_fence_leak_detected",
            {"role": "snowflake_write", "table": "source_fetch_decision", "privilege": "SELECT"},
        )
    ]
    summary_events = [e for e in events if e[0] == "mdm_fence_check_result"]
    assert summary_events == [
        (
            "mdm_fence_check_result",
            {
                "fenced_table_count": 1,
                "owner_role_count": 1,
                "leak_count": 1,
                "access_gap_count": 0,
            },
        )
    ]
    payload = json.loads(capsys.readouterr().out)
    assert payload["is_clean"] is False


def test_access_gap_result_exits_nonzero_and_logs(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        mdm_cli, "emit_mdm_event", lambda event, **payload: events.append((event, payload))
    )
    monkeypatch.setattr("edgar_warehouse.mdm.database.get_engine", lambda: object())
    result = FenceCheckResult(
        fenced_tables=("source_fetch_decision",),
        owner_roles=("edgartools_acquisition_owner",),
        leaks=(),
        access_gaps=(
            OperationalAccessGap(
                table="source_fetch_decision", role="edgartools_acquisition_owner"
            ),
        ),
    )
    monkeypatch.setattr(
        "edgar_warehouse.mdm.fence_monitor.check_ledger_fence", lambda engine: result
    )

    exit_code = mdm_cli._handle_check_fence(argparse_namespace_stub())

    assert exit_code == 1
    gap_events = [e for e in events if e[0] == "mdm_fence_access_gap_detected"]
    assert gap_events == [
        (
            "mdm_fence_access_gap_detected",
            {"table": "source_fetch_decision", "role": "edgartools_acquisition_owner"},
        )
    ]
