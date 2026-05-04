"""Tests for edgar_warehouse/mdm/universe.py — MDM tracked-universe primitives."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from edgar_warehouse.mdm.database import Base
from edgar_warehouse.mdm.universe import (
    bulk_upsert_universe,
    get_tracked_ciks,
    update_tracking_status,
)


@pytest.fixture
def engine():
    """In-memory SQLite engine with full MDM schema via ORM metadata."""
    eng = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    return eng


def test_bulk_upsert_creates_new_companies(engine):
    rows = [
        {"cik": 1234, "ticker": "AAPL", "exchange": "NASDAQ"},
        {"cik": 5678, "ticker": "MSFT", "exchange": "NASDAQ"},
    ]
    count = bulk_upsert_universe(engine, rows)
    assert count == 2
    ciks = get_tracked_ciks(engine, status_filter="active")
    assert sorted(ciks) == [1234, 5678]


def test_bulk_upsert_is_idempotent(engine):
    rows = [{"cik": 1234, "ticker": "AAPL", "exchange": "NASDAQ"}]
    count1 = bulk_upsert_universe(engine, rows)
    count2 = bulk_upsert_universe(engine, rows)
    assert count1 == 1
    assert count2 == 1
    assert get_tracked_ciks(engine, "active") == [1234]


def test_bulk_upsert_does_not_overwrite_canonical_name(engine):
    rows = [{"cik": 1234, "ticker": "AAPL", "exchange": "NASDAQ"}]
    bulk_upsert_universe(engine, rows)
    with engine.begin() as conn:
        conn.execute(text("UPDATE mdm_company SET canonical_name = 'Apple Inc' WHERE cik = 1234"))
    bulk_upsert_universe(engine, rows)
    with engine.connect() as conn:
        name = conn.execute(text("SELECT canonical_name FROM mdm_company WHERE cik = 1234")).scalar()
    assert name == "Apple Inc"


def test_get_tracked_ciks_filters_by_status(engine):
    rows = [
        {"cik": 1234, "ticker": "AAPL", "exchange": "NASDAQ"},
        {"cik": 5678, "ticker": "MSFT", "exchange": "NASDAQ"},
    ]
    bulk_upsert_universe(engine, rows)
    update_tracking_status(engine, 5678, "paused")
    assert get_tracked_ciks(engine, "active") == [1234]
    assert get_tracked_ciks(engine, "paused") == [5678]


def test_get_tracked_ciks_returns_empty_for_unknown_status(engine):
    rows = [{"cik": 1234, "ticker": "AAPL", "exchange": "NASDAQ"}]
    bulk_upsert_universe(engine, rows)
    assert get_tracked_ciks(engine, "bootstrap_pending") == []


def test_update_tracking_status_returns_false_for_missing_cik(engine):
    result = update_tracking_status(engine, 99999, "active")
    assert result is False


def test_update_tracking_status_returns_true_when_updated(engine):
    rows = [{"cik": 1234, "ticker": "AAPL", "exchange": "NASDAQ"}]
    bulk_upsert_universe(engine, rows)
    result = update_tracking_status(engine, 1234, "paused")
    assert result is True
    assert get_tracked_ciks(engine, "paused") == [1234]
    assert get_tracked_ciks(engine, "active") == []


def test_bulk_upsert_respects_default_status(engine):
    rows = [{"cik": 1234, "ticker": "AAPL", "exchange": "NASDAQ"}]
    bulk_upsert_universe(engine, rows, default_status="bootstrap_pending")
    assert get_tracked_ciks(engine, "bootstrap_pending") == [1234]
    assert get_tracked_ciks(engine, "active") == []


def test_bulk_upsert_does_not_overwrite_existing_tracking_status(engine):
    """Re-seeding should not reset tracking_status already set by resolver."""
    rows = [{"cik": 1234, "ticker": "AAPL", "exchange": "NASDAQ"}]
    bulk_upsert_universe(engine, rows)
    update_tracking_status(engine, 1234, "paused")
    bulk_upsert_universe(engine, rows)
    assert get_tracked_ciks(engine, "paused") == [1234]
    assert get_tracked_ciks(engine, "active") == []


def test_bulk_upsert_handles_missing_ticker_gracefully(engine):
    rows = [{"cik": 9999, "ticker": "", "exchange": None}]
    count = bulk_upsert_universe(engine, rows)
    assert count == 1
    assert get_tracked_ciks(engine, "active") == [9999]


# ---------------------------------------------------------------------------
# Migration 003 tests
# ---------------------------------------------------------------------------

def test_migration_003_sql_applies_to_sqlite(engine):
    """003_tracking_status_index.sql must be valid SQL that SQLite can run."""
    from pathlib import Path
    sql_path = (
        Path(__file__).parent.parent.parent
        / "edgar_warehouse" / "mdm" / "migrations" / "003_tracking_status_index.sql"
    )
    assert sql_path.exists(), "Migration file 003_tracking_status_index.sql must exist"
    sql = sql_path.read_text(encoding="utf-8").strip()
    assert sql, "Migration file must not be empty"
    with engine.begin() as conn:
        conn.execute(text(sql))


def test_migration_003_is_idempotent(engine):
    """Applying migration 003 twice must not raise."""
    from pathlib import Path
    sql_path = (
        Path(__file__).parent.parent.parent
        / "edgar_warehouse" / "mdm" / "migrations" / "003_tracking_status_index.sql"
    )
    sql = sql_path.read_text(encoding="utf-8").strip()
    with engine.begin() as conn:
        conn.execute(text(sql))
    with engine.begin() as conn:
        conn.execute(text(sql))


def test_migrate_runtime_includes_003_for_postgres_path():
    """migrate() must call _apply_sql_file for 003 on non-MSSQL dialects."""
    import inspect
    from edgar_warehouse.mdm.migrations import runtime as rt
    source = inspect.getsource(rt.migrate)
    assert "003_tracking_status_index.sql" in source, (
        "migrate() must call _apply_sql_file(engine, '003_tracking_status_index.sql')"
    )


# ---------------------------------------------------------------------------
# CLI seed-universe handler tests
# ---------------------------------------------------------------------------

def test_seed_universe_cli_handler(engine, monkeypatch):
    """_handle_seed_universe must download SEC JSON, parse it, and upsert into MDM."""
    import argparse
    import edgar_warehouse.mdm.cli as mdm_cli

    captured: dict = {}

    def fake_download(url: str) -> bytes:
        captured["url"] = url
        return b'{"0":{"cik_str":1234,"ticker":"AAPL","exchange":"NASDAQ"},"1":{"cik_str":5678,"ticker":"MSFT","exchange":"NASDAQ"}}'

    monkeypatch.setattr(mdm_cli, "_download_sec_bytes", fake_download)
    monkeypatch.setattr(mdm_cli, "_get_mdm_engine", lambda: engine)

    args = argparse.Namespace(limit=None, tracking_status="active")
    result = mdm_cli._handle_seed_universe(args)

    assert result == 0
    assert "sec.gov" in captured["url"]
    assert sorted(get_tracked_ciks(engine, "active")) == [1234, 5678]


def test_seed_universe_cli_handler_respects_limit(engine, monkeypatch):
    import argparse
    import edgar_warehouse.mdm.cli as mdm_cli

    payload = b'{"0":{"cik_str":1,"ticker":"A","exchange":"NYSE"},"1":{"cik_str":2,"ticker":"B","exchange":"NYSE"},"2":{"cik_str":3,"ticker":"C","exchange":"NYSE"}}'

    monkeypatch.setattr(mdm_cli, "_download_sec_bytes", lambda url: payload)
    monkeypatch.setattr(mdm_cli, "_get_mdm_engine", lambda: engine)

    args = argparse.Namespace(limit=1, tracking_status="active")
    mdm_cli._handle_seed_universe(args)

    assert len(get_tracked_ciks(engine, "active")) == 1


def test_seed_universe_cli_handler_respects_tracking_status(engine, monkeypatch):
    import argparse
    import edgar_warehouse.mdm.cli as mdm_cli

    monkeypatch.setattr(mdm_cli, "_download_sec_bytes", lambda url: b'{"0":{"cik_str":99,"ticker":"ZZZ","exchange":"NYSE"}}')
    monkeypatch.setattr(mdm_cli, "_get_mdm_engine", lambda: engine)

    args = argparse.Namespace(limit=None, tracking_status="bootstrap_pending")
    mdm_cli._handle_seed_universe(args)

    assert get_tracked_ciks(engine, "bootstrap_pending") == [99]
    assert get_tracked_ciks(engine, "active") == []
