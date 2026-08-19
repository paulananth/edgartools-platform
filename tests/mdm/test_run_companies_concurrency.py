"""Tests for MDMPipeline.run_companies()'s bounded-concurrency resolution path.

run_companies() previously resolved companies one at a time on a single
SQLAlchemy session, each row paying a ~68ms network round trip against MDM's
Postgres store (measured live, prod, pipeline-throughput-architecture map's
MDM addendum) -- ~37 hours projected for a 62,190-row universe. It now
resolves each row on its own worker thread and session, bounded by
MDM_COMPANY_RESOLVE_CONCURRENCY (default 8), falling back to a single worker
whenever the bound SQLAlchemy engine is SQLite (real production is always
Postgres; SQLite's StaticPool test fixture shares one physical connection
across all sessions and cannot run simultaneous transactions on it -- see
pipeline.py's dialect check).

These tests cover:
  1. _first_per_key, the new bulk ticker/tracking prefetch helper.
  2. run_companies() end-to-end against the StaticPool SQLite fixture (the
     dialect guard forces this through sequentially -- proves the new code
     path is behaviorally identical to the old one).
  3. Genuine concurrent-write safety: multiple threads, each with its own
     session against a real multi-connection (file-based) SQLite engine,
     independently resolving distinct CIKs -- the actual safety property the
     production Postgres path depends on.
  4. Idempotency: re-running against already-resolved CIKs reuses existing
     entities rather than duplicating them (CIK-exact rematch).
  5. Partial-failure propagation: a raising resolve_one must not be silently
     swallowed.
"""
from __future__ import annotations

import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.mdm.database import Base, MdmCompany, MdmEntity, get_session
from edgar_warehouse.mdm.migrations.runtime import seed_defaults
from edgar_warehouse.mdm.pipeline import MDMPipeline, _first_per_key
from edgar_warehouse.mdm.resolvers import CompanyResolver
from edgar_warehouse.mdm.resolvers.base import ResolverContext
from edgar_warehouse.mdm.rules import MDMRuleEngine


class StubSilver:
    """Returns canned rows keyed by a substring of the SQL."""

    def __init__(self, fixtures: dict[str, list[dict]]):
        self._fixtures = fixtures

    def fetch(self, sql: str, params: Optional[list[Any]] = None) -> list[dict]:
        matched: list[dict] = []
        for needle, rows in self._fixtures.items():
            if needle in sql:
                matched.extend(rows)
        return matched


def _companies_fixture(n: int) -> dict[str, list[dict]]:
    companies = [
        {"cik": 900000 + i, "entity_name": f"Company {i}", "ein": None, "sic": None,
         "sic_description": None, "state_of_incorporation": None, "fiscal_year_end": None}
        for i in range(n)
    ]
    return {
        "FROM sec_company": companies,
        "FROM sec_company_ticker": [],
        "FROM sec_company_sync_state": [],
    }


def _seeded_sqlite_session(*, static_pool: bool) -> Session:
    if static_pool:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        # Real file, default pooling -- distinct connections per session,
        # same as a real multi-connection backend (Postgres in production).
        db_path = Path(tempfile.mkstemp(suffix=".db")[1])
        engine = create_engine(f"sqlite:///{db_path}")

    from datetime import datetime, timezone

    @event.listens_for(engine, "connect")
    def _register_now(dbapi_conn, _record):
        dbapi_conn.create_function("NOW", 0, lambda: datetime.now(timezone.utc).isoformat())

    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_defaults(session)
    session.commit()
    return session


# ---------------------------------------------------------------------------
# 1. _first_per_key
# ---------------------------------------------------------------------------

class TestFirstPerKey:
    def test_keeps_first_occurrence_per_key(self):
        rows = [
            {"cik": 1, "ticker": "AAA"},
            {"cik": 2, "ticker": "BBB"},
            {"cik": 1, "ticker": "AAA-STALE"},
        ]
        out = _first_per_key(rows, "cik")
        assert out[1]["ticker"] == "AAA"
        assert out[2]["ticker"] == "BBB"
        assert len(out) == 2

    def test_empty_rows(self):
        assert _first_per_key([], "cik") == {}


# ---------------------------------------------------------------------------
# 2. run_companies() end-to-end, StaticPool sqlite (dialect guard -> 1 worker)
# ---------------------------------------------------------------------------

class TestRunCompaniesSequentialFallback:
    def test_resolves_all_companies_correctly_under_sqlite_guard(self):
        session = _seeded_sqlite_session(static_pool=True)
        silver = StubSilver(_companies_fixture(12))
        pipeline = MDMPipeline(session=session, silver=silver)

        processed = pipeline.run_companies()

        assert processed == 12
        rows = session.execute(select(MdmCompany)).scalars().all()
        assert {r.cik for r in rows} == {900000 + i for i in range(12)}
        assert len({r.entity_id for r in rows}) == 12  # every company got a distinct entity


# ---------------------------------------------------------------------------
# 2b. sec_company_sync_state degrades gracefully when the table is absent
#     (silver-snowflake-migration map, Ticket 12: no EDGARTOOLS_SILVER
#     analog under MDM_SILVER_READ_TARGET=snowflake) -- and logs the same
#     structured mdm_relationship_skip event every other graceful-degrade
#     path in pipeline.py already emits.
# ---------------------------------------------------------------------------

class TestRunCompaniesMissingSyncState:
    def test_missing_sync_state_table_is_skipped_and_logged(self, capsys):
        session = _seeded_sqlite_session(static_pool=True)
        fixtures = _companies_fixture(3)
        del fixtures["FROM sec_company_sync_state"]

        class _RaisingSilver(StubSilver):
            def fetch(self, sql, params=None):
                if "sec_company_sync_state" in sql:
                    raise Exception(
                        "Catalog Error: Table with name sec_company_sync_state does not exist!"
                    )
                return super().fetch(sql, params)

        silver = _RaisingSilver(fixtures)
        pipeline = MDMPipeline(session=session, silver=silver)

        processed = pipeline.run_companies()

        assert processed == 3  # tracking data missing, resolution still proceeds
        stderr_lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
        assert len(stderr_lines) == 1
        import json as _json
        event = _json.loads(stderr_lines[0])
        assert event["event"] == "mdm_relationship_skip"
        assert event["reason"] == "missing_source_table"
        assert event["source_table"] == "sec_company_sync_state"

    def test_a_genuine_non_missing_table_error_still_raises(self):
        session = _seeded_sqlite_session(static_pool=True)
        fixtures = _companies_fixture(1)

        class _RaisingSilver(StubSilver):
            def fetch(self, sql, params=None):
                if "sec_company_sync_state" in sql:
                    raise Exception("connection reset by peer")
                return super().fetch(sql, params)

        silver = _RaisingSilver(fixtures)
        pipeline = MDMPipeline(session=session, silver=silver)

        with pytest.raises(Exception, match="connection reset by peer"):
            pipeline.run_companies()


# ---------------------------------------------------------------------------
# 3. Genuine concurrent-write safety (real multi-connection sqlite)
# ---------------------------------------------------------------------------

class TestConcurrentCompanyResolutionSafety:
    def test_concurrent_workers_create_no_duplicates_or_deadlocks(self):
        """The actual safety property production concurrency depends on:
        CompanyResolver._existing_candidates scopes to the row's own CIK, so
        concurrent workers resolving distinct CIKs never share mutable match
        state. Exercised directly against a real multi-connection engine
        (not the StaticPool test fixture, which run_companies() itself
        deliberately avoids concurrency against) to prove worker sessions
        genuinely don't collide.
        """
        session = _seeded_sqlite_session(static_pool=False)
        engine_bind = session.get_bind()
        rule_engine = MDMRuleEngine.load(session)
        session.commit()

        n = 20
        ciks = [800000 + i for i in range(n)]

        def _resolve(cik: int) -> None:
            worker_session = get_session(engine_bind)
            try:
                ctx = ResolverContext(session=worker_session, engine=rule_engine, silver=None, run_id="test")
                resolver = CompanyResolver()
                resolver.resolve_one(
                    ctx, "edgar_cik", {"cik": cik, "entity_name": f"Company {cik}"}, None, None
                )
                worker_session.commit()
            finally:
                worker_session.close()

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(_resolve, ciks))

        verify_session = Session(engine_bind)
        rows = verify_session.execute(select(MdmCompany)).scalars().all()
        assert {r.cik for r in rows} == set(ciks)
        assert len({r.entity_id for r in rows}) == n, "expected no duplicate entities"
        verify_session.close()


# ---------------------------------------------------------------------------
# 4. Idempotency: re-run reuses existing entities, doesn't duplicate
# ---------------------------------------------------------------------------

class TestRunCompaniesIdempotency:
    def test_second_run_reuses_existing_entity_ids(self):
        session = _seeded_sqlite_session(static_pool=True)
        silver = StubSilver(_companies_fixture(5))
        pipeline = MDMPipeline(session=session, silver=silver)

        pipeline.run_companies()
        first_ids = {
            r.cik: r.entity_id for r in session.execute(select(MdmCompany)).scalars().all()
        }

        pipeline.run_companies()
        second_ids = {
            r.cik: r.entity_id for r in session.execute(select(MdmCompany)).scalars().all()
        }

        assert first_ids == second_ids, "re-run must reuse entity_ids via CIK-exact rematch, not duplicate"
        rows = session.execute(select(MdmCompany)).scalars().all()
        assert len(rows) == 5


# ---------------------------------------------------------------------------
# 5. Partial-failure propagation
# ---------------------------------------------------------------------------

class TestRunCompaniesPartialFailure:
    def test_a_raising_row_propagates_not_swallowed(self):
        session = _seeded_sqlite_session(static_pool=True)
        silver = StubSilver(_companies_fixture(3))
        pipeline = MDMPipeline(session=session, silver=silver)

        with patch(
            "edgar_warehouse.mdm.pipeline.CompanyResolver.resolve_one",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(RuntimeError, match="boom"):
                pipeline.run_companies()
