"""Unit coverage for `mdm check-manages-fund-duplicates`'s CLI handler
(manages-fund-duplicate-rows map, Ticket 03).

The check logic itself (`check_manages_fund_duplicates`) needs a real
Postgres role/JSONB grouping and is covered by
`tests/integration/test_manages_fund_duplicate_monitor_postgres.py`. This
file only exercises the handler's own responsibilities: turning a
`DuplicateCheckResult` into the right structured log events and the right
exit code -- a fast, mock-friendly seam that doesn't need Docker. Mirrors
`test_check_fence_cli.py`'s own structure.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from edgar_warehouse.mdm import cli as mdm_cli
from edgar_warehouse.mdm.manages_fund_duplicate_monitor import (
    DuplicateCheckResult,
    DuplicateGroup,
)


def argparse_namespace_stub():
    class _Args:
        pass

    return _Args()


def test_clean_result_exits_zero(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(mdm_cli, "emit_mdm_event", lambda *a, **k: None)
    monkeypatch.setattr("edgar_warehouse.mdm.database.get_engine", lambda: object())
    result = DuplicateCheckResult(new_duplicate_groups=())
    monkeypatch.setattr(
        "edgar_warehouse.mdm.manages_fund_duplicate_monitor.check_manages_fund_duplicates",
        lambda engine: result,
    )

    exit_code = mdm_cli._handle_check_manages_fund_duplicates(argparse_namespace_stub())

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["is_clean"] is True
    assert payload["new_duplicate_groups"] == []


def test_new_duplicate_group_exits_nonzero_and_logs_each_finding(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        mdm_cli, "emit_mdm_event", lambda event, **payload: events.append((event, payload))
    )
    monkeypatch.setattr("edgar_warehouse.mdm.database.get_engine", lambda: object())
    latest_created_at = datetime(2026, 9, 12, 0, 0, tzinfo=timezone.utc)
    result = DuplicateCheckResult(
        new_duplicate_groups=(
            DuplicateGroup(
                relationship_id="11111111-1111-1111-1111-111111111111",
                active_count=2,
                latest_created_at=latest_created_at,
            ),
        )
    )
    monkeypatch.setattr(
        "edgar_warehouse.mdm.manages_fund_duplicate_monitor.check_manages_fund_duplicates",
        lambda engine: result,
    )

    exit_code = mdm_cli._handle_check_manages_fund_duplicates(argparse_namespace_stub())

    assert exit_code == 1
    group_events = [
        e for e in events if e[0] == "mdm_manages_fund_new_duplicate_group_detected"
    ]
    assert group_events == [
        (
            "mdm_manages_fund_new_duplicate_group_detected",
            {
                "relationship_id": "11111111-1111-1111-1111-111111111111",
                "active_count": 2,
                "latest_created_at": latest_created_at.isoformat(),
            },
        )
    ]
    summary_events = [
        e for e in events if e[0] == "mdm_manages_fund_duplicate_check_result"
    ]
    assert summary_events == [
        ("mdm_manages_fund_duplicate_check_result", {"new_duplicate_group_count": 1})
    ]
    payload = json.loads(capsys.readouterr().out)
    assert payload["is_clean"] is False
    assert payload["new_duplicate_groups"] == [
        {
            "relationship_id": "11111111-1111-1111-1111-111111111111",
            "active_count": 2,
            "latest_created_at": latest_created_at.isoformat(),
        }
    ]
