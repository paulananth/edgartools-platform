from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import mssql, mysql, postgresql

from edgar_warehouse.bookkeeping.clean import storage


@pytest.mark.parametrize("dialect", [postgresql.dialect(), mysql.dialect(), mssql.dialect()])
def test_observation_reads_one_statement_and_excludes_private_evidence(monkeypatch, dialect):
    captured = []
    row = {"run_id": "00000000-0000-0000-0000-000000000001",
           "submission": {"kind": "source", "name": "example", "target": "prepare",
                          "inputs": {"uri": "private-artifact"}},
           "state": "running", "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
           "completed_at": None, "compacted_at": None, "expected_count": 2**53 + 1,
           "checks": {"delivery": True, "private": {"url": "secret-address"}},
           "pending_deliveries": 2, "step": "read", "unit_state": "reported",
           "units": 2**53 + 1, "attempts": 3, "errors": 1}
    def rows(conn, statement):
        captured.append(str(statement.compile(dialect=dialect)))
        return [row]
    monkeypatch.setattr(storage, "rows", rows)
    engine = SimpleNamespace(dialect=dialect, connect=lambda: nullcontext(object()))
    observed = storage.observation(engine, row["run_id"])
    assert len(captured) == 1
    assert "LEFT OUTER JOIN" in captured[0]
    assert observed["expected_units"] == 9007199254740993
    assert observed["steps"] == [{"step": "read", "unit_state": "reported",
                                  "units": 9007199254740993, "attempts": 3, "errors": 1}]
    assert observed["checks"] == {"delivery": True}
    assert "private-artifact" not in str(observed)
    assert "secret-address" not in str(observed)
    if dialect.name == "mssql":
        assert "count_big" in captured[0]


def test_unknown_run_is_an_error_instead_of_an_empty_success(monkeypatch):
    monkeypatch.setattr(storage, "rows", lambda *args: [])
    engine = SimpleNamespace(dialect=postgresql.dialect(), connect=lambda: nullcontext(object()))
    with pytest.raises(ValueError, match="Unknown"):
        storage.observation(engine, "00000000-0000-0000-0000-000000000001")
