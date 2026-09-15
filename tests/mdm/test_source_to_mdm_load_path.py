"""MDM silver preflight and source-to-entity load path (Phase 5 Plan 01,
decisions D-11/D-12, PIPE-01..03, T-05-01/02).

The preflight, protocol-allowlist and required-table checks are covered
here with stub readers. The end-to-end load-path tests that ran
MDMPipeline against a DuckDB silver fixture (run_companies/persons/
securities against the real schema, idempotent domain counts, the coverage
report against a complete fixture) went with the DuckDB engine
(silver-merge-engine-migration Ticket 17): MDM reads EDGARTOOLS_SILVER, and
no local engine runs its SQL.
"""
from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.mdm.database import (
    Base,
)
from edgar_warehouse.mdm.migrations.runtime import seed_defaults


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
# D-11: a legacy s3:// MDM_SILVER_DUCKDB is ignored post-cutover
# ---------------------------------------------------------------------------

class TestLegacyS3SilverDuckdbIsIgnored:
    """D-11 / PIPE-01, post-cutover: a legacy s3:// MDM_SILVER_DUCKDB value is
    ignored by mdm mastering. The DuckDB reader that localized it via
    object_storage.read_bytes() was deleted with the parity commands
    (silver-merge-engine-migration Ticket 08).
    """

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


class TestCoverageReport:
    """mdm coverage-report CLI surface."""

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
