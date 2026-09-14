"""Direct, function-level tests for
edgar_warehouse/mdm/manages_fund_duplicate_backfill.py.

manages-fund-duplicate-rows map, Ticket 05: resolves the existing
~140,907-relationship_id MANAGES_FUND duplicate-active-row backlog by
superseding every row but one deterministic keeper per relationship_id.
Unlike relationship_quarantine_backfill.py's chain-aware conflict
resolution, every row in an affected group here is confirmed
byte-identical evidence -- there is nothing to resolve, only a
deterministic winner to pick.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.mdm.database import Base, MdmRelationshipInstance, MdmRelationshipType
from edgar_warehouse.mdm.manages_fund_duplicate_backfill import (
    REL_TYPE_NAME,
    backfill_relationship_id,
    find_duplicate_relationship_ids,
    run_backfill,
)

_OTHER_REL_TYPE_NAME = "INSTITUTIONAL_HOLDS"


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sess = Session(engine)
    manages_fund_id = str(uuid.uuid4())
    other_id = str(uuid.uuid4())
    sess.add(MdmRelationshipType(
        rel_type_id=manages_fund_id,
        rel_type_name=REL_TYPE_NAME,
        source_node_type="adviser",
        target_node_type="fund",
        direction="outbound",
        is_temporal=True,
        merge_strategy="extend_temporal",
        is_active=True,
    ))
    sess.add(MdmRelationshipType(
        rel_type_id=other_id,
        rel_type_name=_OTHER_REL_TYPE_NAME,
        source_node_type="institution",
        target_node_type="company",
        direction="outbound",
        is_temporal=True,
        merge_strategy="extend_temporal",
        is_active=True,
    ))
    sess.commit()
    sess.info["rel_type_id"] = manages_fund_id
    sess.info["other_rel_type_id"] = other_id
    yield sess
    sess.close()


def _row(
    session: Session,
    *,
    relationship_id: str,
    instance_id: str | None = None,
    properties: dict | None = None,
    valid_from_date=date(2026, 1, 1),
    valid_to_date=None,
    is_active: bool = True,
    quarantined: bool = False,
    superseded_by_version_id: str | None = None,
    rel_type_id: str | None = None,
) -> MdmRelationshipInstance:
    row = MdmRelationshipInstance(
        instance_id=instance_id if instance_id is not None else str(uuid.uuid4()),
        relationship_id=relationship_id,
        rel_type_id=rel_type_id if rel_type_id is not None else session.info["rel_type_id"],
        source_entity_id=str(uuid.uuid4()),
        target_entity_id=str(uuid.uuid4()),
        properties=properties if properties is not None else {"reporting_role": "adviser"},
        valid_from_date=valid_from_date,
        valid_to_date=valid_to_date,
        source_system="sec_adv_private_fund",
        source_accession="acc-1",
        is_active=is_active,
        quarantined=quarantined,
        superseded_by_version_id=superseded_by_version_id,
    )
    session.add(row)
    return row


class TestFindDuplicateRelationshipIds:
    def test_finds_a_relationship_id_with_two_plus_active_rows(self, session):
        rel_id = "rel-dup"
        _row(session, relationship_id=rel_id)
        _row(session, relationship_id=rel_id)
        session.commit()

        assert find_duplicate_relationship_ids(session) == [rel_id]

    def test_excludes_a_relationship_id_with_only_one_active_row(self, session):
        _row(session, relationship_id="rel-single")
        session.commit()

        assert find_duplicate_relationship_ids(session) == []

    def test_excludes_quarantined_and_superseded_rows_from_the_count(self, session):
        rel_id = "rel-mixed"
        keeper = _row(session, relationship_id=rel_id)
        _row(session, relationship_id=rel_id, quarantined=True)
        session.commit()
        _row(session, relationship_id=rel_id, superseded_by_version_id=keeper.instance_id)
        session.commit()

        # Only 1 genuinely active, non-quarantined, non-superseded row --
        # not a duplicate group.
        assert find_duplicate_relationship_ids(session) == []

    def test_ignores_other_relationship_types(self, session):
        rel_id = "rel-other-type"
        _row(session, relationship_id=rel_id, rel_type_id=session.info["other_rel_type_id"])
        _row(session, relationship_id=rel_id, rel_type_id=session.info["other_rel_type_id"])
        session.commit()

        assert find_duplicate_relationship_ids(session) == []

    def test_limit_and_keyset_pagination_advance_through_stable_order(self, session):
        rel_ids = sorted(f"rel-{i}" for i in range(5))
        for rel_id in rel_ids:
            _row(session, relationship_id=rel_id)
            _row(session, relationship_id=rel_id)
        session.commit()

        first_page = find_duplicate_relationship_ids(session, limit=2)
        assert first_page == rel_ids[:2]
        second_page = find_duplicate_relationship_ids(
            session, limit=2, after=first_page[-1]
        )
        assert second_page == rel_ids[2:4]


class TestBackfillRelationshipId:
    def test_supersedes_all_but_one_deterministic_keeper(self, session):
        rel_id = "rel-dup"
        a = _row(session, relationship_id=rel_id, instance_id="b-instance")
        b = _row(session, relationship_id=rel_id, instance_id="a-instance")
        c = _row(session, relationship_id=rel_id, instance_id="c-instance")
        session.commit()

        summary = backfill_relationship_id(session, rel_id)
        session.commit()

        assert summary.relationship_ids_examined == 1
        assert summary.rows_superseded == 2
        session.expire_all()
        # "a-instance" sorts smallest lexicographically -- the keeper.
        keeper = session.get(MdmRelationshipInstance, "a-instance")
        loser_1 = session.get(MdmRelationshipInstance, "b-instance")
        loser_2 = session.get(MdmRelationshipInstance, "c-instance")
        assert keeper.superseded_by_version_id is None
        assert loser_1.superseded_by_version_id == "a-instance"
        assert loser_2.superseded_by_version_id == "a-instance"

    def test_never_touches_is_active_or_valid_to_date(self, session):
        rel_id = "rel-dup"
        _row(session, relationship_id=rel_id, instance_id="a-instance")
        loser = _row(session, relationship_id=rel_id, instance_id="b-instance")
        session.commit()

        backfill_relationship_id(session, rel_id)
        session.commit()

        session.expire_all()
        loser_row = session.get(MdmRelationshipInstance, "b-instance")
        assert loser_row.is_active is True
        assert loser_row.valid_to_date is None
        assert loser_row.superseded_by_version_id == "a-instance"

    def test_never_touches_a_quarantined_row(self, session):
        rel_id = "rel-mixed"
        _row(session, relationship_id=rel_id, instance_id="a-instance")
        _row(session, relationship_id=rel_id, instance_id="b-instance")
        quarantined = _row(
            session, relationship_id=rel_id, instance_id="q-instance", quarantined=True
        )
        session.commit()

        backfill_relationship_id(session, rel_id)
        session.commit()

        session.expire_all()
        quarantined_row = session.get(MdmRelationshipInstance, "q-instance")
        assert quarantined_row.superseded_by_version_id is None
        assert quarantined_row.quarantined is True

    def test_dry_run_does_not_mutate_anything(self, session):
        rel_id = "rel-dup"
        _row(session, relationship_id=rel_id, instance_id="a-instance")
        _row(session, relationship_id=rel_id, instance_id="b-instance")
        session.commit()

        summary = backfill_relationship_id(session, rel_id, dry_run=True)
        session.commit()

        assert summary.rows_superseded == 1
        session.expire_all()
        loser_row = session.get(MdmRelationshipInstance, "b-instance")
        assert loser_row.superseded_by_version_id is None

    def test_single_active_row_is_a_no_op(self, session):
        rel_id = "rel-single"
        _row(session, relationship_id=rel_id, instance_id="a-instance")
        session.commit()

        summary = backfill_relationship_id(session, rel_id)

        assert summary.relationship_ids_examined == 1
        assert summary.rows_superseded == 0


class TestRunBackfill:
    def test_real_run_processes_every_group_and_commits_per_batch(self, session):
        for i in range(3):
            rel_id = f"rel-{i}"
            _row(session, relationship_id=rel_id)
            _row(session, relationship_id=rel_id)
        session.commit()

        summary = run_backfill(session, batch_size=2)

        assert summary.relationship_ids_examined == 3
        assert summary.rows_superseded == 3
        # A second run finds nothing left -- every group dropped below 2
        # active rows, so this is provably idempotent, not just "ran once."
        assert run_backfill(session).relationship_ids_examined == 0

    def test_dry_run_reports_without_mutating(self, session):
        rel_id = "rel-dup"
        a = _row(session, relationship_id=rel_id, instance_id="a-instance")
        _row(session, relationship_id=rel_id, instance_id="b-instance")
        session.commit()

        summary = run_backfill(session, dry_run=True)

        assert summary.relationship_ids_examined == 1
        assert summary.rows_superseded == 1
        session.expire_all()
        assert session.get(MdmRelationshipInstance, "b-instance").superseded_by_version_id is None

    def test_limit_bounds_a_real_run_to_a_first_pass(self, session):
        for i in range(4):
            rel_id = f"rel-{i}"
            _row(session, relationship_id=rel_id)
            _row(session, relationship_id=rel_id)
        session.commit()

        summary = run_backfill(session, limit=2)

        assert summary.relationship_ids_examined == 2
        assert summary.rows_superseded == 2
        # The remaining 2 groups are untouched and still findable.
        assert len(find_duplicate_relationship_ids(session)) == 2

    def test_limit_bounds_a_dry_run_too(self, session):
        for i in range(4):
            rel_id = f"rel-{i}"
            _row(session, relationship_id=rel_id)
            _row(session, relationship_id=rel_id)
        session.commit()

        summary = run_backfill(session, dry_run=True, limit=2)

        assert summary.relationship_ids_examined == 2
