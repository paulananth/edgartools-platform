"""Tests for change-propagation Ticket 49's 1-hop candidate-neighbor expansion."""

from __future__ import annotations

from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import MdmEntity, MdmRelationshipInstance
from edgar_warehouse.mdm.neighbor_expansion import find_one_hop_neighbor_entity_ids

from .conftest import _seed_rel_type


def _make_entity(session: Session, entity_type: str = "company") -> str:
    entity = MdmEntity(entity_type=entity_type, resolution_method="cik_exact", confidence=1.0)
    session.add(entity)
    session.flush()
    return entity.entity_id


def _make_relationship(
    session: Session,
    rel_type_id: str,
    source_entity_id: str,
    target_entity_id: str,
    *,
    is_active: bool = True,
    quarantined: bool = False,
) -> None:
    session.add(
        MdmRelationshipInstance(
            rel_type_id=rel_type_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            is_active=is_active,
            quarantined=quarantined,
        )
    )
    session.flush()


def test_direct_neighbor_is_found_one_hop_away(db_session: Session) -> None:
    company = _make_entity(db_session, "company")
    person = _make_entity(db_session, "person")
    rel_type_id = _seed_rel_type(db_session, "IS_INSIDER", "person", "company")
    db_session.flush()

    _make_relationship(db_session, rel_type_id, source_entity_id=person, target_entity_id=company)

    neighbors = find_one_hop_neighbor_entity_ids(db_session, {company})

    assert neighbors == {person}


def test_two_hop_entity_is_not_returned(db_session: Session) -> None:
    """The ticket's own required test: a changed company re-checks a direct
    neighbor, and does NOT re-check a 2-hop entity.
    """
    company = _make_entity(db_session, "company")
    person = _make_entity(db_session, "person")
    auditor = _make_entity(db_session, "audit_firm")
    rel_type_id = _seed_rel_type(db_session, "IS_INSIDER", "person", "company")
    audited_by_id = _seed_rel_type(db_session, "AUDITED_BY", "audit_firm", "person")

    _make_relationship(db_session, rel_type_id, source_entity_id=person, target_entity_id=company)
    # auditor is 2 hops from company (company -> person -> auditor), never
    # directly linked to company itself.
    _make_relationship(db_session, audited_by_id, source_entity_id=auditor, target_entity_id=person)

    neighbors = find_one_hop_neighbor_entity_ids(db_session, {company})

    assert neighbors == {person}
    assert auditor not in neighbors


def test_changed_entity_is_never_its_own_neighbor(db_session: Session) -> None:
    company_a = _make_entity(db_session, "company")
    company_b = _make_entity(db_session, "company")
    rel_type_id = _seed_rel_type(db_session, "HAS_PARENT_COMPANY_2", "company", "company")

    _make_relationship(
        db_session, rel_type_id, source_entity_id=company_a, target_entity_id=company_b
    )

    neighbors = find_one_hop_neighbor_entity_ids(db_session, {company_a, company_b})

    assert neighbors == set()


def test_quarantined_relationship_is_not_a_real_edge(db_session: Session) -> None:
    company = _make_entity(db_session, "company")
    person = _make_entity(db_session, "person")
    rel_type_id = _seed_rel_type(db_session, "IS_INSIDER", "person", "company")
    db_session.flush()

    _make_relationship(
        db_session, rel_type_id, source_entity_id=person, target_entity_id=company, quarantined=True
    )

    neighbors = find_one_hop_neighbor_entity_ids(db_session, {company})

    assert neighbors == set()


def test_inactive_relationship_is_not_a_real_edge(db_session: Session) -> None:
    company = _make_entity(db_session, "company")
    person = _make_entity(db_session, "person")
    rel_type_id = _seed_rel_type(db_session, "IS_INSIDER", "person", "company")
    db_session.flush()

    _make_relationship(
        db_session, rel_type_id, source_entity_id=person, target_entity_id=company, is_active=False
    )

    neighbors = find_one_hop_neighbor_entity_ids(db_session, {company})

    assert neighbors == set()


def test_empty_changed_set_returns_empty_neighbors_without_a_query(db_session: Session) -> None:
    assert find_one_hop_neighbor_entity_ids(db_session, set()) == set()


def test_neighbor_found_regardless_of_which_side_it_is_on(db_session: Session) -> None:
    """The edge direction (source vs target) must not matter for finding a
    neighbor -- a relationship recorded company->person or person->company
    both count as one direct edge.
    """
    company = _make_entity(db_session, "company")
    person = _make_entity(db_session, "person")
    rel_type_id = _seed_rel_type(db_session, "IS_INSIDER", "company", "person")

    _make_relationship(db_session, rel_type_id, source_entity_id=company, target_entity_id=person)

    neighbors = find_one_hop_neighbor_entity_ids(db_session, {company})

    assert neighbors == {person}
