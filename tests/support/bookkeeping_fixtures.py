"""Shared BookkeepingStore test fixture.

DuckDB Retirement Cutover Ticket 14: many pre-existing end-to-end tests call
``warehouse_orchestrator._execute_warehouse``/``_execute_warehouse_bronze_capture``
directly. Both now unconditionally construct a real ``BookkeepingStore`` (via
``_bookkeeping_store()``), which needs ``BOOKKEEPING_DATABASE_URL`` -- not set in
the test environment. Tests that don't care about bookkeeping's own persisted
state (checkpoints, tracking status, etc.) can patch ``_bookkeeping_store`` to
return this in-memory SQLite-backed store instead of a real Postgres one.
"""

from __future__ import annotations

from edgar_warehouse.bookkeeping.store import BookkeepingStore


def bookkeeping_fixture() -> BookkeepingStore:
    """Build a fresh in-memory SQLite-backed BookkeepingStore for tests."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from edgar_warehouse.bookkeeping.database import Base as BookkeepingBase

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    BookkeepingBase.metadata.create_all(engine)
    return BookkeepingStore(Session(engine))
