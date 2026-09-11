"""Tests for mdm-run-throughput Ticket 05's already-accumulated
mdm_entity_attribute_stage backfill (attribute_stage_backfill.py).

Covers: collapsing a redundant group down to its Pareto-maximal member
(max effective_date, then max loaded_at), leaving single-row and genuinely
distinct-value groups untouched, migrating a lost was_selected flag onto
the retained representative, dry-run not mutating, and run_backfill's
batching/pagination.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select

from edgar_warehouse.mdm.attribute_stage_backfill import (
    collapse_entity,
    find_collapsible_entity_ids,
    run_backfill,
)
from edgar_warehouse.mdm.database import MdmEntityAttributeStage

from tests.mdm.test_run_companies_concurrency import _seeded_sqlite_session

_SOURCE_SYSTEM = "ownership_filing"


def _add_row(
    session,
    *,
    entity_id: str,
    field_name: str = "canonical_title",
    field_value: str = "Class A Common Stock",
    priority: int = 1,
    effective_date=None,
    loaded_at=None,
    was_selected: bool = False,
    source_id: str,
) -> MdmEntityAttributeStage:
    row = MdmEntityAttributeStage(
        entity_id=entity_id,
        source_system=_SOURCE_SYSTEM,
        source_id=source_id,
        field_name=field_name,
        field_value=field_value,
        global_priority=priority,
        effective_date=effective_date,
        was_selected=was_selected,
    )
    session.add(row)
    session.flush()
    if loaded_at is not None:
        row.loaded_at = loaded_at
    return row


def _all_rows(session) -> list[MdmEntityAttributeStage]:
    return list(session.execute(select(MdmEntityAttributeStage)).scalars().all())


class TestCollapseEntity:
    def test_keeps_most_recently_loaded_row_topped_up_with_true_max_effective_date(
        self,
    ) -> None:
        """The survivor is chosen by max loaded_at (needed by 3 of the 4
        survivorship rule types -- immutable/highest_source_rank/
        source_priority all sort purely on (priority, loaded_at), never
        effective_date), then its effective_date is topped up to the
        group's true max (needed by the 4th, most_recent) even when that
        max lived on a DIFFERENT, now-deleted row. Without loaded_at
        overrides, insertion order determines loaded_at order here (later
        _add_row calls load later) -- s3 is inserted last, so it is the
        max-loaded_at survivor despite s2 having the higher effective_date."""
        session = _seeded_sqlite_session(static_pool=True)
        _add_row(session, entity_id="e1", source_id="s1", effective_date=date(2024, 1, 1))
        _add_row(session, entity_id="e1", source_id="s2", effective_date=date(2024, 6, 1))
        _add_row(session, entity_id="e1", source_id="s3", effective_date=date(2024, 3, 1))
        session.commit()

        summary = collapse_entity(session, "e1")
        session.commit()

        assert summary.groups_collapsed == 1
        assert summary.rows_deleted == 2
        rows = _all_rows(session)
        assert len(rows) == 1
        assert rows[0].source_id == "s3", (
            "survivor must be the most-recently-loaded row, not the one "
            "with the highest effective_date"
        )
        assert rows[0].effective_date == date(2024, 6, 1), (
            "effective_date must still be topped up to the group's true "
            "max even though that max came from a different, deleted row"
        )

    def test_max_effective_date_and_max_loaded_at_on_different_rows_both_preserved(
        self,
    ) -> None:
        """The exact bug the mandatory Standards/Spec code-review pass
        caught: an earlier design sorted by (max effective_date, then max
        loaded_at as tiebreak) and would have picked the OLDER-loaded row
        here just because it had the higher effective_date -- silently
        losing the group's true max loaded_at (what immutable/
        highest_source_rank/source_priority actually need) forever."""
        session = _seeded_sqlite_session(static_pool=True)
        stale_loaded = datetime(2026, 1, 1, tzinfo=timezone.utc)
        fresh_loaded = datetime(2026, 9, 1, tzinfo=timezone.utc)
        # Higher effective_date, but loaded (touched) long ago.
        _add_row(
            session, entity_id="e1", source_id="s_high_eff_date",
            effective_date=date(2024, 6, 1), loaded_at=stale_loaded,
        )
        # Lower effective_date (a late-arriving restatement for an older
        # period), but genuinely the most recently reconfirmed evidence.
        _add_row(
            session, entity_id="e1", source_id="s_high_loaded_at",
            effective_date=date(2024, 1, 1), loaded_at=fresh_loaded,
        )
        session.commit()

        collapse_entity(session, "e1")
        session.commit()

        rows = _all_rows(session)
        assert len(rows) == 1
        assert rows[0].source_id == "s_high_loaded_at", (
            "the survivor must be the true max-loaded_at row -- the one "
            "immutable/highest_source_rank/source_priority need -- not "
            "the one with the higher effective_date"
        )
        assert rows[0].effective_date == date(2024, 6, 1), (
            "but the group's true max effective_date (needed by "
            "most_recent) must still be preserved on the survivor, even "
            "though it originally lived on the now-deleted other row"
        )

    def test_ties_on_effective_date_break_on_loaded_at(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        older = datetime(2026, 1, 1, tzinfo=timezone.utc)
        newer = datetime(2026, 6, 1, tzinfo=timezone.utc)
        _add_row(
            session, entity_id="e1", source_id="s1",
            effective_date=date(2024, 1, 1), loaded_at=older,
        )
        _add_row(
            session, entity_id="e1", source_id="s2",
            effective_date=date(2024, 1, 1), loaded_at=newer,
        )
        session.commit()

        collapse_entity(session, "e1")
        session.commit()

        rows = _all_rows(session)
        assert len(rows) == 1
        assert rows[0].source_id == "s2"

    def test_null_effective_date_sorts_after_any_real_date(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        _add_row(session, entity_id="e1", source_id="s1", effective_date=None)
        _add_row(session, entity_id="e1", source_id="s2", effective_date=date(2020, 1, 1))
        session.commit()

        collapse_entity(session, "e1")
        session.commit()

        rows = _all_rows(session)
        assert len(rows) == 1
        assert rows[0].effective_date == date(2020, 1, 1), (
            "a row with a real effective_date must survive over one with none, "
            "matching _pick_by_rule's most_recent sort (missing date sorts last)"
        )

    def test_single_row_group_is_untouched(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        _add_row(session, entity_id="e1", source_id="s1")
        session.commit()

        summary = collapse_entity(session, "e1")
        session.commit()

        assert summary.groups_collapsed == 0
        assert summary.rows_deleted == 0
        assert len(_all_rows(session)) == 1

    def test_distinct_values_are_never_collapsed_into_each_other(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        _add_row(session, entity_id="e1", source_id="s1", field_value="Class A Common Stock")
        _add_row(session, entity_id="e1", source_id="s2", field_value="Class B Common Stock")
        session.commit()

        summary = collapse_entity(session, "e1")
        session.commit()

        assert summary.groups_collapsed == 0
        rows = _all_rows(session)
        assert len(rows) == 2
        assert {r.field_value for r in rows} == {
            "Class A Common Stock", "Class B Common Stock",
        }

    def test_different_field_names_are_never_collapsed_into_each_other(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        _add_row(session, entity_id="e1", source_id="s1", field_name="canonical_title")
        _add_row(session, entity_id="e1", source_id="s2", field_name="security_type")
        session.commit()

        summary = collapse_entity(session, "e1")
        session.commit()

        assert summary.groups_collapsed == 0
        assert len(_all_rows(session)) == 2

    def test_was_selected_migrates_to_the_retained_representative(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        _add_row(
            session, entity_id="e1", source_id="s1",
            effective_date=date(2024, 1, 1), was_selected=True,
        )
        _add_row(
            session, entity_id="e1", source_id="s2",
            effective_date=date(2024, 6, 1), was_selected=False,
        )
        session.commit()

        collapse_entity(session, "e1")
        session.commit()

        rows = _all_rows(session)
        assert len(rows) == 1
        assert rows[0].source_id == "s2", "the newer row is still the Pareto winner"
        assert rows[0].was_selected is True, (
            "a lost was_selected=True from a deleted row must migrate onto "
            "the retained representative -- the stewardship dashboard's "
            "'what was selected' signal must survive the collapse"
        )

    def test_dry_run_reports_but_does_not_mutate(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        _add_row(session, entity_id="e1", source_id="s1", effective_date=date(2024, 1, 1))
        _add_row(session, entity_id="e1", source_id="s2", effective_date=date(2024, 6, 1))
        session.commit()

        summary = collapse_entity(session, "e1", dry_run=True)
        session.commit()

        assert summary.groups_collapsed == 1
        assert summary.rows_deleted == 1
        assert len(_all_rows(session)) == 2, "dry-run must not delete anything"


class TestFindCollapsibleEntityIds:
    def test_only_returns_entities_with_a_multi_row_group(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        _add_row(session, entity_id="e1", source_id="s1", effective_date=date(2024, 1, 1))
        _add_row(session, entity_id="e1", source_id="s2", effective_date=date(2024, 6, 1))
        _add_row(session, entity_id="e2", source_id="s3")  # only 1 row
        session.commit()

        found = find_collapsible_entity_ids(session)
        assert found == ["e1"]

    def test_keyset_pagination_respects_after_cursor(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        for eid in ("e1", "e2", "e3"):
            _add_row(session, entity_id=eid, source_id="s1", effective_date=date(2024, 1, 1))
            _add_row(session, entity_id=eid, source_id="s2", effective_date=date(2024, 6, 1))
        session.commit()

        first_batch = find_collapsible_entity_ids(session, limit=1)
        assert first_batch == ["e1"]
        second_batch = find_collapsible_entity_ids(session, limit=1, after="e1")
        assert second_batch == ["e2"]


class TestRunBackfill:
    def test_batches_across_multiple_entities_and_commits_each_batch(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        for eid in ("e1", "e2", "e3"):
            _add_row(session, entity_id=eid, source_id="s1", effective_date=date(2024, 1, 1))
            _add_row(session, entity_id=eid, source_id="s2", effective_date=date(2024, 6, 1))
        session.commit()

        summary = run_backfill(session, batch_size=1)

        assert summary.entities_examined == 3
        assert summary.groups_collapsed == 3
        assert summary.rows_deleted == 3
        rows = _all_rows(session)
        assert len(rows) == 3
        assert all(r.effective_date == date(2024, 6, 1) for r in rows)

    def test_dry_run_examines_everything_in_one_pass_without_mutating(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        for eid in ("e1", "e2"):
            _add_row(session, entity_id=eid, source_id="s1", effective_date=date(2024, 1, 1))
            _add_row(session, entity_id=eid, source_id="s2", effective_date=date(2024, 6, 1))
        session.commit()

        summary = run_backfill(session, dry_run=True)

        assert summary.entities_examined == 2
        assert summary.groups_collapsed == 2
        assert summary.rows_deleted == 2
        assert len(_all_rows(session)) == 4, "dry-run must not delete anything"
