"""Direct, function-level tests for edgar_warehouse/mdm/relationship_checkpoint.py.

Covers a real bug found by this repo's 3-axis /code-review (Spec axis) on
the mdm-relationship-versioning-gap Ticket 01 diff, at the function level
rather than only through the slower pipeline-level tests in
test_pipeline_relationships.py: advance_relationship_watermark's upsert
guard used a bare `watermark_value < excluded.watermark_value` comparison,
which -- per SQL's three-valued logic -- evaluates to NULL (never TRUE)
whenever the existing row's watermark_value is already NULL. Since
record_relationship_sweep_progress explicitly writes a NULL watermark_value
for every multi-call sweep's first partial batch, this meant
complete_relationship_sweep could never actually advance the watermark for
any sweep that had gone through at least one prior partial-progress write --
exactly the scenario Ticket 01 exists to fix. Reproduced against unfixed
code before the fix landed; confirmed fixed here.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.mdm.database import Base
from edgar_warehouse.mdm.relationship_checkpoint import (
    advance_relationship_watermark,
    complete_relationship_sweep,
    get_relationship_checkpoint_state,
    record_relationship_sweep_progress,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sess = Session(engine)
    yield sess
    sess.close()


class TestAdvanceRelationshipWatermarkNullGuard:
    """advance_relationship_watermark must be able to advance a checkpoint
    row whose existing watermark_value is NULL -- the state every
    multi-call sweep passes through before completing."""

    def test_advances_past_an_existing_null_watermark_value(self, session):
        # Simulate the row a partial sweep would have already created --
        # record_relationship_sweep_progress explicitly writes
        # watermark_value=None for the first partial call.
        record_relationship_sweep_progress(
            session, "TEST_TYPE", rel_type_name="TEST_TYPE",
            watermark_column="ingested_at", cursor_value="910004",
            pending_watermark_value=None,
        )
        session.commit()
        assert get_relationship_checkpoint_state(session, "TEST_TYPE").watermark_value is None

        advance_relationship_watermark(
            session, "TEST_TYPE", rel_type_name="TEST_TYPE",
            watermark_column="ingested_at",
            watermark_value="2024-06-01T00:00:00+00:00",
        )
        session.commit()
        state = get_relationship_checkpoint_state(session, "TEST_TYPE")
        assert state.watermark_value == "2024-06-01T00:00:00+00:00", (
            "watermark_value must advance past an existing NULL, not stay stuck forever"
        )

    def test_still_never_regresses_a_real_existing_value(self, session):
        """Regression guard for the ORIGINAL monotonic-advance contract --
        proves the NULL-handling fix didn't loosen the existing "never
        regress a real value" guarantee."""
        advance_relationship_watermark(
            session, "TEST_TYPE", rel_type_name="TEST_TYPE",
            watermark_column="ingested_at",
            watermark_value="2024-06-01T00:00:00+00:00",
        )
        session.commit()

        advance_relationship_watermark(
            session, "TEST_TYPE", rel_type_name="TEST_TYPE",
            watermark_column="ingested_at",
            watermark_value="2024-01-01T00:00:00+00:00",  # earlier -- must not regress
        )
        session.commit()
        state = get_relationship_checkpoint_state(session, "TEST_TYPE")
        assert state.watermark_value == "2024-06-01T00:00:00+00:00"


class TestCompleteRelationshipSweepAdvancesPastPartialProgress:
    """End-to-end (still function-level, not pipeline-level) proof that a
    sweep spanning a partial call followed by a completing call ends with
    a real, advanced watermark_value -- the exact shape Ticket 01's own
    cursor mechanism produces on every multi-call sweep."""

    def test_watermark_advances_after_a_partial_then_complete_sweep(self, session):
        record_relationship_sweep_progress(
            session, "INSTITUTIONAL_HOLDS", rel_type_name="INSTITUTIONAL_HOLDS",
            watermark_column="ingested_at", cursor_value="910004",
            pending_watermark_value="2024-03-01T00:00:00+00:00",
        )
        session.commit()

        complete_relationship_sweep(
            session, "INSTITUTIONAL_HOLDS", rel_type_name="INSTITUTIONAL_HOLDS",
            watermark_column="ingested_at",
            watermark_value="2024-06-01T00:00:00+00:00",
        )
        session.commit()

        state = get_relationship_checkpoint_state(session, "INSTITUTIONAL_HOLDS")
        assert state.watermark_value == "2024-06-01T00:00:00+00:00"
        assert state.cursor_value is None
        assert state.pending_watermark_value is None
