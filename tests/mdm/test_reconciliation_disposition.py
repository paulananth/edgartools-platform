"""Change-propagation Ticket 50: the MDM Reconciliation Backstop's finding
disposition (BaseResolver._reconcile_against_existing), driven through the
real PersonResolver.resolve_one -- the only shipped resolver where an
unscoped (owner_cik IS NULL) candidate pool makes genuine ambiguity (REVIEW
band, AUTO_MERGE onto a different existing entity) reachable at all;
CompanyResolver's candidates are always CIK-scoped to a single row and
SecurityResolver never produces a MatchVerdict (see pipeline.py's run_all
docstring and resolvers/base.py's _reconcile_against_existing docstring).

Real jellyfish Jaro-Winkler scores against the seeded person/fuzzy_name
thresholds (auto_merge_min=0.92, review_min=0.80, migrations/002_seed_data.sql):
  jaro_winkler("john smith", "jon smith")          = 0.973  -> AUTO_MERGE
  jaro_winkler("jonathan smithers", "john smith")  = 0.810  -> REVIEW
  jaro_winkler("zzz qqq", "john smith")             ~ 0.0   -> QUARANTINE
"""
from __future__ import annotations

from sqlalchemy import select

from edgar_warehouse.mdm.database import (
    MdmChangeLog,
    MdmEntity,
    MdmMatchReview,
    MdmPerson,
    MdmSourceRef,
)
from edgar_warehouse.mdm.match import MatchAction
from edgar_warehouse.mdm.resolvers import PersonResolver
from edgar_warehouse.mdm.resolvers.base import ResolverContext
from edgar_warehouse.mdm.rules import MDMRuleEngine

from tests.mdm.test_run_companies_concurrency import _seeded_sqlite_session


class _NullSilver:
    def fetch(self, sql, params=None):
        return []


def _ctx(session) -> ResolverContext:
    return ResolverContext(
        session=session,
        engine=MDMRuleEngine.load(session),
        silver=_NullSilver(),
        run_id="test-run",
    )


def _owner_row(name: str, accession: str, owner_index: int = 1) -> dict:
    return {
        "owner_cik": None,
        "owner_name": name,
        "officer_title": None,
        "is_director": False,
        "is_officer": False,
        "is_ten_percent_owner": False,
        "is_other": False,
        "accession_number": accession,
        "owner_index": owner_index,
    }


def _current_entity_id_for(session, source_id: str) -> str:
    return session.execute(
        select(MdmSourceRef.entity_id).where(
            MdmSourceRef.source_system == "ownership_filing",
            MdmSourceRef.source_id == source_id,
        )
    ).scalar_one()


def test_skip_if_unchanged_is_off_an_unchanged_row_is_still_rescored(monkeypatch):
    session = _seeded_sqlite_session(static_pool=True)
    resolver = PersonResolver()
    ctx = _ctx(session)

    row = _owner_row("Solo Person", "acc0")
    resolver.resolve_one(ctx, "ownership_filing", row, reconciliation_pass=True)
    session.commit()

    calls = {"n": 0}
    real_skip = resolver._skip_if_unchanged

    def _spy(*args, **kwargs):
        calls["n"] += 1
        return real_skip(*args, **kwargs)

    monkeypatch.setattr(resolver, "_skip_if_unchanged", _spy)

    resolver.resolve_one(ctx, "ownership_filing", row, reconciliation_pass=True)
    session.commit()

    assert calls["n"] == 0, "reconciliation_pass=True must never call _skip_if_unchanged"


def test_same_entity_id_is_a_no_op():
    session = _seeded_sqlite_session(static_pool=True)
    resolver = PersonResolver()
    ctx = _ctx(session)

    row = _owner_row("Solo Unique Person", "acc1")
    first = resolver.resolve_one(ctx, "ownership_filing", row)
    session.commit()

    outcome = resolver.resolve_one(ctx, "ownership_filing", row, reconciliation_pass=True)
    session.commit()

    assert outcome.entity_id == first.entity_id
    entity = session.get(MdmEntity, first.entity_id)
    assert entity.valid_to is None
    assert session.execute(select(MdmMatchReview)).scalars().all() == []


def test_auto_merge_onto_a_different_entity_merges_and_tombstones():
    """A realistic AUTO_MERGE-onto-a-different-entity scenario: this exact
    reporting-owner row was first resolved with no known owner_cik (creating
    its own entity E1), and a later filing reveals the real CIK -- which
    CIKExactMatcher then matches to an already-existing, independently
    created entity E2 (candidates scoped to owner_cik once one is known, so
    this is a clean CIK-exact hit, not a fuzzy-name near-miss).
    """
    session = _seeded_sqlite_session(static_pool=True)
    resolver = PersonResolver()
    ctx = _ctx(session)

    r1 = _owner_row("Solo Person No Cik Yet", "acc1")
    outcome1 = resolver.resolve_one(ctx, "ownership_filing", r1)
    session.commit()
    e1_id = outcome1.entity_id

    # A second, distinct golden record E2, already known under a real CIK --
    # seeded directly rather than through the resolver, to keep it genuinely
    # independent of E1.
    e2 = MdmEntity(entity_type="person", resolution_method="new", confidence=1.0)
    session.add(e2)
    session.flush()
    session.add(MdmPerson(entity_id=e2.entity_id, canonical_name="Some Other Person", owner_cik=778899))
    session.commit()
    e2_id = e2.entity_id

    # Reprocess R1's source row (same source_id) during a backstop pass: a
    # later filing has revealed this owner's real CIK, which is E2's.
    r1_cik_revealed = _owner_row("Solo Person No Cik Yet", "acc1")
    r1_cik_revealed["owner_cik"] = 778899
    outcome2 = resolver.resolve_one(ctx, "ownership_filing", r1_cik_revealed, reconciliation_pass=True)
    session.commit()

    assert outcome2.entity_id == e2_id
    assert outcome2.action == MatchAction.AUTO_MERGE

    e1_after = session.get(MdmEntity, e1_id)
    assert e1_after.valid_to is not None, "the superseded entity must be tombstoned"

    assert _current_entity_id_for(session, "acc1:1") == e2_id

    change = session.execute(
        select(MdmChangeLog).where(
            MdmChangeLog.entity_id == e2_id,
            MdmChangeLog.changed_fields.isnot(None),
        )
    ).scalars().all()
    assert any(c.changed_fields.get("merged_from") == e1_id for c in change)


def test_review_band_writes_match_review_and_leaves_assignment_untouched():
    session = _seeded_sqlite_session(static_pool=True)
    resolver = PersonResolver()
    ctx = _ctx(session)

    # R1 resolves alone (no real candidates) under a name unrelated to
    # everything else in this test, creating E1.
    r1 = _owner_row("Zzz Qqq Nomatch", "acc1")
    outcome1 = resolver.resolve_one(ctx, "ownership_filing", r1)
    session.commit()
    e1_id = outcome1.entity_id

    # A separate, independent golden record E2 ("john smith").
    e2 = MdmEntity(entity_type="person", resolution_method="new", confidence=1.0)
    session.add(e2)
    session.flush()
    session.add(MdmPerson(entity_id=e2.entity_id, canonical_name="john smith"))
    session.commit()
    e2_id = e2.entity_id

    # Reprocess R1, but its name now reads "Jonathan Smithers" -- scores
    # 0.810 against E2 ("john smith"), inside the review band, and near-zero
    # against E1's own stored "zzz qqq nomatch".
    r1_rescored = _owner_row("Jonathan Smithers", "acc1")
    outcome2 = resolver.resolve_one(ctx, "ownership_filing", r1_rescored, reconciliation_pass=True)
    session.commit()

    # Assignment stays on E1 -- REVIEW never merges.
    assert outcome2.entity_id == e1_id
    assert _current_entity_id_for(session, "acc1:1") == e1_id
    e1_after = session.get(MdmEntity, e1_id)
    assert e1_after.valid_to is None

    reviews = session.execute(select(MdmMatchReview)).scalars().all()
    assert len(reviews) == 1
    review = reviews[0]
    assert {review.entity_id_a, review.entity_id_b} == {e1_id, e2_id}
    assert review.status == "pending"
    assert 0.80 <= review.match_score < 0.92


def test_review_band_is_deduped_across_repeated_backstop_runs():
    session = _seeded_sqlite_session(static_pool=True)
    resolver = PersonResolver()
    ctx = _ctx(session)

    r1 = _owner_row("Zzz Qqq Nomatch", "acc1")
    resolver.resolve_one(ctx, "ownership_filing", r1)
    session.commit()

    e2 = MdmEntity(entity_type="person", resolution_method="new", confidence=1.0)
    session.add(e2)
    session.flush()
    session.add(MdmPerson(entity_id=e2.entity_id, canonical_name="john smith"))
    session.commit()

    r1_rescored = _owner_row("Jonathan Smithers", "acc1")
    resolver.resolve_one(ctx, "ownership_filing", r1_rescored, reconciliation_pass=True)
    session.commit()
    resolver.resolve_one(ctx, "ownership_filing", r1_rescored, reconciliation_pass=True)
    session.commit()

    reviews = session.execute(select(MdmMatchReview)).scalars().all()
    assert len(reviews) == 1, "a second backstop pass over unchanged drift must not re-queue"


def test_quarantine_band_never_auto_splits_a_live_golden_record():
    session = _seeded_sqlite_session(static_pool=True)
    resolver = PersonResolver()
    ctx = _ctx(session)

    r1 = _owner_row("Solo Person Alone", "acc1")
    outcome1 = resolver.resolve_one(ctx, "ownership_filing", r1)
    session.commit()
    e1_id = outcome1.entity_id

    # Nothing else exists to match against; a rescore stays firmly below
    # review_min for everything in the candidate pool (including itself,
    # since the name is unchanged it would actually self-match at 1.0 --
    # use a changed, still-nonmatching name to exercise the genuine
    # below-review_min-against-everything path).
    r1_rescored = _owner_row("Totally Different Name Zz", "acc1")
    outcome2 = resolver.resolve_one(ctx, "ownership_filing", r1_rescored, reconciliation_pass=True)
    session.commit()

    assert outcome2.entity_id == e1_id
    e1_after = session.get(MdmEntity, e1_id)
    assert e1_after.valid_to is None
    assert session.execute(select(MdmMatchReview)).scalars().all() == []
