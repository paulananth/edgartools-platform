"""End-to-end proof of change-propagation Ticket 49 through MDMPipeline.run_all().

The ticket's own required test: a changed company re-checks a directly-
linked person and does not re-check a 2-hop entity. This exercises the
real run_all() wiring (not just the pure find_one_hop_neighbor_entity_ids
query, already covered in tests/mdm/test_neighbor_expansion.py).
"""

from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import select

from edgar_warehouse.mdm import pipeline as pipeline_module
from edgar_warehouse.mdm.database import (
    MdmCompany,
    MdmEntity,
    MdmEntityAttributeStage,
    MdmPerson,
    MdmRelationshipInstance,
    MdmRelationshipType,
)
from edgar_warehouse.mdm.pipeline import MDMPipeline

from tests.mdm.test_run_all_step_concurrency import (
    _real_silver_with_companies,
    _seed_fundamentals_relationship_types,
)
from tests.mdm.test_run_companies_concurrency import _seeded_sqlite_session, _StubBookkeeping


def _make_entity(session, entity_type: str) -> str:
    entity = MdmEntity(entity_type=entity_type, resolution_method="cik_exact", confidence=1.0)
    session.add(entity)
    session.flush()
    return entity.entity_id


def test_changed_company_rechecks_direct_person_neighbor_not_two_hop() -> None:
    session = _seeded_sqlite_session(static_pool=True)
    silver = _real_silver_with_companies(1)
    _seed_fundamentals_relationship_types(session)

    company_cik = list(
        row[0]
        for row in silver._conn.execute("SELECT cik FROM sec_company").fetchall()
    )[0]

    # Pre-seed the company entity with NO MdmSourceRef row yet -- resolve_one
    # will treat this as a genuine first observation (not skipped_unchanged),
    # exactly like a real content change would, without needing to fabricate
    # a hash mismatch.
    company_entity_id = _make_entity(session, "company")
    session.add(MdmCompany(entity_id=company_entity_id, cik=company_cik, canonical_name="Old Name"))

    # Direct (1-hop) neighbor: a person with an existing IS_INSIDER edge to
    # the company.
    direct_person_entity_id = _make_entity(session, "person")
    session.add(
        MdmPerson(entity_id=direct_person_entity_id, owner_cik=555001, canonical_name="Direct Insider")
    )
    session.add(
        MdmRelationshipInstance(
            rel_type_id=session.execute(
                select(MdmRelationshipType.rel_type_id).where(
                    MdmRelationshipType.rel_type_name == "IS_INSIDER"
                )
            ).scalar_one(),
            source_entity_id=direct_person_entity_id,
            target_entity_id=company_entity_id,
        )
    )

    # 2-hop entity: a second person linked only to the direct neighbor, not
    # to the company itself -- must never be re-checked by this pass.
    two_hop_person_entity_id = _make_entity(session, "person")
    session.add(
        MdmPerson(entity_id=two_hop_person_entity_id, owner_cik=555002, canonical_name="Two Hop Away")
    )
    session.add(
        MdmRelationshipInstance(
            rel_type_id=session.execute(
                select(MdmRelationshipType.rel_type_id).where(
                    MdmRelationshipType.rel_type_name == "IS_INSIDER"
                )
            ).scalar_one(),
            source_entity_id=two_hop_person_entity_id,
            target_entity_id=direct_person_entity_id,
        )
    )
    session.commit()

    outer_pipeline = MDMPipeline(session=session, silver=silver)

    captured_owner_ciks: list[list[int]] = []
    real_run_persons = MDMPipeline.run_persons

    def _spy_run_persons(self, *args, **kwargs):
        if "owner_ciks" in kwargs:
            captured_owner_ciks.append(list(kwargs["owner_ciks"]))
        return real_run_persons(self, *args, **kwargs)

    with patch.object(MDMPipeline, "run_persons", _spy_run_persons):
        stats = outer_pipeline.run_all(bookkeeping=_StubBookkeeping())

    assert stats.companies_processed == 1
    assert captured_owner_ciks == [[555001]], (
        "expected exactly one owner_ciks-scoped run_persons call, for the "
        "direct neighbor only -- the 2-hop person (555002) must never appear"
    )
    # This test's silver has no sec_ownership_reporting_owner rows for
    # owner_cik 555001, so the scoped re-check call correctly finds and
    # processes zero rows -- the property this test proves is that the
    # call happened, correctly scoped, not that it found new data to
    # resolve (a separate, already-covered property).
    assert stats.neighbor_persons_rechecked == 0


def test_no_relationship_neighbors_means_no_extra_run_persons_call() -> None:
    """A changed company with zero existing relationships triggers no
    neighbor-expansion re-check at all -- proportional cost, not a
    universe scan.
    """
    session = _seeded_sqlite_session(static_pool=True)
    silver = _real_silver_with_companies(1)
    _seed_fundamentals_relationship_types(session)
    outer_pipeline = MDMPipeline(session=session, silver=silver)

    captured_owner_ciks: list[list[int]] = []
    real_run_persons = MDMPipeline.run_persons

    def _spy_run_persons(self, *args, **kwargs):
        if "owner_ciks" in kwargs:
            captured_owner_ciks.append(list(kwargs["owner_ciks"]))
        return real_run_persons(self, *args, **kwargs)

    with patch.object(MDMPipeline, "run_persons", _spy_run_persons):
        stats = outer_pipeline.run_all(bookkeeping=_StubBookkeeping())

    assert stats.companies_processed == 1
    assert captured_owner_ciks == []
    assert stats.neighbor_persons_rechecked == 0


def test_direct_neighbor_with_real_silver_data_is_actually_resolved() -> None:
    """The scoping-only tests above prove owner_ciks reaches run_persons
    correctly, but not that a real re-check does anything -- Standards
    review flagged this gap directly. Here the direct neighbor has a real
    sec_ownership_reporting_owner row in silver, so run_persons(owner_ciks=
    [...]) must actually resolve it, not just iterate an empty result set.
    """
    session = _seeded_sqlite_session(static_pool=True)
    silver = _real_silver_with_companies(1)
    _seed_fundamentals_relationship_types(session)

    company_cik = silver._conn.execute("SELECT cik FROM sec_company").fetchall()[0][0]
    silver._conn.execute(
        """
        INSERT INTO sec_ownership_reporting_owner
            (accession_number, owner_index, owner_cik, owner_name,
             is_director, is_officer, is_ten_percent_owner, is_other, officer_title)
        VALUES ('0000000001', 1, 555001, 'Direct Insider', TRUE, FALSE, FALSE, FALSE, NULL)
        """
    )

    company_entity_id = _make_entity(session, "company")
    session.add(MdmCompany(entity_id=company_entity_id, cik=company_cik, canonical_name="Old Name"))

    direct_person_entity_id = _make_entity(session, "person")
    session.add(
        MdmPerson(entity_id=direct_person_entity_id, owner_cik=555001, canonical_name="Direct Insider")
    )
    session.add(
        MdmRelationshipInstance(
            rel_type_id=session.execute(
                select(MdmRelationshipType.rel_type_id).where(
                    MdmRelationshipType.rel_type_name == "IS_INSIDER"
                )
            ).scalar_one(),
            source_entity_id=direct_person_entity_id,
            target_entity_id=company_entity_id,
        )
    )
    session.commit()

    outer_pipeline = MDMPipeline(session=session, silver=silver)
    stats = outer_pipeline.run_all(bookkeeping=_StubBookkeeping())

    assert stats.companies_processed == 1
    assert stats.neighbor_persons_rechecked == 1


def test_second_call_on_an_unchanged_neighbor_hits_skip_if_unchanged() -> None:
    """Ticket 49's own bullet 3: skip-if-unchanged still applies inside
    the neighbor re-check -- a re-check is not a forced full re-resolution.
    Proven directly at PersonResolver's own mechanism: mdm_entity_attribute_
    stage is append-only (per this repo's PersonResolver.resolve_one
    docstring) and only grows on a real (non-skipped) resolution, so a
    second owner_ciks-scoped call against unchanged silver data must add
    zero new staging rows for that entity, while the first call adds at
    least one.
    """
    session = _seeded_sqlite_session(static_pool=True)
    silver = _real_silver_with_companies(1)
    _seed_fundamentals_relationship_types(session)

    silver._conn.execute(
        """
        INSERT INTO sec_ownership_reporting_owner
            (accession_number, owner_index, owner_cik, owner_name,
             is_director, is_officer, is_ten_percent_owner, is_other, officer_title)
        VALUES ('0000000001', 1, 555001, 'Direct Insider', TRUE, FALSE, FALSE, FALSE, NULL)
        """
    )

    direct_person_entity_id = _make_entity(session, "person")
    session.add(
        MdmPerson(entity_id=direct_person_entity_id, owner_cik=555001, canonical_name="Direct Insider")
    )
    session.commit()

    pipeline = MDMPipeline(session=session, silver=silver)

    first_processed = pipeline.run_persons(owner_ciks=[555001])
    session.commit()
    assert first_processed == 1
    stage_count_after_first = session.execute(
        select(MdmEntityAttributeStage).where(
            MdmEntityAttributeStage.entity_id == direct_person_entity_id
        )
    ).all()
    assert stage_count_after_first, "expected the first (real) resolution to write staging rows"

    second_processed = pipeline.run_persons(owner_ciks=[555001])
    session.commit()
    stage_count_after_second = session.execute(
        select(MdmEntityAttributeStage).where(
            MdmEntityAttributeStage.entity_id == direct_person_entity_id
        )
    ).all()

    assert second_processed == 1  # the row is still iterated
    assert len(stage_count_after_second) == len(stage_count_after_first), (
        "expected skip-if-unchanged to fire on the second call against "
        "unchanged silver data -- no new staging rows, not a second full "
        "resolution"
    )
