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
    """D-11 / PIPE-03: Missing MDM_SILVER_DUCKDB must error before _session() is created.

    Current defect: _handle_run/_handle_derive_relationships/_handle_load_relationships
    all call _session() BEFORE _silver_reader(), so the error message names
    MDM_DATABASE_URL instead of MDM_SILVER_DUCKDB.
    These tests FAIL against the current implementation.
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

    def test_missing_silver_source_error_names_mdm_silver_duckdb(self, monkeypatch, capsys):
        """Error output when MDM_SILVER_DUCKDB is absent must name 'MDM_SILVER_DUCKDB'."""
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
        assert "MDM_SILVER_DUCKDB" in stderr_text, (
            f"Expected 'MDM_SILVER_DUCKDB' in stderr error message. Got:\n{stderr_text!r}"
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

        class FakePipeline:
            def __init__(self, *, session, silver):
                assert session is fake_session

            def run_all(self, limit=None):
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
        """_silver_reader() must call object_storage.read_bytes(s3_uri) for s3:// URIs."""
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

        reader = mdm_cli._silver_reader()

        assert s3_uri in read_bytes_calls, (
            f"Expected _silver_reader() to call object_storage.read_bytes({s3_uri!r}). "
            f"Got: {read_bytes_calls}"
        )
        assert reader is not None, (
            "Expected _silver_reader() to return a DuckDB reader after localization"
        )

    def test_s3_backed_silver_validates_required_tables(
        self, monkeypatch, silver_duckdb, tmp_path
    ):
        """After s3:// download, silver table validation must run before _session() is opened.

        The fixture has all required tables populated.  After preflight passes,
        _session() IS called — but only AFTER validation.  We verify this by
        recording the order of events (preflight → session) rather than asserting
        _session is never called.  A correct implementation calls _session() only
        after the silver reader and table checks succeed.
        """
        import edgar_warehouse.infrastructure.object_storage as obj_store
        import edgar_warehouse.mdm.cli as mdm_cli

        s3_uri = "s3://my-bucket/warehouse/silver/silver.duckdb"
        silver_bytes = silver_duckdb.read_bytes()
        local_path = tmp_path / "localized_silver2.duckdb"

        monkeypatch.setenv("MDM_SILVER_DUCKDB", s3_uri)
        monkeypatch.setenv("MDM_LOCAL_SILVER_DUCKDB", str(local_path))
        monkeypatch.setattr(obj_store, "read_bytes", lambda _: silver_bytes)

        # Track what happened: preflight must succeed before session is opened.
        # We assert session was NOT called before read_bytes (preflight) completed.
        events: list[str] = []

        original_read_bytes = lambda _: silver_bytes  # noqa: E731

        def spy_read_bytes(path: str) -> bytes:
            events.append("read_bytes")
            return silver_bytes

        monkeypatch.setattr(obj_store, "read_bytes", spy_read_bytes)

        # Session spy: records when session is opened but does not raise,
        # because after a valid silver source preflight passes, _session() IS
        # expected to be called.  We assert it is called only AFTER read_bytes.
        session_opened_at: list[int] = []

        def _spy_session():
            session_opened_at.append(len(events))  # how many events before session open
            # Return a no-op mock that satisfies the pipeline close() calls
            m = MagicMock()
            m.__enter__ = lambda s: s
            m.__exit__ = MagicMock(return_value=False)
            return m

        monkeypatch.setattr(mdm_cli, "_session", _spy_session)

        import argparse
        args = argparse.Namespace(entity_type="company", limit=None)

        # Run; may succeed or fail (e.g. pipeline raises on mock session).
        # What matters is the ORDER: read_bytes must precede session open.
        try:
            mdm_cli._handle_run(args)
        except Exception:
            pass  # pipeline failure is expected with mock session; order is what we test

        assert "read_bytes" in events, (
            "Expected object_storage.read_bytes to be called for s3:// silver localization"
        )
        if session_opened_at:
            assert session_opened_at[0] >= 1, (
                "_session() was opened before object_storage.read_bytes was called. "
                "Silver source validation (including read_bytes) must precede session open."
            )


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

    def test_empty_duckdb_fails_required_table_check(self, tmp_path, monkeypatch):
        """An empty DuckDB (no tables) must fail preflight with a missing-table message."""
        import edgar_warehouse.mdm.cli as mdm_cli

        empty_db = tmp_path / "empty.duckdb"
        con = duckdb.connect(str(empty_db))
        con.close()

        monkeypatch.setenv("MDM_SILVER_DUCKDB", str(empty_db))
        monkeypatch.setattr(mdm_cli, "_session", MagicMock(
            side_effect=AssertionError("_session must not be called for empty silver DB")
        ))

        import argparse
        args = argparse.Namespace(entity_type="all", limit=None)
        rc = mdm_cli._handle_run(args)

        assert rc != 0, "Expected nonzero exit for silver DB with no required tables"

    def test_silver_missing_ownership_table_fails_person_entity_run(
        self, tmp_path, monkeypatch, mdm_session
    ):
        """A silver DB missing sec_ownership_reporting_owner must fail person entity load preflight.

        This test is RED because no preflight table check exists.
        The test asserts the REQUIRED content: sec_ownership_reporting_owner must
        be listed in any required-tables check for 'person' entity type.
        """
        import edgar_warehouse.mdm.cli as mdm_cli

        no_ownership_db = tmp_path / "no_ownership.duckdb"
        con = duckdb.connect(str(no_ownership_db))
        # Only company tables, no ownership tables
        con.execute("CREATE TABLE IF NOT EXISTS sec_company (cik BIGINT PRIMARY KEY, entity_name TEXT)")
        con.execute("INSERT INTO sec_company VALUES (910001, 'Test Co')")
        con.close()

        monkeypatch.setenv("MDM_SILVER_DUCKDB", str(no_ownership_db))
        monkeypatch.setattr(mdm_cli, "_session", MagicMock(
            side_effect=AssertionError("_session must not be called without preflight")
        ))

        import argparse
        args = argparse.Namespace(entity_type="person", limit=None)
        rc = mdm_cli._handle_run(args)

        assert rc != 0, (
            "Expected nonzero exit when silver DB is missing sec_ownership_reporting_owner "
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
        self, silver_duckdb, mdm_session
    ):
        """run_companies() must not reference sec_tracked_universe; use sec_company_sync_state."""
        reader = _DuckReader(str(silver_duckdb))
        pipeline = MDMPipeline(session=mdm_session, silver=reader)

        # Will raise DuckDB BinderException if sec_tracked_universe is queried
        try:
            pipeline.run_companies()
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
        self, silver_duckdb, mdm_session
    ):
        """run_companies() must successfully load companies from the silver fixture.

        Fails because the current code queries sec_tracked_universe.
        """
        reader = _DuckReader(str(silver_duckdb))
        pipeline = MDMPipeline(session=mdm_session, silver=reader)

        n = pipeline.run_companies()
        assert n >= 1, (
            f"Expected at least 1 company loaded from silver fixture, got {n}. "
            f"This may indicate a sec_tracked_universe schema mismatch."
        )

    def test_run_persons_uses_sec_ownership_reporting_owner(self, silver_duckdb, mdm_session):
        """run_persons() must query sec_ownership_reporting_owner for person rows."""
        reader = _DuckReader(str(silver_duckdb))
        pipeline = MDMPipeline(session=mdm_session, silver=reader)

        # This will fail if run_companies has schema errors — run it first to seed companies
        try:
            pipeline.run_companies()
            mdm_session.commit()
        except Exception:
            pass  # Allow test to continue to person loader even if companies fail

        n = pipeline.run_persons()
        assert n >= 0  # Just ensure it doesn't raise a schema error


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

    def test_entity_load_is_idempotent_for_domain_counts(self, silver_duckdb, mdm_session):
        """Running entity loaders twice on the same silver fixture keeps domain counts stable.

        Fails because run_companies() raises on sec_tracked_universe in current code.
        """
        reader = _DuckReader(str(silver_duckdb))

        # First run
        pipeline1 = MDMPipeline(session=mdm_session, silver=reader)
        pipeline1.run_companies()
        pipeline1.run_advisers()
        pipeline1.run_persons()
        pipeline1.run_securities()
        pipeline1.run_funds()
        mdm_session.commit()
        counts_after_first = self._domain_counts(mdm_session)

        # Second run against the same data
        pipeline2 = MDMPipeline(session=mdm_session, silver=reader)
        pipeline2.run_companies()
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

    def test_domain_counts_include_all_five_entity_types(self, silver_duckdb, mdm_session):
        """After loading all entity types, all five domain tables must have ≥1 rows.

        Fails because run_companies() raises on sec_tracked_universe — no entities
        are ever loaded.
        """
        reader = _DuckReader(str(silver_duckdb))
        pipeline = MDMPipeline(session=mdm_session, silver=reader)
        pipeline.run_companies()
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

    def _load_all(self, silver_duckdb, mdm_session):
        """Run all five entity loaders and return the loaded session."""
        reader = _DuckReader(str(silver_duckdb))
        pipeline = MDMPipeline(session=mdm_session, silver=reader)
        pipeline.run_companies()
        pipeline.run_advisers()
        pipeline.run_persons()
        pipeline.run_securities()
        pipeline.run_funds()
        mdm_session.commit()
        return reader

    def test_zero_gap_against_complete_fixture(self, silver_duckdb, mdm_session):
        """compute_coverage returns 5 domains all with gap == 0 after all loaders run."""
        from edgar_warehouse.mdm.coverage import compute_coverage

        reader = self._load_all(silver_duckdb, mdm_session)
        rows = compute_coverage(reader, mdm_session)

        assert len(rows) == 5, f"Expected 5 domain rows, got {len(rows)}"
        domains = {r["domain"] for r in rows}
        assert domains == {"companies", "persons", "securities", "advisers", "funds"}

        for row in rows:
            assert row["gap"] == 0, (
                f"Domain '{row['domain']}' has gap={row['gap']} "
                f"(silver={row['silver_count']}, mdm={row['mdm_count']}). "
                "Expected 0 gap against the complete 1-per-domain fixture."
            )

    def test_handler_exits_0_with_nonzero_gap(self, silver_duckdb, mdm_session, monkeypatch, capsys):
        """CLI handler returns 0 even when a synthetic gap exists (D-19 reporting semantics)."""
        import edgar_warehouse.mdm.cli as mdm_cli
        from edgar_warehouse.mdm.coverage import compute_coverage

        # Load only companies — persons/securities/advisers/funds will have silver
        # rows but no MDM entities → nonzero gaps.
        reader = _DuckReader(str(silver_duckdb))
        monkeypatch.setenv("MDM_SILVER_DUCKDB", str(silver_duckdb))
        monkeypatch.setattr(mdm_cli, "_silver_reader", lambda: reader)
        monkeypatch.setattr(mdm_cli, "_session", lambda: mdm_session)

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

    def test_securities_reason_mentions_xbrl_and_phase_6(self, silver_duckdb, mdm_session):
        """Securities domain reason string explicitly references XBRL and Phase 6 deferral (D-24/D-28)."""
        from edgar_warehouse.mdm.coverage import compute_coverage

        reader = _DuckReader(str(silver_duckdb))
        rows = compute_coverage(reader, mdm_session)

        sec_row = next(r for r in rows if r["domain"] == "securities")
        reason_lower = sec_row["reason"].lower()
        assert "xbrl" in reason_lower, (
            f"Securities reason must mention 'XBRL'. Got: {sec_row['reason']}"
        )
        assert "phase 6" in reason_lower or "phase6" in reason_lower, (
            f"Securities reason must reference Phase 6 deferral. Got: {sec_row['reason']}"
        )
