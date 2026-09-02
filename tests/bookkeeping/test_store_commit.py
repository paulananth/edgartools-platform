"""Regression coverage for BookkeepingStore.commit (2026-09-01 durability bug).

Confirmed live in prod: BookkeepingStore's Session never auto-commits, so
every write made through it (checkpoints, sync-run/pipeline-run records,
etc.) was silently rolled back when the owning ECS task process exited --
a checkpoint logged as "status: succeeded" was unreadable by both a
separate task and a fresh rerun of the same command minutes later.

These tests reproduce that shape by closing the writing Session (mirroring
process exit) before checking visibility from a second, independent
Session against the same underlying connection -- the same fixtures
tests/bookkeeping/conftest.py already provides. Note: an in-memory SQLite
engine with StaticPool multiplexes every Session over one shared physical
connection, so a *second, still-open* Session sees an *uncommitted* write
from a first, still-open Session (unlike real Postgres's per-session
transaction isolation) -- that shared-connection quirk is not what these
tests check. What both this fixture and real Postgres agree on, and what
actually reproduces the prod bug, is that closing the writing session
without an explicit commit rolls the write back.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from edgar_warehouse.bookkeeping.store import BookkeepingStore


class TestCommitDurability:
    def test_without_commit_the_write_is_lost_when_the_session_closes(
        self, store: BookkeepingStore, session: Session
    ) -> None:
        """Reproduces the live bug: a process that writes and exits without
        committing loses the write, even though the call site never saw an
        error and the write was readable through this same session."""
        store.upsert_source_checkpoint(
            {"source_name": "s", "source_key": "k", "raw_object_id": "first"}
        )
        assert store.get_source_checkpoint("s", "k") is not None

        engine = session.get_bind()
        session.close()

        with Session(engine) as later_session:
            later_store = BookkeepingStore(later_session)
            assert later_store.get_source_checkpoint("s", "k") is None

    def test_commit_survives_the_original_session_closing(
        self, store: BookkeepingStore, session: Session
    ) -> None:
        """Mirrors the real fix: the process commits, then exits (closing its
        session), and a later, unrelated process must still see the write."""
        store.upsert_source_checkpoint(
            {"source_name": "s", "source_key": "k", "raw_object_id": "first"}
        )
        store.commit()

        engine = session.get_bind()
        session.close()

        with Session(engine) as later_session:
            later_store = BookkeepingStore(later_session)
            row = later_store.get_source_checkpoint("s", "k")
            assert row is not None
            assert row["raw_object_id"] == "first"
