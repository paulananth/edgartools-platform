"""Tests for stage_candidate()'s upsert-on-natural-key fix (2026-08-21,
investigate-and-fix-stage-bloat).

Root cause this closes: stage_candidate() (edgar_warehouse/mdm/
survivorship.py) previously INSERTed a fresh mdm_entity_attribute_stage row
unconditionally on every call, with no dedup on (entity_id, source_system,
source_id, field_name) and no DB-level constraint preventing it. Confirmed
live in production: a heavily-refiled security's stage history reached
10,713-14,785+ rows from ~6 restarts of run_securities() before the
skip-if-unchanged fast path (mdm-resolver-skip-unchanged map) existed to
stop it. That fix only closes the gap for resolvers with a skip-if-
unchanged check; this fix closes it structurally, at the call site
everything shares (_stage_attrs -> stage_candidate) and at the DB level
(a new UNIQUE constraint on the natural key, mirroring MdmSourceRef's own
primary key for the same (entity_id, source_system, source_id) grouping).

These tests cover:
  1. A fresh natural key still inserts a new row (baseline, no regression).
  2. Restaging the same natural key upserts in place -- exactly one row,
     not two -- even when the field_value differs (a genuine correction,
     not just a pure restart-duplicate).
  3. The upsert resets was_selected to False and bumps loaded_at, so a
     stale "was the winner" flag from before the value changed doesn't
     survive, and recency-based survivorship rules see the new value as
     the most current.
  4. The new DB-level UNIQUE constraint is real, not just conventionally
     honored by stage_candidate() -- a raw duplicate INSERT that bypasses
     stage_candidate() entirely still fails.
  5. End-to-end: calling stage_candidate() N times for the identical
     source row (the exact restart-without-skip-if-unchanged shape that
     caused the production bloat) leaves exactly one row, not N.
"""
from __future__ import annotations

import time

from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from edgar_warehouse.mdm.database import MdmEntityAttributeStage
from edgar_warehouse.mdm.rules import MDMRuleEngine
from edgar_warehouse.mdm.survivorship import stage_candidate

from tests.mdm.test_run_companies_concurrency import _seeded_sqlite_session

_ENTITY_TYPE = "security"
_SOURCE_SYSTEM = "ownership_filing"


def _all_stage_rows(session) -> list[MdmEntityAttributeStage]:
    return list(session.execute(select(MdmEntityAttributeStage)).scalars().all())


class TestStageCandidateUpsert:
    def test_fresh_natural_key_inserts_a_new_row(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        engine = MDMRuleEngine.load(session)

        stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-1:0:0", "canonical_title", "Common Stock",
        )
        session.commit()

        rows = _all_stage_rows(session)
        assert len(rows) == 1
        assert rows[0].field_value == "Common Stock"

    def test_restaging_same_natural_key_upserts_in_place(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        engine = MDMRuleEngine.load(session)

        stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-1:0:0", "canonical_title", "Common Stock",
        )
        session.commit()

        # A genuine correction (different value), not just a pure
        # restart-duplicate of the identical value -- the fix must handle
        # both the same way, since it's the same underlying source_id.
        stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-1:0:0", "canonical_title", "Common Stock Corrected",
        )
        session.commit()

        rows = _all_stage_rows(session)
        assert len(rows) == 1, (
            "restaging the same (entity_id, source_system, source_id, "
            "field_name) must upsert, not accumulate a second row -- this "
            "is the exact production bug: unbounded duplicate growth "
            "across repeated restaging of the same source row"
        )
        assert rows[0].field_value == "Common Stock Corrected"

    def test_upsert_resets_was_selected_and_bumps_loaded_at(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        engine = MDMRuleEngine.load(session)

        row = stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-1:0:0", "canonical_title", "Common Stock",
        )
        session.commit()
        row.was_selected = True
        session.commit()
        first_loaded_at = row.loaded_at

        time.sleep(0.01)
        stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-1:0:0", "canonical_title", "Common Stock Corrected",
        )
        session.commit()

        rows = _all_stage_rows(session)
        assert len(rows) == 1
        assert rows[0].was_selected is False, (
            "a stale was_selected=True from before the value changed must "
            "not survive an upsert that changes the value"
        )
        assert rows[0].loaded_at is not None
        assert first_loaded_at is not None
        # SQLite's server-side NOW() (the INSERT-time default) and the
        # explicit datetime.now(timezone.utc) stage_candidate() sets on
        # UPDATE round-trip through SQLite with different tzinfo
        # awareness -- normalize both to naive for a portable comparison;
        # the DB-level default/UPDATE behavior itself is what's under
        # test, not tzinfo handling.
        assert rows[0].loaded_at.replace(tzinfo=None) > first_loaded_at.replace(tzinfo=None), (
            "loaded_at must advance on upsert so recency-based "
            "survivorship rules see this as the current value"
        )

    def test_duplicate_natural_key_insert_bypassing_stage_candidate_fails(self) -> None:
        """Proves the UNIQUE constraint is a real DB-level guarantee, not
        just a convention stage_candidate() happens to follow -- any future
        write path that constructs MdmEntityAttributeStage rows directly
        (bypassing stage_candidate() entirely) cannot silently reintroduce
        the bloat bug either."""
        session = _seeded_sqlite_session(static_pool=True)

        session.add(MdmEntityAttributeStage(
            entity_id="entity-1", source_system=_SOURCE_SYSTEM,
            source_id="acc-1:0:0", field_name="canonical_title",
            field_value="Common Stock", global_priority=1,
        ))
        session.commit()

        session.add(MdmEntityAttributeStage(
            entity_id="entity-1", source_system=_SOURCE_SYSTEM,
            source_id="acc-1:0:0", field_name="canonical_title",
            field_value="Common Stock", global_priority=1,
        ))
        try:
            session.commit()
            assert False, "expected IntegrityError from the unique constraint"
        except IntegrityError:
            session.rollback()

    def test_repeated_restage_of_the_same_source_row_leaves_exactly_one_row(self) -> None:
        """End-to-end reproduction of the production bug shape: a resolver
        loop restarted N times before a skip-if-unchanged check existed,
        restaging the identical source row every time. Directly calling
        stage_candidate() N times (bypassing any resolver-level skip check)
        proves the fix holds structurally, not just for resolvers that
        happen to check first."""
        session = _seeded_sqlite_session(static_pool=True)
        engine = MDMRuleEngine.load(session)

        for _ in range(6):
            stage_candidate(
                session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
                "acc-1:0:0", "canonical_title", "Common Stock",
            )
            session.commit()

        rows = _all_stage_rows(session)
        assert len(rows) == 1, (
            f"6 restages of the identical source row produced {len(rows)} "
            "stage rows -- matches the exact live production shape "
            "(10,713-14,785+ duplicate rows from ~6 pre-fix restarts)"
        )
