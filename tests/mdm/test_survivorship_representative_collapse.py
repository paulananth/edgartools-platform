"""Tests for stage_candidate()'s representative_cache collapsing
(mdm-run-throughput Ticket 05).

Root cause this closes: migration 012's natural key (entity_id,
source_system, source_id, field_name) never collapses genuinely distinct
source_ids -- real, separate transactions -- that all confirm the exact
same field_value. Confirmed live in production: one heavily-refiled
security had 5,048 mdm_entity_attribute_stage rows for one field, ALL
identical value, ALL one source_system, each from a distinct ownership
transaction. run_survivorship_for_entity()'s SELECT re-reads that entire,
ever-growing set every time the entity is touched (measured live:
611-619ms max execution time vs. 0.15-0.51ms mean).

_pick_by_rule (survivorship.py) only ever needs, per (entity_id,
field_name, source_system, global_priority, field_value) group, the single
member with that group's max effective_date (then max loaded_at as
tiebreak) -- every rule type's sort key reduces to exactly that within a
group where value and priority are held fixed. These tests prove:

  1. With a representative_cache, distinct source_ids sharing the same
     value collapse to one row instead of accumulating.
  2. Without a cache (the default), pre-Ticket-05 behavior is unchanged --
     no unintended round-trip or accumulation-behavior change for callers
     that haven't opted in (run_companies' per-row path).
  3. effective_date only ever advances forward, never regresses.
  4. loaded_at/source_id still refresh on a same-or-older-effective_date
     re-confirmation (a stale re-confirmation should still win recency
     tie-breaks against genuinely stale, un-reconfirmed alternatives).
  5. A cache hit costs zero SQL round trips -- the whole point of the
     fix, per this map's own "flat ~68-100ms round trip" cost model.
  6. A different (source_system, field_value, global_priority) group is
     never accidentally collapsed into an unrelated one.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import event, select

from edgar_warehouse.mdm.database import MdmEntityAttributeStage
from edgar_warehouse.mdm.rules import MDMRuleEngine
from edgar_warehouse.mdm.survivorship import stage_candidate

from tests.mdm.test_run_companies_concurrency import _seeded_sqlite_session

_ENTITY_TYPE = "security"
_SOURCE_SYSTEM = "ownership_filing"


def _all_stage_rows(session) -> list[MdmEntityAttributeStage]:
    return list(session.execute(select(MdmEntityAttributeStage)).scalars().all())


class TestRepresentativeCacheCollapse:
    def test_distinct_source_ids_same_value_collapse_with_cache(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        engine = MDMRuleEngine.load(session)
        cache: dict = {}

        for i in range(5):
            stage_candidate(
                session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
                f"acc-{i}:0:0", "canonical_title", "Class A Common Stock",
                representative_cache=cache,
            )
            session.commit()

        rows = _all_stage_rows(session)
        assert len(rows) == 1, (
            "5 distinct source_ids confirming the identical value must "
            f"collapse to one representative row, not accumulate ({len(rows)} found) -- "
            "matches the exact live production shape (5,048 rows, 1 distinct value)"
        )
        assert rows[0].field_value == "Class A Common Stock"
        assert rows[0].source_id == "acc-4:0:0", (
            "the representative must point at the most recently seen evidence"
        )

    def test_without_cache_distinct_source_ids_still_accumulate(self) -> None:
        """Baseline: representative_cache=None (the default) must preserve
        stage_candidate()'s exact pre-Ticket-05 behavior for any caller
        that hasn't opted in -- deliberately no collapsing, no extra
        round trip. This is what run_companies' per-row path still gets."""
        session = _seeded_sqlite_session(static_pool=True)
        engine = MDMRuleEngine.load(session)

        for i in range(5):
            stage_candidate(
                session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
                f"acc-{i}:0:0", "canonical_title", "Class A Common Stock",
            )
            session.commit()

        rows = _all_stage_rows(session)
        assert len(rows) == 5, (
            "opting out of the cache must leave stage_candidate()'s "
            "pre-Ticket-05 behavior completely unchanged"
        )

    def test_effective_date_only_advances_forward(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        engine = MDMRuleEngine.load(session)
        cache: dict = {}

        stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-1:0:0", "canonical_title", "Class A Common Stock",
            effective_date=date(2024, 6, 1),
            representative_cache=cache,
        )
        session.commit()

        # A late-arriving, OLDER-period filing re-confirming the same value
        # must not regress effective_date backward.
        stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-2:0:0", "canonical_title", "Class A Common Stock",
            effective_date=date(2024, 1, 1),
            representative_cache=cache,
        )
        session.commit()

        rows = _all_stage_rows(session)
        assert len(rows) == 1
        assert rows[0].effective_date == date(2024, 6, 1), (
            "an older-effective_date re-confirmation of the same value must "
            "never regress the group's max effective_date -- most_recent "
            "rule correctness depends on this"
        )

        # A genuinely newer filing must advance it.
        stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-3:0:0", "canonical_title", "Class A Common Stock",
            effective_date=date(2024, 9, 1),
            representative_cache=cache,
        )
        session.commit()

        rows = _all_stage_rows(session)
        assert len(rows) == 1
        assert rows[0].effective_date == date(2024, 9, 1)

    def test_loaded_at_and_source_id_refresh_even_without_effective_date_advance(
        self,
    ) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        engine = MDMRuleEngine.load(session)
        cache: dict = {}

        row = stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-1:0:0", "canonical_title", "Class A Common Stock",
            effective_date=date(2024, 6, 1),
            representative_cache=cache,
        )
        session.commit()
        first_loaded_at = row.loaded_at

        stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-2:0:0", "canonical_title", "Class A Common Stock",
            effective_date=date(2024, 1, 1),  # older, doesn't advance
            representative_cache=cache,
        )
        session.commit()

        rows = _all_stage_rows(session)
        assert len(rows) == 1
        assert rows[0].source_id == "acc-2:0:0", (
            "the evidence pointer must still advance to the latest "
            "confirmation even when effective_date doesn't"
        )
        assert rows[0].loaded_at.replace(tzinfo=None) >= first_loaded_at.replace(
            tzinfo=None
        ), "a re-confirmation must still refresh loaded_at for recency tie-breaks"

    def test_cache_hit_within_a_commit_interval_skips_the_value_lookup_and_the_insert(
        self,
    ) -> None:
        """A cache hit still pays the pre-existing exact-source_id-match
        SELECT (unavoidable -- it's what detects a literal restage of the
        same transaction, unrelated to this ticket) but must skip BOTH the
        second, value-based representative lookup AND the INSERT that used
        to happen on every distinct source_id. That's the fix's entire
        point: the map's own flat ~68-100ms round-trip cost applies per
        statement, and this path used to pay one INSERT per transaction
        for a value that never changes.

        Deliberately uses flush(), not commit(), between the two calls --
        matches _run_grouped_concurrent's real shape, where a group's rows
        share one uncommitted-until-commit_interval session (Ticket 04),
        not a commit after every single row. See the sibling test below for
        what happens once a periodic commit does land mid-group."""
        session = _seeded_sqlite_session(static_pool=True)
        engine = MDMRuleEngine.load(session)
        cache: dict = {}

        stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-1:0:0", "canonical_title", "Class A Common Stock",
            representative_cache=cache,
        )
        session.flush()

        statements: list[str] = []

        def _capture_statement(_conn, _cursor, statement, *_args, **_kwargs) -> None:
            statements.append(statement)

        bind = session.get_bind()
        event.listen(bind, "before_cursor_execute", _capture_statement)
        try:
            stage_candidate(
                session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
                "acc-2:0:0", "canonical_title", "Class A Common Stock",
                representative_cache=cache,
            )
            session.flush()
        finally:
            event.remove(bind, "before_cursor_execute", _capture_statement)

        assert len(statements) == 2, (
            "expected exactly the one unavoidable exact-source_id-match "
            "SELECT plus one UPDATE for the cached representative's "
            f"in-place mutation, got {len(statements)}: {statements}"
        )
        assert statements[0].strip().upper().startswith("SELECT"), statements
        assert statements[1].strip().upper().startswith("UPDATE"), statements
        assert "INSERT" not in " ".join(statements).upper(), (
            "a cache hit must never issue an INSERT -- that's the whole "
            "point of collapsing distinct source_ids into one representative"
        )
        where_clauses = [s.lower().split("where", 1)[-1] for s in statements]
        assert not any("field_value" in clause for clause in where_clauses), (
            "the second, value-based representative lookup (WHERE ... "
            "field_value = ...) must be fully skipped on a cache hit -- "
            f"got: {statements}"
        )

    def test_cache_hit_after_a_periodic_commit_pays_one_reload_select_not_more(
        self,
    ) -> None:
        """SQLAlchemy's default expire_on_commit=True means a cached ORM
        row's attributes expire after commit() -- the next touch triggers
        one reload SELECT-by-PK before mutating. Ticket 04's periodic
        worker_session.commit() (every commit_interval rows) means this
        happens roughly once per commit_interval per still-hot cached key,
        not once per row -- a real, bounded, acceptable cost, not a defeat
        of the fix (still ~1 extra SELECT per 1000 rows, vs. 1 INSERT per
        row before this ticket)."""
        session = _seeded_sqlite_session(static_pool=True)
        engine = MDMRuleEngine.load(session)
        cache: dict = {}

        stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-1:0:0", "canonical_title", "Class A Common Stock",
            representative_cache=cache,
        )
        session.commit()  # simulates a Ticket 04 commit_interval boundary

        statements: list[str] = []

        def _capture_statement(_conn, _cursor, statement, *_args, **_kwargs) -> None:
            statements.append(statement)

        bind = session.get_bind()
        event.listen(bind, "before_cursor_execute", _capture_statement)
        try:
            stage_candidate(
                session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
                "acc-2:0:0", "canonical_title", "Class A Common Stock",
                representative_cache=cache,
            )
            session.flush()
        finally:
            event.remove(bind, "before_cursor_execute", _capture_statement)

        assert "INSERT" not in " ".join(statements).upper(), (
            "a cache hit must never issue an INSERT even across a commit "
            "boundary -- that's the whole point of collapsing distinct "
            "source_ids into one representative"
        )
        rows = _all_stage_rows(session)
        assert len(rows) == 1, "still exactly one row after the reload + mutate"
        assert rows[0].source_id == "acc-2:0:0"

    def test_different_value_in_same_group_does_not_collapse(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        engine = MDMRuleEngine.load(session)
        cache: dict = {}

        stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-1:0:0", "canonical_title", "Class A Common Stock",
            representative_cache=cache,
        )
        session.commit()

        # A genuine correction -- must get its own row, not overwrite the
        # prior value's representative (which stays a distinct history
        # entry, not merged away).
        stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-2:0:0", "canonical_title", "Class B Common Stock",
            representative_cache=cache,
        )
        session.commit()

        rows = _all_stage_rows(session)
        assert len(rows) == 2, (
            "distinct values must never collapse into each other -- only "
            "repeated confirmations of the SAME value are redundant"
        )
        values = {r.field_value for r in rows}
        assert values == {"Class A Common Stock", "Class B Common Stock"}

    def test_restage_with_changed_value_does_not_leave_a_stale_cache_entry(self) -> None:
        """Regression found by the mandatory Standards code-review pass:
        restaging the SAME source_id with a DIFFERENT value (e.g. under
        reconciliation_pass, which bypasses _skip_if_unchanged and can
        reprocess a row already seen earlier in the same group) mutates
        the row via the exact-match branch, which never touches
        representative_cache -- if a cache entry for the row's OLD value
        still points at it, a later brand-new source_id confirming that
        OLD value would wrongly reuse (and further mutate) a row that no
        longer represents it, corrupting both rows' evidence."""
        session = _seeded_sqlite_session(static_pool=True)
        engine = MDMRuleEngine.load(session)
        cache: dict = {}

        # First confirmation of "Class A" -- populates the cache under the
        # "Class A" key, pointing at this row.
        row = stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-1:0:0", "canonical_title", "Class A Common Stock",
            representative_cache=cache,
        )
        session.flush()

        # The identical source_id restages with a DIFFERENT value -- hits
        # the exact-match branch, mutating the same row to "Class B".
        stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-1:0:0", "canonical_title", "Class B Common Stock",
            representative_cache=cache,
        )
        session.flush()

        # A genuinely new transaction confirms the ORIGINAL value again.
        stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-2:0:0", "canonical_title", "Class A Common Stock",
            representative_cache=cache,
        )
        session.commit()

        rows = _all_stage_rows(session)
        assert len(rows) == 2, (
            f"expected 2 rows (one per distinct current value), got {len(rows)}: "
            f"{[(r.source_id, r.field_value) for r in rows]}"
        )
        by_value = {r.field_value: r for r in rows}
        assert by_value["Class B Common Stock"].source_id == "acc-1:0:0", (
            "the restaged row must keep representing its new value"
        )
        assert by_value["Class A Common Stock"].source_id == "acc-2:0:0", (
            "the new confirmation of the original value must land on its "
            "own row, not get merged into the row that moved on to a "
            "different value under a stale cache key"
        )
        assert by_value["Class A Common Stock"].stage_id != row.stage_id, (
            "must be a genuinely different row, not the same object reused "
            "under the stale cache entry"
        )

    def test_different_entity_in_same_cache_does_not_collapse(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        engine = MDMRuleEngine.load(session)
        cache: dict = {}

        stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-1:0:0", "canonical_title", "Class A Common Stock",
            representative_cache=cache,
        )
        stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-2", _SOURCE_SYSTEM,
            "acc-2:0:0", "canonical_title", "Class A Common Stock",
            representative_cache=cache,
        )
        session.commit()

        rows = _all_stage_rows(session)
        assert len(rows) == 2, (
            "two different entities sharing an identical value (e.g. the "
            "same generic title on two different issuers' securities, "
            "possible under the shared-group-by-title design) must each "
            "keep their own representative row"
        )

    def test_cache_reuses_an_existing_db_row_on_first_miss(self) -> None:
        """A representative may already exist in the DB from a prior run
        (before this group's in-memory cache was ever built) -- the first
        cache miss must find and reuse it, not insert a duplicate."""
        session = _seeded_sqlite_session(static_pool=True)
        engine = MDMRuleEngine.load(session)

        # Simulates a prior run's write, with no cache in play.
        stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-1:0:0", "canonical_title", "Class A Common Stock",
        )
        session.commit()

        # This run builds a fresh, empty cache (per-group, as
        # _run_grouped_concurrent does) and sees the same value again from
        # a brand-new transaction.
        cache: dict = {}
        stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-2:0:0", "canonical_title", "Class A Common Stock",
            representative_cache=cache,
        )
        session.commit()

        rows = _all_stage_rows(session)
        assert len(rows) == 1, (
            "a fresh, empty per-group cache must still find and reuse an "
            "existing DB representative on its first miss, not insert a "
            "second row for the same value"
        )
        assert rows[0].source_id == "acc-2:0:0"

    def test_cache_miss_db_fallback_preserves_both_maxima_from_different_legacy_rows(
        self,
    ) -> None:
        """Regression for the exact bug the mandatory Standards/Spec
        code-review pass caught: an earlier design's cache-miss DB lookup
        was `ORDER BY effective_date DESC, loaded_at DESC LIMIT 1` -- a
        single lexicographic sort that could silently discard the group's
        true max-loaded_at legacy row (what immutable/highest_source_rank/
        source_priority need) just because a DIFFERENT legacy row had a
        higher effective_date. Reproduces a not-yet-backfilled group with
        exactly that divergence already sitting in the DB."""
        session = _seeded_sqlite_session(static_pool=True)
        engine = MDMRuleEngine.load(session)

        row_a = stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-high-eff-date", "canonical_title", "Class A Common Stock",
            effective_date=date(2024, 6, 1),
        )
        row_b = stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-high-loaded-at", "canonical_title", "Class A Common Stock",
            effective_date=date(2024, 1, 1),
        )
        session.commit()
        # Force row_b to be the true max-loaded_at row and row_a to be the
        # true max-effective_date row -- on different physical rows.
        # Explicit tz-aware literals for both (not derived from a
        # server-default NOW() re-fetch) sidestep SQLite's naive/aware
        # round-trip inconsistency for TIMESTAMP(timezone=True) columns --
        # a pre-existing, already-documented test-only quirk
        # (test_survivorship_stage_upsert.py has the same normalization).
        row_a.loaded_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        row_b.loaded_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
        session.commit()

        cache: dict = {}
        stage_candidate(
            session, engine, _ENTITY_TYPE, "entity-1", _SOURCE_SYSTEM,
            "acc-new", "canonical_title", "Class A Common Stock",
            representative_cache=cache,
        )
        session.commit()

        rows = _all_stage_rows(session)
        assert len(rows) == 2, (
            "the cache-miss fallback must not delete legacy duplicates -- "
            "that's the backfill CLI's job, not stage_candidate()'s"
        )
        survivor = next(r for r in rows if r.source_id == "acc-new")
        assert survivor.effective_date == date(2024, 6, 1), (
            "the true max effective_date (from row_a) must be preserved "
            "on whichever row absorbs the next confirmation"
        )
