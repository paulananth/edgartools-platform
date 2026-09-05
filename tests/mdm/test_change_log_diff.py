"""Regression tests for the mdm_change_log write-side diff (fixed 2026-09-05).

Live production evidence found `mdm_change_log` had accumulated 584,338
rows with one single entity alone responsible for 40,356 of them.
Root cause: `BaseResolver._log_change` wrote a changelog row every time
survivorship ran for an entity, regardless of whether the winning value
actually differed from what was already stored -- and `SecurityResolver`
never even passed `existing_values` to `run_survivorship_for_entity` at
all, so every security was treated as brand-new on every touch.

This is a distinct scenario from the existing `test_run_*_skip_unchanged`
suites: those cover a SECOND run over the SAME source row (same
source_id), which short-circuits via `_skip_if_unchanged`'s content hash
before ever reaching survivorship again. The real production shape is
the opposite -- the SAME security is referenced by MANY DIFFERENT source
rows (separate ownership-transaction filings, each with its own
source_id), so `_skip_if_unchanged` never fires, and survivorship runs
fresh every time even though the resolved value never changes.
"""
from __future__ import annotations

from sqlalchemy import select

from edgar_warehouse.mdm.database import MdmChangeLog, MdmSecurity
from edgar_warehouse.mdm.pipeline import MDMPipeline

from tests.mdm.test_run_companies_concurrency import StubSilver, _seeded_sqlite_session
from tests.mdm.test_run_securities_persons_concurrency import _security_rows


class TestSecurityChangeLogDiff:
    def test_repeated_touches_with_unchanged_value_log_change_only_once(self) -> None:
        """Three separate ownership-transaction rows, same issuer/title --
        each has its own source_id (so none are caught by
        _skip_if_unchanged), but all resolve to the same entity with the
        same winning values. Before the fix, this produced 3 change_log
        rows for one entity that never actually changed; it must produce
        exactly 1.
        """
        session = _seeded_sqlite_session(static_pool=True)
        fixtures = _security_rows({111: ["Common Stock", "Common Stock", "Common Stock"]})
        pipeline = MDMPipeline(session=session, silver=StubSilver(fixtures))

        n = pipeline.run_securities()

        assert n == 3, "all 3 rows must reach resolve_one (none skipped by content hash)"
        securities = session.execute(select(MdmSecurity)).scalars().all()
        assert len(securities) == 1, "all 3 rows dedupe to one entity"

        change_log_rows = session.execute(
            select(MdmChangeLog).where(MdmChangeLog.entity_id == securities[0].entity_id)
        ).scalars().all()
        assert len(change_log_rows) == 1, (
            "the entity's resolved value never changed across the 3 touches -- "
            "exactly one change_log row, not one per touch"
        )

    def test_first_touch_of_a_brand_new_security_is_still_logged(self) -> None:
        """A brand-new entity has no prior golden record, so its first
        resolution must still be logged -- proves the fix doesn't
        over-suppress creation just because it reads `existing_golden`
        before any domain row exists.
        """
        session = _seeded_sqlite_session(static_pool=True)
        fixtures = _security_rows({111: ["Common Stock"], 222: ["Preferred Stock"]})
        pipeline = MDMPipeline(session=session, silver=StubSilver(fixtures))

        n = pipeline.run_securities()

        assert n == 2
        change_log_rows = session.execute(select(MdmChangeLog)).scalars().all()
        assert len(change_log_rows) == 2, "one change_log row per newly-created security"
