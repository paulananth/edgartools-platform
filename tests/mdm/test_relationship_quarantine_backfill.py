"""Direct, function-level tests for
edgar_warehouse/mdm/relationship_quarantine_backfill.py.

mdm-relationship-versioning-gap Ticket 05: corrects the ~199,252 already-
quarantined `mdm_relationship_instance` rows in prod now that Tickets
01-03 fixed the write-time logic that would have prevented them, by
replaying the same discriminator/overlap/chronological-guard semantics
`ensure_relationship`/`_deactivate_if_properties_changed` already use,
directly against the already-existing rows (repurposing their own
instance_ids) rather than re-deriving fresh synthetic rows.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.mdm.database import (
    Base,
    MdmRelationshipInstance,
    MdmRelationshipSourcePriority,
    MdmRelationshipType,
)
from edgar_warehouse.mdm.relationship_quarantine_backfill import (
    backfill_relationship_id,
    find_quarantined_relationship_ids,
    run_backfill,
)

REL_TYPE_NAME = "TEST_REL_TYPE"


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sess = Session(engine)
    rel_type_id = str(uuid.uuid4())
    sess.add(MdmRelationshipType(
        rel_type_id=rel_type_id,
        rel_type_name=REL_TYPE_NAME,
        source_node_type="person",
        target_node_type="company",
        direction="outbound",
        is_temporal=True,
        merge_strategy="extend_temporal",
        is_active=True,
    ))
    sess.commit()
    sess.info["rel_type_id"] = rel_type_id
    yield sess
    sess.close()


def _row(
    session: Session,
    *,
    relationship_id: str,
    properties: dict,
    effective_from,
    valid_from_date=None,
    valid_to_date=None,
    quarantined: bool = False,
    source_system: str = "ownership_filing",
) -> MdmRelationshipInstance:
    row = MdmRelationshipInstance(
        instance_id=str(uuid.uuid4()),
        relationship_id=relationship_id,
        rel_type_id=session.info["rel_type_id"],
        source_entity_id=str(uuid.uuid4()),
        target_entity_id=str(uuid.uuid4()),
        properties=properties,
        effective_from=effective_from,
        valid_from_date=valid_from_date if valid_from_date is not None else effective_from,
        valid_to_date=valid_to_date,
        source_system=source_system,
        source_accession="acc-1",
        quarantined=quarantined,
        quarantine_reason="conflicting overlapping evidence" if quarantined else None,
    )
    session.add(row)
    return row


class TestBackfillCoreCase:
    def test_reopens_a_quarantined_row_when_conflict_still_present_same_source(self, session):
        rel_id = "rel-1"
        current = _row(
            session, relationship_id=rel_id,
            properties={"role": "officer"}, effective_from=date(2024, 10, 16),
        )
        quarantined = _row(
            session, relationship_id=rel_id,
            properties={"role": "director"}, effective_from=date(2025, 10, 8),
            quarantined=True,
        )
        session.commit()

        summary = backfill_relationship_id(session, rel_id)
        session.commit()

        assert summary.closed == 1
        assert summary.reopened == 1
        session.expire_all()
        current_row = session.get(MdmRelationshipInstance, current.instance_id)
        newer_row = session.get(MdmRelationshipInstance, quarantined.instance_id)
        assert current_row.valid_to_date == date(2025, 10, 8)
        assert newer_row.quarantined is False
        assert newer_row.quarantine_reason is None
        assert newer_row.valid_to_date is None

    def test_records_an_audit_trail_on_both_rows(self, session):
        """mdm_change_log doesn't track relationships at all -- the
        correction must leave a trace via source_evidence instead, so a
        future reader can tell 'originally never quarantined' apart from
        'corrected by this backfill'."""
        rel_id = "rel-audit-trail"
        current = _row(
            session, relationship_id=rel_id,
            properties={"role": "officer"}, effective_from=date(2024, 10, 16),
        )
        quarantined = _row(
            session, relationship_id=rel_id,
            properties={"role": "director"}, effective_from=date(2025, 10, 8),
            quarantined=True,
        )
        session.commit()

        backfill_relationship_id(session, rel_id)
        session.commit()

        session.expire_all()
        current_row = session.get(MdmRelationshipInstance, current.instance_id)
        newer_row = session.get(MdmRelationshipInstance, quarantined.instance_id)
        assert any(
            e.get("source_system") == "relationship_quarantine_backfill"
            for e in (current_row.source_evidence or [])
        )
        assert any(
            e.get("source_system") == "relationship_quarantine_backfill"
            for e in (newer_row.source_evidence or [])
        )

    def test_reopens_a_multi_version_chain_in_chronological_order(self, session):
        """Three versions of the same pair: v1 open (winner-by-default),
        v2 and v3 both quarantined against v1. Backfill must reconstruct
        the whole chain: v1 closes at v2's date, v2 opens then closes at
        v3's date, v3 ends up the sole open version."""
        rel_id = "rel-chain"
        v1 = _row(
            session, relationship_id=rel_id,
            properties={"role": "officer"}, effective_from=date(2023, 1, 1),
        )
        v2 = _row(
            session, relationship_id=rel_id,
            properties={"role": "director"}, effective_from=date(2024, 1, 1),
            quarantined=True,
        )
        v3 = _row(
            session, relationship_id=rel_id,
            properties={"role": "chairman"}, effective_from=date(2025, 1, 1),
            quarantined=True,
        )
        session.commit()

        summary = backfill_relationship_id(session, rel_id)
        session.commit()

        assert summary.closed == 2
        assert summary.reopened == 2
        session.expire_all()
        rows = {
            r.instance_id: r for r in session.scalars(
                select(MdmRelationshipInstance).where(
                    MdmRelationshipInstance.relationship_id == rel_id
                )
            )
        }
        assert rows[v1.instance_id].valid_to_date == date(2024, 1, 1)
        assert rows[v2.instance_id].valid_to_date == date(2025, 1, 1)
        assert rows[v2.instance_id].quarantined is False
        assert rows[v3.instance_id].valid_to_date is None
        assert rows[v3.instance_id].quarantined is False

    def test_reopens_against_multiple_simultaneously_open_predecessors(self, session):
        """Real prod shape (mdm-relationship-versioning-gap Ticket 08/09):
        write-time closing never fired for v1/v2, so BOTH sit open
        (valid_to_date=None) with differing properties -- already a
        violated invariant before v3 ever arrives. v3 then conflicts with
        BOTH v1 and v2 simultaneously (they're both still open-ended), not
        just one. The old pairwise design bails out entirely on 2+
        conflicts (skipped_multiple_conflicts); the chain-aware walk must
        instead close v1 at v2's date and v2 at v3's date -- reusing the
        SAME chronological ordering that already resolves the single-
        conflict case -- leaving only v3 open, even though v1 and v2 were
        never themselves quarantined."""
        rel_id = "rel-multi-open-chain"
        v1 = _row(
            session, relationship_id=rel_id,
            properties={"shares": 100}, effective_from=date(2023, 1, 1),
        )
        v2 = _row(
            session, relationship_id=rel_id,
            properties={"shares": 200}, effective_from=date(2024, 1, 1),
        )
        v3 = _row(
            session, relationship_id=rel_id,
            properties={"shares": 300}, effective_from=date(2025, 1, 1),
            quarantined=True,
        )
        session.commit()

        summary = backfill_relationship_id(session, rel_id)
        session.commit()

        assert summary.closed == 2
        assert summary.reopened == 1
        session.expire_all()
        rows = {
            r.instance_id: r for r in session.scalars(
                select(MdmRelationshipInstance).where(
                    MdmRelationshipInstance.relationship_id == rel_id
                )
            )
        }
        assert rows[v1.instance_id].valid_to_date == date(2024, 1, 1)
        assert rows[v2.instance_id].valid_to_date == date(2025, 1, 1)
        assert rows[v3.instance_id].valid_to_date is None
        assert rows[v3.instance_id].quarantined is False

    def test_closing_a_row_via_later_supersession_also_clears_its_own_stale_quarantine_flag(self, session):
        """A row can stay quarantined=True after its OWN group's processing
        (e.g. an irreconcilable same-date sibling conflict) but still joins
        open_set regardless -- it can then be the `conflict` a later,
        cleanly-resolving row closes. close_relationship_version only ever
        sets valid_to_date/effective_to, never quarantined -- so without
        this fix, such a row ends up permanently stuck quarantined=True
        forever with a valid_to_date already set, a self-contradictory
        state (closed history that never stops being flagged as needing
        review) that no future run can ever correct, since a closed row's
        own effective_from/valid_to_date never change again."""
        rel_id = "rel-close-clears-quarantine"
        a = _row(
            session, relationship_id=rel_id,
            properties={"shares": 100}, effective_from=date(2024, 1, 1),
            quarantined=True,
        )
        b = _row(
            session, relationship_id=rel_id,
            properties={"shares": 200}, effective_from=date(2024, 1, 1),
            quarantined=True,
        )
        c = _row(
            session, relationship_id=rel_id,
            properties={"shares": 300}, effective_from=date(2025, 1, 1),
        )
        session.commit()

        summary = backfill_relationship_id(session, rel_id)
        session.commit()

        assert summary.skipped_multiple_conflicts == 2  # a/b's own same-date tie
        assert summary.closed == 2  # c closes both a and b
        assert summary.reopened == 2  # a and b's stale quarantine is cleared on close
        session.expire_all()
        rows = {
            r.instance_id: r for r in session.scalars(
                select(MdmRelationshipInstance).where(
                    MdmRelationshipInstance.relationship_id == rel_id
                )
            )
        }
        assert rows[a.instance_id].valid_to_date == date(2025, 1, 1)
        assert rows[a.instance_id].quarantined is False
        assert rows[a.instance_id].quarantine_reason is None
        assert rows[b.instance_id].valid_to_date == date(2025, 1, 1)
        assert rows[b.instance_id].quarantined is False
        assert rows[b.instance_id].quarantine_reason is None
        assert rows[c.instance_id].valid_to_date is None
        assert rows[c.instance_id].quarantined is False

    def test_no_current_conflict_remaining_just_reopens_without_closing_anything(self, session):
        """The row this quarantined row originally conflicted with has
        since been closed by some other process -- nothing left to close,
        just reopen."""
        rel_id = "rel-already-closed"
        already_closed = _row(
            session, relationship_id=rel_id,
            properties={"role": "officer"}, effective_from=date(2023, 1, 1),
            valid_to_date=date(2024, 1, 1),
        )
        quarantined = _row(
            session, relationship_id=rel_id,
            properties={"role": "director"}, effective_from=date(2024, 1, 1),
            quarantined=True,
        )
        session.commit()

        summary = backfill_relationship_id(session, rel_id)
        session.commit()

        assert summary.closed == 0
        assert summary.reopened == 1
        session.expire_all()
        assert session.get(MdmRelationshipInstance, already_closed.instance_id).valid_to_date == date(2024, 1, 1)
        newer = session.get(MdmRelationshipInstance, quarantined.instance_id)
        assert newer.quarantined is False


class TestBackfillSkipsWhatItShouldNotResolve:
    def test_cross_source_conflict_is_left_untouched(self, session):
        """A quarantined row that conflicted with a DIFFERENT source_system
        is a genuine cross-source disagreement -- needs a
        mdm_relationship_source_priority rule or manual review, not an
        automated 'newer wins' override. Must be left exactly as-is."""
        rel_id = "rel-cross-source"
        current = _row(
            session, relationship_id=rel_id,
            properties={"role": "officer"}, effective_from=date(2024, 1, 1),
            source_system="ownership_filing",
        )
        quarantined = _row(
            session, relationship_id=rel_id,
            properties={"role": "director"}, effective_from=date(2025, 1, 1),
            quarantined=True, source_system="proxy_filing",
        )
        session.commit()

        summary = backfill_relationship_id(session, rel_id)
        session.commit()

        assert summary.closed == 0
        assert summary.reopened == 0
        assert summary.skipped_cross_source == 1
        session.expire_all()
        assert session.get(MdmRelationshipInstance, current.instance_id).valid_to_date is None
        assert session.get(MdmRelationshipInstance, quarantined.instance_id).quarantined is True

    def test_priority_rule_now_configured_is_left_for_separate_decision(self, session):
        """If a mdm_relationship_source_priority rule has been added SINCE
        the row was quarantined, that's a different resolution axis
        (authority-based supersession, not versioning) -- this backfill
        must not silently apply chronological reconstruction on top of a
        now-configured priority rule; it should flag it and leave both
        rows untouched."""
        session.add(MdmRelationshipSourcePriority(
            rel_type_id=session.info["rel_type_id"],
            source_system="ownership_filing", priority=1,
        ))
        session.add(MdmRelationshipSourcePriority(
            rel_type_id=session.info["rel_type_id"],
            source_system="proxy_filing", priority=2,
        ))
        rel_id = "rel-priority-now-configured"
        current = _row(
            session, relationship_id=rel_id,
            properties={"role": "officer"}, effective_from=date(2024, 1, 1),
            source_system="ownership_filing",
        )
        quarantined = _row(
            session, relationship_id=rel_id,
            properties={"role": "director"}, effective_from=date(2025, 1, 1),
            quarantined=True, source_system="proxy_filing",
        )
        session.commit()

        summary = backfill_relationship_id(session, rel_id)
        session.commit()

        assert summary.closed == 0
        assert summary.reopened == 0
        assert summary.skipped_priority_now_configured == 1
        assert summary.skipped_cross_source == 0
        session.expire_all()
        assert session.get(MdmRelationshipInstance, current.instance_id).valid_to_date is None
        assert session.get(MdmRelationshipInstance, quarantined.instance_id).quarantined is True

    def test_earlier_quarantined_row_resolves_as_legitimate_prior_history(self, session):
        """A quarantined row dated EARLIER than an already-active row it
        conflicts with is NOT the ambiguous case
        `confirmed_chronologically_after`'s own docstring guards against
        ('never close a NEWER version using a stale date') -- it's the
        opposite direction: the chronological walk reaches the LATER
        (already-active) row, confirms ITS date is after the quarantined
        row's date, and closes the quarantined row using the later row's
        own confirmed date. Officer 2024-10-16 -> 2025-10-08, then
        director 2025-10-08 onward, is a complete and correct two-period
        history -- leaving the officer row quarantined forever would serve
        no purpose. (Ticket 09: confirmed this is the intended behavior,
        a correction from the pairwise design's blind spot, not a
        regression -- the old design only ever checked the quarantined
        row's own date against its one candidate, never the reverse
        direction.)"""
        rel_id = "rel-out-of-order"
        current = _row(
            session, relationship_id=rel_id,
            properties={"role": "director"}, effective_from=date(2025, 10, 8),
        )
        quarantined = _row(
            session, relationship_id=rel_id,
            properties={"role": "officer"}, effective_from=date(2024, 10, 16),
            quarantined=True,
        )
        session.commit()

        summary = backfill_relationship_id(session, rel_id)
        session.commit()

        assert summary.closed == 1
        assert summary.reopened == 1
        session.expire_all()
        assert session.get(MdmRelationshipInstance, current.instance_id).valid_to_date is None
        newer = session.get(MdmRelationshipInstance, quarantined.instance_id)
        assert newer.quarantined is False
        assert newer.valid_to_date == date(2025, 10, 8)

    def test_same_day_supersession_is_genuinely_ambiguous_and_left_untouched(self, session):
        """Two rows with the IDENTICAL effective_from can never be
        positively confirmed as one coming strictly after the other --
        `confirmed_chronologically_after` requires strict `>`, matching
        `ck_rel_instance_valid_interval`'s own `valid_to_date > valid_from_date`
        constraint (a zero-length interval is rejected outright). This is
        the case the guard genuinely exists for, regardless of which
        direction the walk approaches it from."""
        rel_id = "rel-same-day"
        current = _row(
            session, relationship_id=rel_id,
            properties={"role": "director"}, effective_from=date(2025, 1, 1),
        )
        quarantined = _row(
            session, relationship_id=rel_id,
            properties={"role": "officer"}, effective_from=date(2025, 1, 1),
            quarantined=True,
        )
        session.commit()

        summary = backfill_relationship_id(session, rel_id)
        session.commit()

        assert summary.closed == 0
        assert summary.reopened == 0
        assert summary.skipped_ambiguous_order == 1
        session.expire_all()
        assert session.get(MdmRelationshipInstance, current.instance_id).valid_to_date is None
        assert session.get(MdmRelationshipInstance, quarantined.instance_id).quarantined is True

    def test_same_day_supersession_is_ambiguous_regardless_of_row_insertion_order(self, session):
        """Same scenario as the test above, but with the quarantined row
        inserted BEFORE the active row -- the outcome must not depend on
        which row a database query happens to return first for a tied
        effective_from. A walk that only checks a row against whatever's
        already accumulated in an 'open set' would let whichever row is
        iterated first see zero conflicts and get trivially reopened,
        before its same-day sibling is ever added -- this must not
        happen regardless of insertion/iteration order."""
        rel_id = "rel-same-day-reversed"
        quarantined = _row(
            session, relationship_id=rel_id,
            properties={"role": "officer"}, effective_from=date(2025, 1, 1),
            quarantined=True,
        )
        current = _row(
            session, relationship_id=rel_id,
            properties={"role": "director"}, effective_from=date(2025, 1, 1),
        )
        session.commit()

        summary = backfill_relationship_id(session, rel_id)
        session.commit()

        assert summary.closed == 0
        assert summary.reopened == 0
        assert summary.skipped_ambiguous_order == 1
        session.expire_all()
        assert session.get(MdmRelationshipInstance, current.instance_id).valid_to_date is None
        assert session.get(MdmRelationshipInstance, quarantined.instance_id).quarantined is True

    def test_missing_dates_on_both_sides_is_left_untouched(self, session):
        rel_id = "rel-no-dates"
        _row(
            session, relationship_id=rel_id,
            properties={"role": "officer"}, effective_from=date(2024, 1, 1),
        )
        quarantined = _row(
            session, relationship_id=rel_id,
            properties={"role": "director"}, effective_from=None, valid_from_date=None,
            quarantined=True,
        )
        session.commit()

        summary = backfill_relationship_id(session, rel_id)
        session.commit()

        assert summary.skipped_ambiguous_date == 1
        assert summary.closed == 0
        assert summary.reopened == 0
        session.expire_all()
        assert session.get(MdmRelationshipInstance, quarantined.instance_id).quarantined is True


class TestBackfillDryRun:
    def test_dry_run_reports_but_does_not_mutate(self, session):
        rel_id = "rel-dry-run"
        current = _row(
            session, relationship_id=rel_id,
            properties={"role": "officer"}, effective_from=date(2024, 10, 16),
        )
        quarantined = _row(
            session, relationship_id=rel_id,
            properties={"role": "director"}, effective_from=date(2025, 10, 8),
            quarantined=True,
        )
        session.commit()

        summary = backfill_relationship_id(session, rel_id, dry_run=True)

        assert summary.closed == 1
        assert summary.reopened == 1
        session.expire_all()
        assert session.get(MdmRelationshipInstance, current.instance_id).valid_to_date is None
        assert session.get(MdmRelationshipInstance, quarantined.instance_id).quarantined is True


class TestFindQuarantinedRelationshipIdsPagination:
    def test_after_excludes_already_seen_ids_regardless_of_outcome(self, session):
        """Keyset pagination must advance past a relationship_id even when
        its quarantined row was SKIPPED (still quarantined afterward) --
        otherwise a batch loop keyed on 'still has a quarantined row'
        would loop forever on exactly the rows it can't safely resolve."""
        _row(
            session, relationship_id="rel-aaa",
            properties={"role": "officer"}, effective_from=date(2024, 1, 1),
        )
        _row(
            session, relationship_id="rel-aaa",
            properties={"role": "director"}, effective_from=date(2020, 1, 1),
            quarantined=True,  # ambiguous order -- will be skipped, stays quarantined
        )
        _row(
            session, relationship_id="rel-bbb",
            properties={"role": "officer"}, effective_from=date(2024, 1, 1),
        )
        _row(
            session, relationship_id="rel-bbb",
            properties={"role": "director"}, effective_from=date(2025, 1, 1),
            quarantined=True,
        )
        session.commit()

        first_batch = find_quarantined_relationship_ids(session, limit=1)
        assert first_batch == ["rel-aaa"]
        second_batch = find_quarantined_relationship_ids(session, limit=1, after=first_batch[-1])
        assert second_batch == ["rel-bbb"]


class TestRunBackfillEndToEnd:
    def test_drains_all_quarantined_relationship_ids_across_batches(self, session):
        for i in range(3):
            rel_id = f"rel-{i}"
            _row(
                session, relationship_id=rel_id,
                properties={"role": "officer"}, effective_from=date(2024, 1, 1),
            )
            _row(
                session, relationship_id=rel_id,
                properties={"role": "director"}, effective_from=date(2025, 1, 1),
                quarantined=True,
            )
        session.commit()

        summary = run_backfill(session, batch_size=1)

        assert summary.relationship_ids_examined == 3
        assert summary.closed == 3
        assert summary.reopened == 3
        assert find_quarantined_relationship_ids(session) == []

    def test_batched_run_advances_past_unresolvable_rows_without_looping_forever(self, session):
        """The bug the keyset-pagination fix closes: a relationship_id
        whose quarantined row is skipped (still quarantined afterward)
        must not make run_backfill loop forever re-fetching it."""
        _row(
            session, relationship_id="rel-stuck",
            properties={"role": "officer"}, effective_from=date(2024, 1, 1),
            source_system="ownership_filing",
        )
        _row(
            session, relationship_id="rel-stuck",
            properties={"role": "director"}, effective_from=date(2025, 1, 1),
            quarantined=True, source_system="proxy_filing",  # cross-source -- unresolvable
        )
        session.commit()

        summary = run_backfill(session, batch_size=1)

        assert summary.relationship_ids_examined == 1
        assert summary.skipped_cross_source == 1
        # Still quarantined -- confirms the run terminated rather than
        # looping, without silently pretending the row got fixed.
        assert find_quarantined_relationship_ids(session) == ["rel-stuck"]
