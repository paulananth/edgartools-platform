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


def test_bulk_upsert_populates_ticker_attribute(engine):
    rows = [{"cik": 1234, "ticker": "AAPL", "exchange": "NASDAQ"}]
    bulk_upsert_universe(engine, rows)
    with engine.connect() as conn:
        ticker, primary_ticker = conn.execute(
            text("SELECT ticker, primary_ticker FROM mdm_company WHERE cik = 1234")
        ).one()
    assert ticker == "AAPL"
    assert primary_ticker == "AAPL"


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
    """_handle_seed_universe must fetch tickers via edgartools, parse them, and upsert into MDM."""
    import argparse
    import edgar_warehouse.mdm.cli as mdm_cli

    fake_payload = {
        "fields": ["cik", "ticker", "exchange"],
        "data": [[1234, "AAPL", "NASDAQ"], [5678, "MSFT", "NASDAQ"]],
    }

    monkeypatch.setattr(mdm_cli, "_company_tickers_payload", lambda: fake_payload)
    monkeypatch.setattr(mdm_cli, "_get_mdm_engine", lambda: engine)

    args = argparse.Namespace(limit=None, tracking_status="active", source="edgartools", silver_path=None)
    result = mdm_cli._handle_seed_universe(args)

    assert result == 0
    assert sorted(get_tracked_ciks(engine, "active")) == [1234, 5678]


def test_seed_universe_cli_handler_respects_limit(engine, monkeypatch):
    import argparse
    import edgar_warehouse.mdm.cli as mdm_cli

    payload = {
        "fields": ["cik", "ticker", "exchange"],
        "data": [[1, "A", "NYSE"], [2, "B", "NYSE"], [3, "C", "NYSE"]],
    }

    monkeypatch.setattr(mdm_cli, "_company_tickers_payload", lambda: payload)
    monkeypatch.setattr(mdm_cli, "_get_mdm_engine", lambda: engine)

    args = argparse.Namespace(limit=1, tracking_status="active", source="edgartools", silver_path=None)
    mdm_cli._handle_seed_universe(args)

    assert len(get_tracked_ciks(engine, "active")) == 1


def test_seed_universe_cli_handler_respects_tracking_status(engine, monkeypatch):
    import argparse
    import edgar_warehouse.mdm.cli as mdm_cli

    payload = {"fields": ["cik", "ticker", "exchange"], "data": [[99, "ZZZ", "NYSE"]]}

    monkeypatch.setattr(mdm_cli, "_company_tickers_payload", lambda: payload)
    monkeypatch.setattr(mdm_cli, "_get_mdm_engine", lambda: engine)

    args = argparse.Namespace(limit=None, tracking_status="bootstrap_pending", source="edgartools", silver_path=None)
    mdm_cli._handle_seed_universe(args)

    assert get_tracked_ciks(engine, "bootstrap_pending") == [99]
    assert get_tracked_ciks(engine, "active") == []


def test_company_tickers_payload_uses_edgartools_not_direct_sec_call(monkeypatch):
    """_company_tickers_payload must source data from edgar.get_company_tickers,
    not a direct SEC HTTP call, and must tolerate a missing (None) exchange
    without turning it into the truthy string "nan" (pandas NaN vs. None trap)."""
    import pandas as pd
    import edgar
    import edgar_warehouse.mdm.cli as mdm_cli

    fake_df = pd.DataFrame(
        {
            "cik": [1234, 5678],
            "ticker": ["AAPL", "ZZZZ"],
            "exchange": ["NASDAQ", None],
            "company": ["Apple Inc.", "No Exchange Co."],
        }
    )
    # edgartools is imported lazily inside _company_tickers_payload (not at
    # mdm/cli.py module level) so every other mdm subcommand avoids pulling in
    # pandas/pyarrow transitively -- patch the real edgar module's attribute
    # directly rather than mdm_cli.edgar, which no longer exists as a
    # module-level name.
    monkeypatch.setattr(edgar, "get_company_tickers", lambda: fake_df)

    payload = mdm_cli._company_tickers_payload()

    assert payload["fields"] == ["cik", "ticker", "exchange"]
    assert [1234, "AAPL", "NASDAQ"] in payload["data"]
    assert [5678, "ZZZZ", None] in payload["data"]


def test_importing_mdm_cli_does_not_pull_in_edgartools_pandas_pyarrow():
    """The MDM ECS image (Dockerfile.mdm-deps, `.[s3,mdm-runtime]`) exists to
    be leaner than the full warehouse image, but edgartools/pyarrow/spacy are
    unconditional base package deps (pyproject.toml), so they get installed
    regardless. The actual runtime cost this test guards against is import
    time: mdm/cli.py used to `import edgar` at module level for one helper
    (_company_tickers_payload, used only by the seed-universe subcommand),
    which transitively loaded pandas+pyarrow on every mdm subcommand
    invocation (run/sync-graph/verify-graph/backfill-relationships included).
    Run in a subprocess so this test's own imports (e.g. pandas, imported
    directly above for the fixture) can't contaminate the sys.modules check."""
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys\n"
            "from edgar_warehouse.mdm import cli as mdm_cli\n"
            "from edgar_warehouse.mdm import pipeline as mdm_pipeline\n"
            "loaded = sorted(m for m in ('pandas', 'pyarrow', 'spacy') if m in sys.modules)\n"
            "print(','.join(loaded))\n",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "", (
        f"importing mdm.cli/mdm.pipeline unexpectedly loaded: {result.stdout.strip()}"
    )
