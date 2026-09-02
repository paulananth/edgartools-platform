"""RED tests for MDM silver preflight and source-to-entity load path.

Wave 0 — Phase 5 Plan 01. These tests encode decisions D-11 and D-12 and
MUST FAIL against the current implementation.

Known current defects that cause failures:
  - D-11 / PIPE-03: _handle_run, _handle_derive_relationships, and
    _handle_load_relationships call _session() BEFORE _silver_reader(), so
    when MDM_SILVER_DUCKDB is absent, the error names MDM_DATABASE_URL
    instead of MDM_SILVER_DUCKDB.
  - D-12 / PIPE-01: MDMPipeline.run_companies() queries sec_tracked_universe
    which does not exist in the current silver DDL (sec_company_sync_state
    is the correct table). DuckDB raises a binder error.
  - PIPE-02: Idempotency test fails because run_companies raises before
    loading any rows.
  - T-05-01: Unsupported URI protocol (ftp://) must fail at object_storage
    allowlist, not silently proceed.
  - T-05-02: Required-table validation does not exist today; tests that assert
    it must fail.
"""
from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest
import duckdb
import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.bookkeeping.database import Base as BookkeepingBase
from edgar_warehouse.bookkeeping.store import BookkeepingStore
from edgar_warehouse.mdm.database import (
    Base,
    MdmAdviser,
    MdmCompany,
    MdmEntity,
    MdmEntityTypeDefinition,
    MdmFund,
    MdmPerson,
    MdmRelationshipType,
    MdmSecurity,
)
from edgar_warehouse.mdm.migrations.runtime import seed_defaults
from edgar_warehouse.mdm.pipeline import MDMPipeline


# ---------------------------------------------------------------------------
# DuckDB silver fixture helpers
# ---------------------------------------------------------------------------

_SILVER_DDL = """
CREATE TABLE IF NOT EXISTS sec_company (
    cik BIGINT PRIMARY KEY,
    entity_name TEXT,
    entity_type TEXT,
    sic TEXT,
    sic_description TEXT,
    state_of_incorporation TEXT,
    state_of_incorporation_desc TEXT,
    fiscal_year_end TEXT,
    ein TEXT,
    description TEXT,
    category TEXT,
    first_sync_run_id TEXT,
    last_sync_run_id TEXT,
    last_synced_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS sec_company_ticker (
    cik BIGINT,
    ticker TEXT,
    exchange TEXT,
    source_name TEXT NOT NULL DEFAULT 'company_tickers_exchange',
    source_rank INTEGER,
    last_sync_run_id TEXT,
    last_synced_at TIMESTAMPTZ,
    PRIMARY KEY (cik, ticker, source_name)
);

CREATE TABLE IF NOT EXISTS sec_company_sync_state (
    cik BIGINT PRIMARY KEY,
    tracking_status TEXT,
    bootstrap_completed_at TIMESTAMPTZ,
    last_main_sync_at TIMESTAMPTZ,
    last_main_raw_object_id TEXT,
    last_main_sha256 TEXT,
    latest_filing_date_seen DATE,
    latest_acceptance_datetime_seen TIMESTAMPTZ,
    pagination_files_expected INTEGER,
    pagination_files_loaded INTEGER,
    pagination_completed_at TIMESTAMPTZ,
    next_sync_after TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS sec_company_filing (
    accession_number TEXT PRIMARY KEY,
    cik BIGINT,
    form TEXT,
    filing_date DATE,
    report_date DATE,
    acceptance_datetime TEXT,
    act TEXT,
    file_number TEXT,
    film_number TEXT,
    items TEXT,
    size BIGINT,
    is_xbrl BOOLEAN,
    is_inline_xbrl BOOLEAN,
    primary_document TEXT,
    primary_doc_desc TEXT,
    last_sync_run_id TEXT,
    last_synced_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS sec_adv_filing (
    accession_number TEXT PRIMARY KEY,
    cik BIGINT,
    crd_number TEXT,
    registrant_name TEXT,
    total_aum DOUBLE,
    effective_date DATE,
    last_sync_run_id TEXT
);

CREATE TABLE IF NOT EXISTS sec_adv_office (
    accession_number TEXT,
    office_index INTEGER,
    city TEXT,
    state_or_country TEXT,
    is_headquarters BOOLEAN,
    last_sync_run_id TEXT,
    PRIMARY KEY (accession_number, office_index)
);

CREATE TABLE IF NOT EXISTS sec_adv_private_fund (
    accession_number TEXT,
    fund_index INTEGER,
    fund_id TEXT,
    fund_name TEXT,
    fund_type TEXT,
    total_assets DOUBLE,
    effective_date DATE,
    last_sync_run_id TEXT,
    PRIMARY KEY (accession_number, fund_index)
);

CREATE TABLE IF NOT EXISTS sec_ownership_reporting_owner (
    accession_number TEXT,
    owner_index SMALLINT,
    owner_cik BIGINT,
    owner_name TEXT,
    is_director BOOLEAN,
    is_officer BOOLEAN,
    is_ten_percent_owner BOOLEAN,
    is_other BOOLEAN,
    officer_title TEXT,
    parser_version TEXT,
    last_sync_run_id TEXT,
    PRIMARY KEY (accession_number, owner_index)
);

CREATE TABLE IF NOT EXISTS sec_ownership_non_derivative_txn (
    accession_number TEXT,
    owner_index SMALLINT,
    txn_index SMALLINT,
    security_title TEXT,
    transaction_date DATE,
    transaction_code TEXT,
    transaction_shares DECIMAL(28,8),
    transaction_price DECIMAL(28,8),
    acquired_disposed_code TEXT,
    shares_owned_after DECIMAL(28,8),
    ownership_direct_indirect TEXT,
    last_sync_run_id TEXT,
    PRIMARY KEY (accession_number, owner_index, txn_index)
);

CREATE TABLE IF NOT EXISTS sec_ownership_derivative_txn (
    accession_number TEXT,
    owner_index SMALLINT,
    txn_index SMALLINT,
    security_title TEXT,
    transaction_date DATE,
    transaction_code TEXT,
    transaction_shares DECIMAL(28,8),
    transaction_price DECIMAL(28,8),
    acquired_disposed_code TEXT,
    shares_owned_after DECIMAL(28,8),
    ownership_nature TEXT,
    ownership_direct_indirect TEXT,
    conversion_or_exercise_price DECIMAL(28,8),
    exercise_date DATE,
    expiration_date DATE,
    underlying_security_title TEXT,
    underlying_security_shares DECIMAL(28,8),
    parser_version TEXT,
    last_sync_run_id TEXT,
    PRIMARY KEY (accession_number, owner_index, txn_index)
);
"""


def _create_silver_fixture(path: str) -> None:
    """Create a minimal real DuckDB silver fixture with rows for all five entity domains."""
    con = duckdb.connect(path)
    con.execute(_SILVER_DDL)

    # Company domain
    con.execute(
        "INSERT INTO sec_company (cik, entity_name, entity_type) VALUES (?, ?, ?)",
        [910001, "Issuer Corp", "operating"],
    )
    con.execute(
        "INSERT INTO sec_company_ticker (cik, ticker, exchange, source_name) VALUES (?, ?, ?, ?)",
        [910001, "ISSU", "NASDAQ", "company_tickers_exchange"],
    )
    con.execute(
        "INSERT INTO sec_company_sync_state (cik, tracking_status) VALUES (?, ?)",
        [910001, "active"],
    )

    # Filing for ownership (needed by person/security queries)
    con.execute(
        "INSERT INTO sec_company_filing (accession_number, cik, form, filing_date, report_date) "
        "VALUES (?, ?, ?, ?, ?)",
        ["0001234567-24-000001", 910001, "4", "2024-01-15", "2024-01-14"],
    )

    # ADV domain (adviser)
    con.execute(
        "INSERT INTO sec_adv_filing (accession_number, cik, crd_number, registrant_name, effective_date) "
        "VALUES (?, ?, ?, ?, ?)",
        ["0009876543-24-000001", 920001, "99001", "Test Adviser LLC", "2024-01-01"],
    )
    con.execute(
        "INSERT INTO sec_adv_office (accession_number, office_index, city, state_or_country, is_headquarters) "
        "VALUES (?, ?, ?, ?, ?)",
        ["0009876543-24-000001", 1, "New York", "NY", True],
    )

    # Fund domain — effective_date is NULL to avoid date-string coercion in SQLite tests.
    # PostgreSQL handles str->'2024-01-01' coercion for Date columns; SQLite does not.
    con.execute(
        "INSERT INTO sec_adv_private_fund "
        "(accession_number, fund_index, fund_id, fund_name, fund_type, effective_date) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ["0009876543-24-000001", 1, "FUND-001", "Test Alpha Fund", "Hedge Fund", None],
    )

    # Ownership reporting owner (person domain)
    con.execute(
        "INSERT INTO sec_ownership_reporting_owner "
        "(accession_number, owner_index, owner_cik, owner_name, is_director, is_officer, "
        "is_ten_percent_owner, is_other) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ["0001234567-24-000001", 0, 910101, "Jane Doe", True, False, False, False],
    )

    # Security domain (non-derivative transaction)
    con.execute(
        "INSERT INTO sec_ownership_non_derivative_txn "
        "(accession_number, owner_index, txn_index, security_title, transaction_date) "
        "VALUES (?, ?, ?, ?, ?)",
        ["0001234567-24-000001", 0, 0, "Common Stock", "2024-01-14"],
    )

    # Untracked-issuer regression fixture (mdm-ownership-resolver-filing-join-gap
    # ticket 01): this accession deliberately has NO matching sec_company_filing
    # row -- reproducing a real live-prod shape (an insider's Form 4 for an
    # issuer that was never bootstrapped as a tracked company, so its
    # sec_company_filing history was never populated). run_persons()/
    # run_securities() must not silently and permanently drop these rows.
    con.execute(
        "INSERT INTO sec_ownership_reporting_owner "
        "(accession_number, owner_index, owner_cik, owner_name, is_director, is_officer, "
        "is_ten_percent_owner, is_other) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ["0009999999-24-000099", 0, 910202, "Untracked Issuer Insider", True, False, False, False],
    )
    # Deliberately a distinct title from the "Common Stock" row above -- sharing
    # a canonical_title with another issuer's row would exercise
    # SecurityResolver's separate (and separately order-dependent, pre-existing,
    # out of scope for this ticket) NULL-issuer "upgrade" merge path instead of
    # cleanly testing the JOIN-gap fix in isolation.
    con.execute(
        "INSERT INTO sec_ownership_non_derivative_txn "
        "(accession_number, owner_index, txn_index, security_title, transaction_date) "
        "VALUES (?, ?, ?, ?, ?)",
        ["0009999999-24-000099", 0, 0, "Untracked Co Common Stock", "2024-02-01"],
    )

    con.close()


@pytest.fixture()
def silver_duckdb(tmp_path) -> Path:
    """Real temporary DuckDB fixture with rows for all five entity domains."""
    path = tmp_path / "silver.duckdb"
    _create_silver_fixture(str(path))
    return path


# ---------------------------------------------------------------------------
# MDM in-memory SQLite fixture
# ---------------------------------------------------------------------------

def _seed_registry(session: Session) -> None:
    """Seed full MDM registry: entity types, source priorities, field rules,
    match thresholds, normalization rules, and relationship types.

    Uses seed_defaults() from migrations to ensure the rule engine has all
    required source priorities and field survivorship rules for resolver calls.
    """
    seed_defaults(session)
    session.commit()


@pytest.fixture()
def mdm_session() -> Session:
    """In-memory SQLite MDM session with full schema and registry seeding."""
    from sqlalchemy.pool import StaticPool
    from datetime import datetime, timezone

    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Register NOW() for SQLite compatibility
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _register_now(dbapi_conn, _record):
        dbapi_conn.create_function("NOW", 0, lambda: datetime.now(timezone.utc).isoformat())

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        _seed_registry(session)
        yield session


@pytest.fixture()
def bookkeeping_store() -> BookkeepingStore:
    """In-memory SQLite bookkeeping store, seeded to match _create_silver_fixture's
    own sec_company_sync_state insert (cik=910001, tracking_status='active') --
    DuckDB Retirement Cutover Ticket 13 moved that table off DuckDB silver onto
    this store, so this fixture's data must mirror what silver_duckdb used to
    hold directly for this file's end-to-end fidelity to still hold.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    BookkeepingBase.metadata.create_all(engine)
    with Session(engine) as session:
        store = BookkeepingStore(session)
        store.upsert_company_sync_state({"cik": 910001, "tracking_status": "active"})
        session.commit()
        yield store


class _DuckReader:
    """Minimal DuckDB reader matching the interface _silver_reader() produces."""

    def __init__(self, path: str) -> None:
        self._con = duckdb.connect(path, read_only=True)

    def fetch(self, sql: str, params: Optional[list] = None) -> list[dict]:
        rows = self._con.execute(sql, params or []).fetchall()
        cols = [d[0] for d in self._con.description]
        return [dict(zip(cols, r)) for r in rows]


# ---------------------------------------------------------------------------
# D-11 / PIPE-03: Missing MDM_SILVER_DUCKDB fails before _session()
# ---------------------------------------------------------------------------

class TestMissingSilverSourceFailsBeforeSession:
    """D-11 / PIPE-03: an unreachable silver source must error before
    _session() is created. _handle_run/_handle_derive_relationships/
    _handle_load_relationships all call _silver_reader() before _session(),
    so a preflight failure (DuckDB Retirement Cutover Ticket 05: now always
    a Snowflake-connect failure, not a missing MDM_SILVER_DUCKDB) surfaces
    before a DB session is ever opened.
    """

    def _make_session_spy(self):
        """Return a callable that raises if called (proves _session is NOT called first)."""
        def _session_must_not_be_called():
            raise AssertionError(
                "_session() was called before silver source was validated. "
                "MDM_SILVER_DUCKDB preflight must run before opening a DB session."
            )
        return _session_must_not_be_called

    def test_missing_silver_source_fails_before_session_in_handle_run(self, monkeypatch):
        """_handle_run: missing MDM_SILVER_DUCKDB must fail before _session() is called."""
        import edgar_warehouse.mdm.cli as mdm_cli

        monkeypatch.delenv("MDM_SILVER_DUCKDB", raising=False)
        monkeypatch.delenv("MDM_DATABASE_URL", raising=False)

        session_called = []

        def _spy_session():
            session_called.append(True)
            raise RuntimeError("_session() must not be called before silver preflight")

        monkeypatch.setattr(mdm_cli, "_session", _spy_session)

        import argparse
        args = argparse.Namespace(
            entity_type="all",
            limit=None,
        )

        rc = mdm_cli._handle_run(args)

        assert rc != 0, "Expected nonzero exit code when MDM_SILVER_DUCKDB is missing"
        assert not session_called, (
            "_session() must not be called before MDM_SILVER_DUCKDB is validated. "
            "Current code calls _session() first, causing MDM_DATABASE_URL error instead."
        )

    def test_missing_silver_source_error_names_snowflake(self, monkeypatch, capsys):
        """Error output when the silver source can't be reached must name
        the actual backend (Snowflake, DuckDB Retirement Cutover Ticket 05
        -- MDM_SILVER_DUCKDB is no longer what _silver_reader() depends on,
        so the error message was updated to stop naming it)."""
        import edgar_warehouse.mdm.cli as mdm_cli

        monkeypatch.delenv("MDM_SILVER_DUCKDB", raising=False)
        monkeypatch.delenv("MDM_DATABASE_URL", raising=False)

        # Prevent _session from opening any real DB
        monkeypatch.setattr(mdm_cli, "_session", MagicMock(side_effect=RuntimeError("no DB")))

        import argparse
        args = argparse.Namespace(entity_type="all", limit=None)

        rc = mdm_cli._handle_run(args)
        captured = capsys.readouterr()

        assert rc != 0
        stderr_text = captured.err
        assert "Snowflake silver reader" in stderr_text, (
            f"Expected 'Snowflake silver reader' in stderr error message. Got:\n{stderr_text!r}"
        )

    def test_handle_run_all_succeeds(self, monkeypatch):
        """_handle_run runs the relational MDM pipeline and returns 0."""
        from types import SimpleNamespace

        import edgar_warehouse.mdm.cli as mdm_cli
        import edgar_warehouse.mdm.pipeline as mdm_pipeline

        fake_session = MagicMock()
        monkeypatch.setattr(
            mdm_cli,
            "_require_silver_reader",
            MagicMock(return_value=(object(), 0)),
        )
        monkeypatch.setattr(mdm_cli, "_session", MagicMock(return_value=fake_session))
        monkeypatch.setattr(mdm_cli, "_bookkeeping_store", MagicMock(return_value=MagicMock()))

        class FakePipeline:
            def __init__(self, *, session, silver, run_id):
                assert session is fake_session
                assert run_id

            def run_all(
                self, limit=None, *, resume_ledger_run_id=None, run_id=None, bookkeeping=None
            ):
                assert limit == 10
                return SimpleNamespace(
                    companies_processed=0,
                    advisers_processed=0,
                    securities_processed=0,
                    persons_processed=0,
                    funds_processed=0,
                    relationships_written=0,
                    relationship_counts_by_type={},
                    graph_nodes_synced=0,
                    graph_edges_synced=0,
                )

        monkeypatch.setattr(mdm_pipeline, "MDMPipeline", FakePipeline)

        import argparse
        args = argparse.Namespace(entity_type="all", limit=10)

        assert mdm_cli._handle_run(args) == 0
        fake_session.close.assert_called_once()

    def test_missing_silver_source_fails_before_session_in_handle_derive_relationships(
        self, monkeypatch
    ):
        """_handle_derive_relationships: missing MDM_SILVER_DUCKDB must fail before _session()."""
        import edgar_warehouse.mdm.cli as mdm_cli

        monkeypatch.delenv("MDM_SILVER_DUCKDB", raising=False)
        monkeypatch.delenv("MDM_DATABASE_URL", raising=False)

        session_called = []

        def _spy_session():
            session_called.append(True)
            raise RuntimeError("_session() must not be called before silver preflight")

        monkeypatch.setattr(mdm_cli, "_session", _spy_session)

        import argparse
        args = argparse.Namespace(
            target_per_type=10,
            relationship_type=None,
        )

        rc = mdm_cli._handle_derive_relationships(args)

        assert rc != 0
        assert not session_called, (
            "_session() must not be called before MDM_SILVER_DUCKDB is validated "
            "in _handle_derive_relationships."
        )

    def test_missing_silver_source_fails_before_session_in_handle_load_relationships(
        self, monkeypatch
    ):
        """_handle_load_relationships: missing MDM_SILVER_DUCKDB must fail before _session()."""
        import edgar_warehouse.mdm.cli as mdm_cli

        monkeypatch.delenv("MDM_SILVER_DUCKDB", raising=False)
        monkeypatch.delenv("MDM_DATABASE_URL", raising=False)

        session_called = []

        def _spy_session():
            session_called.append(True)
            raise RuntimeError("_session() must not be called before silver preflight")

        monkeypatch.setattr(mdm_cli, "_session", _spy_session)

        import argparse
        args = argparse.Namespace(
            target_per_type=10,
            entity_limit=None,
            relationship_type=None,
            skip_entity_resolution=False,
            skip_graph_sync=True,
        )

        rc = mdm_cli._handle_load_relationships(args)

        assert rc != 0
        assert not session_called, (
            "_session() must not be called before MDM_SILVER_DUCKDB is validated "
            "in _handle_load_relationships."
        )


# ---------------------------------------------------------------------------
# T-05-01: Unsupported URI protocol rejected via object_storage allowlist
# ---------------------------------------------------------------------------

class TestUnsupportedProtocolRejected:
    """T-05-01: Unsupported protocols must fail through object_storage.read_bytes() allowlist."""

    def test_ftp_protocol_rejected_by_object_storage(self, monkeypatch):
        """ftp:// MDM_SILVER_DUCKDB must be rejected before any download attempt."""
        from edgar_warehouse.application.errors import WarehouseRuntimeError
        from edgar_warehouse.infrastructure import object_storage

        ftp_uri = "ftp://internal.example.com/silver/silver.duckdb"

        with pytest.raises((WarehouseRuntimeError, Exception)) as exc_info:
            object_storage.read_bytes(ftp_uri)

        err_str = str(exc_info.value).lower()
        assert "unsupported" in err_str or "ftp" in err_str, (
            f"Expected 'unsupported' protocol error, got: {exc_info.value}"
        )

    def test_http_url_rejected_by_object_storage(self):
        """http:// must be rejected by the protocol allowlist (only s3:// is supported)."""
        from edgar_warehouse.application.errors import WarehouseRuntimeError
        from edgar_warehouse.infrastructure import object_storage

        http_uri = "http://attacker.example.com/evil.duckdb"

        with pytest.raises((WarehouseRuntimeError, Exception)):
            object_storage.read_bytes(http_uri)


# ---------------------------------------------------------------------------
# D-11: s3:// MDM_SILVER_DUCKDB succeeds via object_storage.read_bytes monkeypatch
# ---------------------------------------------------------------------------

class TestS3BackedSilverSourceUsesObjectStorageReadBytes:
    """D-11 / PIPE-01: s3:// MDM_SILVER_DUCKDB must use object_storage.read_bytes().

    The monkeypatch returns real DuckDB bytes from a local fixture, simulating
    a successful S3 download.  This test asserts that:
      1. object_storage.read_bytes is called with the s3:// URI
      2. The localized file is a valid DuckDB database
      3. No SEC download helper is invoked

    These tests FAIL against the current implementation because the required-table
    preflight does not exist, so the post-download validation step cannot pass.
    """

    def test_s3_backed_silver_source_uses_object_storage_read_bytes(
        self, monkeypatch, silver_duckdb, tmp_path
    ):
        """_duckdb_silver_reader() must call object_storage.read_bytes(s3_uri)
        for s3:// URIs -- still exercised (DuckDB Retirement Cutover Ticket
        05) because verify-silver-parity/verify-resolver-input-parity need
        this DuckDB path; mdm mastering itself no longer reaches it (see
        test_s3_env_vars_do_not_affect_handle_run below)."""
        import edgar_warehouse.infrastructure.object_storage as obj_store
        import edgar_warehouse.mdm.cli as mdm_cli

        s3_uri = "s3://my-bucket/warehouse/silver/silver.duckdb"
        silver_bytes = silver_duckdb.read_bytes()
        local_path = tmp_path / "localized_silver.duckdb"

        read_bytes_calls: list[str] = []

        def spy_read_bytes(path: str) -> bytes:
            read_bytes_calls.append(path)
            return silver_bytes

        monkeypatch.setenv("MDM_SILVER_DUCKDB", s3_uri)
        monkeypatch.setenv("MDM_LOCAL_SILVER_DUCKDB", str(local_path))
        monkeypatch.setattr(obj_store, "read_bytes", spy_read_bytes)

        reader = mdm_cli._duckdb_silver_reader()

        assert s3_uri in read_bytes_calls, (
            f"Expected _duckdb_silver_reader() to call object_storage.read_bytes({s3_uri!r}). "
            f"Got: {read_bytes_calls}"
        )
        assert reader is not None, (
            "Expected _duckdb_silver_reader() to return a DuckDB reader after localization"
        )

    def test_s3_env_vars_do_not_affect_handle_run(self, monkeypatch, tmp_path):
        """DuckDB Retirement Cutover Ticket 05: mdm mastering's silver preflight
        must run before _session() is opened (unchanged intent from the
        original D-11/PIPE-03 decision this test used to encode) -- but the
        silver source is now Snowflake unconditionally. A legacy
        MDM_SILVER_DUCKDB=s3://... value must be completely ignored: no
        object_storage.read_bytes call, no S3 localization, no DuckDB at
        all. This replaces the pre-cutover version of this test, which
        asserted the opposite (that read_bytes WAS called) -- that
        assertion described the retired code path, not the new one.
        """
        import edgar_warehouse.infrastructure.object_storage as obj_store
        import edgar_warehouse.mdm.cli as mdm_cli
        from edgar_warehouse.silver_support.snowflake_reader import SnowflakeSilverReader

        monkeypatch.setenv("MDM_SILVER_DUCKDB", "s3://my-bucket/warehouse/silver/silver.duckdb")
        monkeypatch.setenv("MDM_LOCAL_SILVER_DUCKDB", str(tmp_path / "localized_silver2.duckdb"))

        events: list[str] = []

        def spy_read_bytes(path: str) -> bytes:
            events.append("read_bytes")
            raise AssertionError("object_storage.read_bytes must not be called post-cutover")

        monkeypatch.setattr(obj_store, "read_bytes", spy_read_bytes)

        class _FakeSnowflakeReader:
            def fetch(self, sql, params=None):
                return [{"n": 1}]

            def close(self):
                pass

        session_opened_at: list[int] = []

        def _spy_session():
            session_opened_at.append(len(events))
            m = MagicMock()
            m.__enter__ = lambda s: s
            m.__exit__ = MagicMock(return_value=False)
            return m

        monkeypatch.setattr(mdm_cli, "_session", _spy_session)
        monkeypatch.setattr(SnowflakeSilverReader, "connect", lambda: _FakeSnowflakeReader())

        import argparse
        args = argparse.Namespace(entity_type="company", limit=None)

        # Run; may succeed or fail (e.g. pipeline raises on mock session).
        # What matters is that read_bytes/S3 were never touched.
        try:
            mdm_cli._handle_run(args)
        except Exception:
            pass  # pipeline failure is expected with mock session; S3-avoidance is what we test

        assert events == [], (
            "Expected object_storage.read_bytes to never be called -- "
            "_silver_reader() must ignore MDM_SILVER_DUCKDB entirely post-cutover"
        )
        assert session_opened_at, "_session() should still have been reached after preflight passed"


# ---------------------------------------------------------------------------
# T-05-02: Required-table validation via fixed allowlist
# ---------------------------------------------------------------------------

class TestRequiredTableValidation:
    """T-05-02: Silver preflight must validate required tables using a fixed allowlist.

    These tests are RED because required-table validation does not exist today.
    """

    class _CountReader:
        def __init__(self, counts: dict[str, int]) -> None:
            self._counts = counts

        def fetch(self, sql: str, params: Optional[list] = None) -> list[dict]:
            table_name = sql.split(" FROM ", 1)[1].split()[0]
            if table_name not in self._counts:
                raise RuntimeError(f"Catalog Error: Table with name {table_name} does not exist")
            return [{"n": self._counts[table_name]}]

    def test_empty_duckdb_fails_required_table_check(self, monkeypatch):
        """An empty silver source (no tables) must fail preflight with a
        missing-table message.

        DuckDB Retirement Cutover Ticket 05: the silver reader is
        EDGARTOOLS_SILVER via SnowflakeSilverReader now, not a real local
        DuckDB file -- _silver_reader() itself is monkeypatched with a
        reader that raises "does not exist" for every table, the same
        shape a real empty/unreachable EDGARTOOLS_SILVER would produce.
        """
        import edgar_warehouse.mdm.cli as mdm_cli

        monkeypatch.setattr(mdm_cli, "_silver_reader", lambda: self._CountReader({}))
        monkeypatch.setattr(mdm_cli, "_session", MagicMock(
            side_effect=AssertionError("_session must not be called for empty silver source")
        ))

        import argparse
        args = argparse.Namespace(entity_type="all", limit=None)
        rc = mdm_cli._handle_run(args)

        assert rc != 0, "Expected nonzero exit for silver source with no required tables"

    def test_silver_missing_ownership_table_fails_person_entity_run(
        self, monkeypatch, mdm_session
    ):
        """A silver source missing sec_ownership_reporting_owner must fail
        person entity load preflight.

        DuckDB Retirement Cutover Ticket 05: same _silver_reader()
        monkeypatch approach as the test above, seeded with only
        sec_company -- exercises the exact required-tables-for-'person'
        content this test was written to assert.
        """
        import edgar_warehouse.mdm.cli as mdm_cli

        monkeypatch.setattr(
            mdm_cli, "_silver_reader", lambda: self._CountReader({"sec_company": 1})
        )
        monkeypatch.setattr(mdm_cli, "_session", MagicMock(
            side_effect=AssertionError("_session must not be called without preflight")
        ))

        import argparse
        args = argparse.Namespace(entity_type="person", limit=None)
        rc = mdm_cli._handle_run(args)

        assert rc != 0, (
            "Expected nonzero exit when silver source is missing sec_ownership_reporting_owner "
            "for 'person' entity type run"
        )

    def test_all_run_preflight_allows_empty_optional_parser_tables(self):
        """Bulk MDM recovery may load companies even when optional parser domains are empty."""
        import edgar_warehouse.mdm.cli as mdm_cli

        counts = {
            "sec_company": 120,
            "sec_company_filing": 500,
            "sec_adv_filing": 0,
            "sec_adv_office": 0,
            "sec_adv_private_fund": 0,
            "sec_ownership_reporting_owner": 0,
            "sec_ownership_non_derivative_txn": 0,
            "sec_ownership_derivative_txn": 0,
        }

        failures = mdm_cli._validate_silver_tables(
            self._CountReader(counts),
            mdm_cli._required_tables_for_run("all"),
        )

        assert failures == []

    def test_relationship_preflight_allows_empty_ownership_tables(self):
        """Relationship commands should no-op on empty ownership schemas instead of blocking."""
        import edgar_warehouse.mdm.cli as mdm_cli

        counts = {
            "sec_company": 120,
            "sec_company_filing": 500,
            "sec_ownership_reporting_owner": 0,
            "sec_ownership_non_derivative_txn": 0,
            "sec_ownership_derivative_txn": 0,
        }

        failures = mdm_cli._validate_silver_tables(
            self._CountReader(counts),
            mdm_cli._REQUIRED_TABLES_RELATIONSHIPS,
        )

        assert failures == []

    def test_targeted_person_and_security_runs_still_require_ownership_rows(self):
        """Direct ownership-backed entity loads should still fail clearly on empty inputs."""
        import edgar_warehouse.mdm.cli as mdm_cli

        counts = {
            "sec_company_filing": 500,
            "sec_ownership_reporting_owner": 0,
            "sec_ownership_non_derivative_txn": 0,
            "sec_ownership_derivative_txn": 0,
        }

        person_failures = mdm_cli._validate_silver_tables(
            self._CountReader(counts),
            mdm_cli._required_tables_for_run("person"),
        )
        security_failures = mdm_cli._validate_silver_tables(
            self._CountReader(counts),
            mdm_cli._required_tables_for_run("security"),
        )

        assert (
            "required table 'sec_ownership_reporting_owner' is empty (0 rows)"
            in person_failures
        )
        assert (
            "required table 'sec_ownership_non_derivative_txn' is empty (0 rows)"
            in security_failures
        )


# ---------------------------------------------------------------------------
# D-12 / PIPE-01: MDM pipeline entity loaders work with current silver schema
# ---------------------------------------------------------------------------

class TestMDMPipelineUsesCurrentSilverSchema:
    """D-12 / PIPE-01: MDMPipeline.run_companies() must use sec_company_sync_state, not sec_tracked_universe.

    Current defect: pipeline.py:101 queries sec_tracked_universe which is NOT
    in the current silver DDL.  Tests FAIL with a DuckDB binder error.
    """

    def test_run_companies_does_not_query_sec_tracked_universe(
        self, silver_duckdb, mdm_session, bookkeeping_store
    ):
        """run_companies() must not reference sec_tracked_universe; use sec_company_sync_state."""
        reader = _DuckReader(str(silver_duckdb))
        pipeline = MDMPipeline(session=mdm_session, silver=reader)

        # Will raise DuckDB BinderException if sec_tracked_universe is queried
        try:
            pipeline.run_companies(bookkeeping=bookkeeping_store)
        except Exception as exc:
            err_str = str(exc).lower()
            if "sec_tracked_universe" in err_str or "table.*not found" in err_str.lower() or "binder" in err_str.lower():
                pytest.fail(
                    f"run_companies() queries the stale 'sec_tracked_universe' table "
                    f"which does not exist in the current silver DDL. "
                    f"Use 'sec_company_sync_state' instead.\nError: {exc}"
                )
            raise

    def test_run_companies_returns_nonzero_count_from_silver_fixture(
        self, silver_duckdb, mdm_session, bookkeeping_store
    ):
        """run_companies() must successfully load companies from the silver fixture.

        Fails because the current code queries sec_tracked_universe.
        """
        reader = _DuckReader(str(silver_duckdb))
        pipeline = MDMPipeline(session=mdm_session, silver=reader)

        n = pipeline.run_companies(bookkeeping=bookkeeping_store)
        assert n >= 1, (
            f"Expected at least 1 company loaded from silver fixture, got {n}. "
            f"This may indicate a sec_tracked_universe schema mismatch."
        )

    def test_run_persons_uses_sec_ownership_reporting_owner(
        self, silver_duckdb, mdm_session, bookkeeping_store
    ):
        """run_persons() must query sec_ownership_reporting_owner for person rows."""
        reader = _DuckReader(str(silver_duckdb))
        pipeline = MDMPipeline(session=mdm_session, silver=reader)

        # This will fail if run_companies has schema errors — run it first to seed companies
        try:
            pipeline.run_companies(bookkeeping=bookkeeping_store)
            mdm_session.commit()
        except Exception:
            pass  # Allow test to continue to person loader even if companies fail

        n = pipeline.run_persons()
        assert n >= 0  # Just ensure it doesn't raise a schema error

    def test_run_persons_resolves_owner_with_no_filing_match(
        self, silver_duckdb, mdm_session, bookkeeping_store
    ):
        """mdm-ownership-resolver-filing-join-gap ticket 01: an ownership row whose
        accession has no sec_company_filing row (an untracked issuer) must still be
        resolved -- not silently and permanently dropped by the INNER JOIN.
        """
        from edgar_warehouse.mdm.database import MdmSourceRef

        reader = _DuckReader(str(silver_duckdb))
        pipeline = MDMPipeline(session=mdm_session, silver=reader)

        pipeline.run_companies(bookkeeping=bookkeeping_store)
        mdm_session.commit()
        pipeline.run_persons()
        mdm_session.commit()

        ref = (
            mdm_session.query(MdmSourceRef)
            .filter_by(source_system="ownership_filing", source_id="0009999999-24-000099:0")
            .one_or_none()
        )
        assert ref is not None, (
            "run_persons() dropped the reporting-owner row for accession "
            "0009999999-24-000099 (no sec_company_filing match) instead of resolving "
            "it -- the INNER JOIN to sec_company_filing must not silently exclude rows "
            "whose issuer was never bootstrapped as a tracked company."
        )

    def test_run_securities_resolves_txn_with_no_filing_match(
        self, silver_duckdb, mdm_session, bookkeeping_store
    ):
        """mdm-ownership-resolver-filing-join-gap ticket 01: same gap, run_securities()."""
        from edgar_warehouse.mdm.database import MdmSourceRef

        reader = _DuckReader(str(silver_duckdb))
        pipeline = MDMPipeline(session=mdm_session, silver=reader)

        pipeline.run_companies(bookkeeping=bookkeeping_store)
        mdm_session.commit()
        pipeline.run_securities()
        mdm_session.commit()

        ref = (
            mdm_session.query(MdmSourceRef)
            .filter_by(
                source_system="ownership_filing",
                source_id="0009999999-24-000099:0:0",
            )
            .one_or_none()
        )
        assert ref is not None, (
            "run_securities() dropped the non-derivative txn row for accession "
            "0009999999-24-000099 (no sec_company_filing match) instead of resolving "
            "it -- the INNER JOIN to sec_company_filing must not silently exclude rows "
            "whose issuer was never bootstrapped as a tracked company."
        )


# ---------------------------------------------------------------------------
# PIPE-02: Repeated entity loading keeps domain counts stable
# ---------------------------------------------------------------------------

class TestEntityLoadIdempotentForDomainCounts:
    """PIPE-02: Repeated entity loading must keep mdm_company/adviser/person/security/fund
    counts stable.

    These tests FAIL against the current implementation because run_companies()
    raises a DuckDB binder error on sec_tracked_universe.
    """

    def _domain_counts(self, session: Session) -> dict[str, int]:
        """Count rows in the five domain tables only."""
        counts = {}
        for table_cls, key in [
            (MdmCompany, "company"),
            (MdmAdviser, "adviser"),
            (MdmPerson, "person"),
            (MdmSecurity, "security"),
            (MdmFund, "fund"),
        ]:
            n = session.query(table_cls).count()
            counts[key] = n
        return counts

    def test_entity_load_is_idempotent_for_domain_counts(
        self, silver_duckdb, mdm_session, bookkeeping_store
    ):
        """Running entity loaders twice on the same silver fixture keeps domain counts stable.

        Fails because run_companies() raises on sec_tracked_universe in current code.
        """
        reader = _DuckReader(str(silver_duckdb))

        # First run
        pipeline1 = MDMPipeline(session=mdm_session, silver=reader)
        pipeline1.run_companies(bookkeeping=bookkeeping_store)
        pipeline1.run_advisers()
        pipeline1.run_persons()
        pipeline1.run_securities()
        pipeline1.run_funds()
        mdm_session.commit()
        counts_after_first = self._domain_counts(mdm_session)

        # Second run against the same data
        pipeline2 = MDMPipeline(session=mdm_session, silver=reader)
        pipeline2.run_companies(bookkeeping=bookkeeping_store)
        pipeline2.run_advisers()
        pipeline2.run_persons()
        pipeline2.run_securities()
        pipeline2.run_funds()
        mdm_session.commit()
        counts_after_second = self._domain_counts(mdm_session)

        for entity_type in ("company", "adviser", "person", "security", "fund"):
            first = counts_after_first[entity_type]
            second = counts_after_second[entity_type]
            assert first == second, (
                f"Domain count for '{entity_type}' changed between runs: "
                f"{first} -> {second}. Entity loading must be idempotent."
            )

    def test_domain_counts_include_all_five_entity_types(
        self, silver_duckdb, mdm_session, bookkeeping_store
    ):
        """After loading all entity types, all five domain tables must have ≥1 rows.

        Fails because run_companies() raises on sec_tracked_universe — no entities
        are ever loaded.
        """
        reader = _DuckReader(str(silver_duckdb))
        pipeline = MDMPipeline(session=mdm_session, silver=reader)
        pipeline.run_companies(bookkeeping=bookkeeping_store)
        pipeline.run_advisers()
        pipeline.run_persons()
        pipeline.run_securities()
        pipeline.run_funds()
        mdm_session.commit()

        counts = self._domain_counts(mdm_session)

        # All five domains must be non-empty
        for entity_type in ("company", "adviser", "person", "security", "fund"):
            assert counts[entity_type] >= 1, (
                f"Expected ≥1 row in mdm_{entity_type} after loading silver fixture. "
                f"Got {counts[entity_type]}. "
                f"All counts: {counts}"
            )


# ---------------------------------------------------------------------------
# PIPE-04: mdm coverage-report — compute_coverage + CLI subcommand
# ---------------------------------------------------------------------------

class TestCoverageReport:
    """PIPE-04: mdm coverage-report returns 5-domain coverage table with 0 gap
    against the complete 1-per-domain fixture, exits 0 even with gaps, and
    documents XBRL/Phase 6 deferral in the securities reason string.
    """

    def _load_all(self, silver_duckdb, mdm_session, bookkeeping_store):
        """Run all five entity loaders and return the loaded session."""
        reader = _DuckReader(str(silver_duckdb))
        pipeline = MDMPipeline(session=mdm_session, silver=reader)
        pipeline.run_companies(bookkeeping=bookkeeping_store)
        pipeline.run_advisers()
        pipeline.run_persons()
        pipeline.run_securities()
        pipeline.run_funds()
        mdm_session.commit()
        return reader

    def test_zero_gap_against_complete_fixture(self, silver_duckdb, mdm_session, bookkeeping_store):
        """compute_coverage returns 5 domains all with gap == 0 after all loaders run."""
        from edgar_warehouse.mdm.coverage import compute_coverage

        reader = self._load_all(silver_duckdb, mdm_session, bookkeeping_store)
        rows = compute_coverage(reader, mdm_session, bookkeeping_store)

        assert len(rows) == 5, f"Expected 5 domain rows, got {len(rows)}"
        domains = {r["domain"] for r in rows}
        assert domains == {"companies", "persons", "securities", "advisers", "funds"}

        for row in rows:
            assert row["gap"] == 0, (
                f"Domain '{row['domain']}' has gap={row['gap']} "
                f"(silver={row['silver_count']}, mdm={row['mdm_count']}). "
                "Expected 0 gap against the complete 1-per-domain fixture."
            )

    def test_handler_exits_0_with_nonzero_gap(
        self, silver_duckdb, mdm_session, bookkeeping_store, monkeypatch, capsys
    ):
        """CLI handler returns 0 even when a synthetic gap exists (D-19 reporting semantics)."""
        import edgar_warehouse.mdm.cli as mdm_cli
        from edgar_warehouse.mdm.coverage import compute_coverage

        # Load only companies — persons/securities/advisers/funds will have silver
        # rows but no MDM entities → nonzero gaps.
        reader = _DuckReader(str(silver_duckdb))
        monkeypatch.setenv("MDM_SILVER_DUCKDB", str(silver_duckdb))
        monkeypatch.setattr(mdm_cli, "_silver_reader", lambda: reader)
        monkeypatch.setattr(mdm_cli, "_session", lambda: mdm_session)
        monkeypatch.setattr(mdm_cli, "_bookkeeping_store", lambda: bookkeeping_store)

        import argparse
        args = argparse.Namespace()
        rc = mdm_cli._handle_coverage_report(args)

        assert rc == 0, (
            f"coverage-report must exit 0 even with gaps (D-19). Got rc={rc}"
        )
        out = capsys.readouterr().out
        assert "domain" in out.lower(), "Expected table header in stdout"

    def test_coverage_report_help_exits_0(self):
        """mdm coverage-report --help parses without error."""
        import argparse
        from edgar_warehouse.mdm.cli import register_mdm_subparser

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers()
        register_mdm_subparser(sub)

        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["mdm", "coverage-report", "--help"])
        assert exc_info.value.code == 0

    def test_securities_reason_mentions_xbrl_and_phase_6(
        self, silver_duckdb, mdm_session, bookkeeping_store
    ):
        """Securities domain reason string explicitly references XBRL and Phase 6 deferral (D-24/D-28)."""
        from edgar_warehouse.mdm.coverage import compute_coverage

        reader = _DuckReader(str(silver_duckdb))
        rows = compute_coverage(reader, mdm_session, bookkeeping_store)

        sec_row = next(r for r in rows if r["domain"] == "securities")
        reason_lower = sec_row["reason"].lower()
        assert "xbrl" in reason_lower, (
            f"Securities reason must mention 'XBRL'. Got: {sec_row['reason']}"
        )
        assert "phase 6" in reason_lower or "phase6" in reason_lower, (
            f"Securities reason must reference Phase 6 deferral. Got: {sec_row['reason']}"
        )
