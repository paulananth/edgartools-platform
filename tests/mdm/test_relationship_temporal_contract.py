"""Tests for Phase 7 Plan 01: relationship identity, temporal contract, and
conflict/quarantine rules (RTEMP-01, RTEMP-03, RTEMP-04, RLINE-01).

Uses an in-memory SQLite store (schema created from the ORM via
Base.metadata.create_all), matching the existing MDM test convention -- see
tests/mdm/test_pipeline_relationships.py. The Postgres-only migration SQL
(006_relationship_temporal_contract.sql) cannot run against SQLite, so its
idempotency guards are checked structurally (test_migration_*), and the
critical migration/runtime consistency invariant -- that the SQL backfill's
md5-derived relationship_id matches database.relationship_logical_id()
exactly -- is checked by recomputing the same formula independently in
Python (test_relationship_id_matches_sql_backfill_formula).
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.mdm import graph as graph_module
from edgar_warehouse.mdm.database import (
    Base,
    MdmEntity,
    MdmEntityTypeDefinition,
    MdmRelationshipInstance,
    MdmRelationshipSourcePriority,
    MdmRelationshipType,
    relationship_logical_id,
)
from edgar_warehouse.mdm.graph import (
    GraphRegistry,
    GraphSyncEngine,
    close_relationship_version,
    quarantine_relationship_version,
    supersede_relationship_version,
)
from edgar_warehouse.mdm.migrations import runtime as migrations


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _seed_registry(session: Session) -> dict[str, str]:
    for et, label, table in [
        ("person", "Person", "mdm_person"),
        ("company", "Company", "mdm_company"),
    ]:
        session.add(MdmEntityTypeDefinition(
            entity_type=et, neo4j_label=label, domain_table=table,
            api_path_prefix=f"/{et}s", primary_id_field="entity_id",
            display_name=label, is_active=True,
        ))
    rel_types = {}
    for name, src, tgt in [("EMPLOYED_BY", "person", "company")]:
        rt_id = str(uuid.uuid4())
        session.add(MdmRelationshipType(
            rel_type_id=rt_id, rel_type_name=name,
            source_node_type=src, target_node_type=tgt,
            direction="outbound", is_temporal=True,
            merge_strategy="extend_temporal", is_active=True,
        ))
        rel_types[name] = rt_id
    session.commit()
    return rel_types


def _add_entity(session: Session, entity_type: str) -> str:
    eid = str(uuid.uuid4())
    session.add(MdmEntity(entity_id=eid, entity_type=entity_type))
    session.flush()
    return eid


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def world(session: Session):
    rel_types = _seed_registry(session)
    person_id = _add_entity(session, "person")
    company_id = _add_entity(session, "company")
    return {
        "rel_types": rel_types,
        "person_id": person_id,
        "company_id": company_id,
        "engine": GraphSyncEngine(session, GraphRegistry.load(session)),
    }


# ---------------------------------------------------------------------------
# Task 1: identity, migration guards, interval constraint
# ---------------------------------------------------------------------------

class TestRelationshipIdentity:
    def test_relationship_id_matches_sql_backfill_formula(self, world):
        """The Python logical-ID function and the SQL migration's md5 backfill
        must produce byte-identical output for the same triple -- otherwise a
        pre-migration row and a post-migration write for the same logical
        relationship would silently diverge onto two different logical IDs.
        """
        rel_type_id = world["rel_types"]["EMPLOYED_BY"]
        source_id = world["person_id"]
        target_id = world["company_id"]

        actual = relationship_logical_id(rel_type_id, source_id, target_id)

        digest = hashlib.md5(f"{rel_type_id}:{source_id}:{target_id}".encode("utf-8")).hexdigest()
        expected_sql_equivalent = (
            f"{digest[0:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"
        )
        assert actual == expected_sql_equivalent
        uuid.UUID(actual)  # must be a syntactically valid UUID

    def test_relationship_id_is_stable_and_deterministic(self, world):
        rel_type_id = world["rel_types"]["EMPLOYED_BY"]
        first = relationship_logical_id(rel_type_id, world["person_id"], world["company_id"])
        second = relationship_logical_id(rel_type_id, world["person_id"], world["company_id"])
        assert first == second

    def test_relationship_id_differs_for_different_triples(self, world, session):
        rel_type_id = world["rel_types"]["EMPLOYED_BY"]
        other_company = _add_entity(session, "company")
        a = relationship_logical_id(rel_type_id, world["person_id"], world["company_id"])
        b = relationship_logical_id(rel_type_id, world["person_id"], other_company)
        assert a != b

    def test_existing_instance_ids_are_preserved_and_get_a_relationship_id(self, world):
        engine = world["engine"]
        row, created = engine.ensure_relationship(
            "EMPLOYED_BY", world["person_id"], world["company_id"],
            properties={"title": "CEO"}, source_system="proxy_fundamentals",
        )
        assert created
        assert row.instance_id is not None
        assert row.relationship_id == relationship_logical_id(
            world["rel_types"]["EMPLOYED_BY"], world["person_id"], world["company_id"]
        )


class TestValidIntervalConstraint:
    def test_reversed_interval_is_rejected(self, world, session):
        row = MdmRelationshipInstance(
            relationship_id=relationship_logical_id(
                world["rel_types"]["EMPLOYED_BY"], world["person_id"], world["company_id"]
            ),
            rel_type_id=world["rel_types"]["EMPLOYED_BY"],
            source_entity_id=world["person_id"],
            target_entity_id=world["company_id"],
            valid_from_date=date(2024, 1, 1),
            valid_to_date=date(2023, 1, 1),
        )
        session.add(row)
        with pytest.raises(IntegrityError):
            session.flush()

    def test_open_ended_interval_is_allowed(self, world, session):
        row = MdmRelationshipInstance(
            relationship_id=relationship_logical_id(
                world["rel_types"]["EMPLOYED_BY"], world["person_id"], world["company_id"]
            ),
            rel_type_id=world["rel_types"]["EMPLOYED_BY"],
            source_entity_id=world["person_id"],
            target_entity_id=world["company_id"],
            valid_from_date=date(2024, 1, 1),
            valid_to_date=None,
        )
        session.add(row)
        session.flush()  # must not raise


class TestMigrationFileGuards:
    """Structural guard checks (mirrors test_runtime_ops.py's normalized-text
    style) since 006's Postgres-only SQL cannot execute against SQLite."""

    def _sql(self) -> str:
        path = Path(migrations.__file__).with_name("006_relationship_temporal_contract.sql")
        return path.read_text(encoding="utf-8")

    def test_all_new_columns_are_guarded_additive(self):
        sql = self._sql()
        for column in (
            "relationship_id", "valid_from_date", "valid_to_date", "date_provenance",
            "relationship_kind", "source_evidence", "superseded_by_version_id",
            "quarantined", "quarantine_reason",
        ):
            assert f"ADD COLUMN IF NOT EXISTS {column}" in sql, column

    def test_new_table_is_guarded(self):
        sql = self._sql()
        assert "CREATE TABLE IF NOT EXISTS mdm_relationship_source_priority" in sql

    def test_constraints_are_existence_checked_before_adding(self):
        sql = self._sql()
        assert sql.count("IF NOT EXISTS (\n        SELECT 1 FROM pg_constraint") >= 3

    def test_is_registered_in_migrate(self):
        assert "006_relationship_temporal_contract.sql" in Path(migrations.__file__).read_text()


# ---------------------------------------------------------------------------
# Task 2: versioning, merge, conflict/priority, quarantine, no-delete
# ---------------------------------------------------------------------------

class TestIdenticalEvidenceMerges:
    def test_repeated_identical_evidence_does_not_duplicate(self, world, session):
        engine = world["engine"]
        row1, created1 = engine.ensure_relationship(
            "EMPLOYED_BY", world["person_id"], world["company_id"],
            properties={"title": "CEO"}, valid_from_date=date(2024, 1, 1),
            source_system="proxy_fundamentals", source_accession="0001-24-000001",
        )
        row2, created2 = engine.ensure_relationship(
            "EMPLOYED_BY", world["person_id"], world["company_id"],
            properties={"title": "CEO"}, valid_from_date=date(2024, 1, 1),
            source_system="proxy_fundamentals", source_accession="0001-25-000002",
        )
        session.flush()
        assert created1 is True
        assert created2 is False
        assert row1.instance_id == row2.instance_id
        all_rows = list(session.scalars(
            select(MdmRelationshipInstance).where(
                MdmRelationshipInstance.relationship_id == row1.relationship_id
            )
        ))
        assert len(all_rows) == 1
        assert len(row1.source_evidence) == 2


class TestConflictResolution:
    def test_overlap_without_configured_priority_quarantines_new_version(self, world, session):
        engine = world["engine"]
        existing, _ = engine.ensure_relationship(
            "EMPLOYED_BY", world["person_id"], world["company_id"],
            properties={"title": "CEO"}, valid_from_date=date(2024, 1, 1),
            source_system="proxy_fundamentals",
        )
        session.flush()

        new_row, created = engine.ensure_relationship(
            "EMPLOYED_BY", world["person_id"], world["company_id"],
            properties={"title": "President"}, valid_from_date=date(2024, 6, 1),
            source_system="unverified_scrape",
        )
        session.flush()

        assert created is True
        assert new_row.quarantined is True
        assert new_row.quarantine_reason
        assert new_row.superseded_by_version_id is None
        assert existing.superseded_by_version_id is None
        assert existing.quarantined is False

    def test_overlap_with_configured_priority_supersedes_loser(self, world, session):
        rel_type_id = world["rel_types"]["EMPLOYED_BY"]
        session.add(MdmRelationshipSourcePriority(
            rel_type_id=rel_type_id, source_system="proxy_fundamentals", priority=1,
        ))
        session.add(MdmRelationshipSourcePriority(
            rel_type_id=rel_type_id, source_system="unverified_scrape", priority=99,
        ))
        session.commit()

        engine = world["engine"]
        existing, _ = engine.ensure_relationship(
            "EMPLOYED_BY", world["person_id"], world["company_id"],
            properties={"title": "President"}, valid_from_date=date(2024, 1, 1),
            source_system="unverified_scrape",
        )
        session.flush()

        winner, created = engine.ensure_relationship(
            "EMPLOYED_BY", world["person_id"], world["company_id"],
            properties={"title": "CEO"}, valid_from_date=date(2024, 6, 1),
            source_system="proxy_fundamentals",
        )
        session.flush()

        assert created is True
        assert existing.superseded_by_version_id == winner.instance_id
        assert winner.superseded_by_version_id is None
        assert winner.quarantined is False

    def test_non_overlapping_versions_both_remain_current(self, world, session):
        engine = world["engine"]
        stint1, _ = engine.ensure_relationship(
            "EMPLOYED_BY", world["person_id"], world["company_id"],
            properties={"title": "Engineer"},
            valid_from_date=date(2018, 1, 1), valid_to_date=date(2020, 1, 1),
            source_system="proxy_fundamentals",
        )
        session.flush()
        stint2, created = engine.ensure_relationship(
            "EMPLOYED_BY", world["person_id"], world["company_id"],
            properties={"title": "VP"},
            valid_from_date=date(2022, 1, 1), valid_to_date=None,
            source_system="proxy_fundamentals",
        )
        session.flush()

        assert created is True
        assert stint1.superseded_by_version_id is None
        assert stint2.superseded_by_version_id is None
        assert stint1.quarantined is False
        assert stint2.quarantined is False
        assert stint1.relationship_id == stint2.relationship_id


class TestDirectVsDerived:
    def test_default_relationship_kind_is_direct(self, world):
        row, _ = world["engine"].ensure_relationship(
            "EMPLOYED_BY", world["person_id"], world["company_id"],
            properties={"title": "CEO"}, source_system="proxy_fundamentals",
        )
        assert row.relationship_kind == "direct"

    def test_relationship_kind_can_be_declared_derived(self, world):
        row, _ = world["engine"].ensure_relationship(
            "EMPLOYED_BY", world["person_id"], world["company_id"],
            properties={"title": "CEO"}, source_system="proxy_fundamentals",
            relationship_kind="derived",
        )
        assert row.relationship_kind == "derived"


class TestNoPhysicalDelete:
    def test_no_delete_function_is_exposed(self):
        public_names = [n for n in dir(graph_module) if not n.startswith("_")]
        assert not any("delete" in n.lower() for n in public_names)

    def test_close_supersede_quarantine_never_remove_the_row(self, world, session):
        engine = world["engine"]
        row, _ = engine.ensure_relationship(
            "EMPLOYED_BY", world["person_id"], world["company_id"],
            properties={"title": "CEO"}, valid_from_date=date(2024, 1, 1),
            source_system="proxy_fundamentals",
        )
        session.flush()
        instance_id = row.instance_id

        close_relationship_version(session, instance_id, date(2025, 1, 1))
        assert session.get(MdmRelationshipInstance, instance_id) is not None

        other, _ = engine.ensure_relationship(
            "EMPLOYED_BY", world["person_id"], world["company_id"],
            properties={"title": "President"}, valid_from_date=date(2025, 1, 1),
            source_system="proxy_fundamentals",
        )
        session.flush()
        supersede_relationship_version(session, instance_id, other.instance_id)
        assert session.get(MdmRelationshipInstance, instance_id) is not None
        assert session.get(MdmRelationshipInstance, instance_id).superseded_by_version_id == other.instance_id

        quarantine_relationship_version(session, other.instance_id, "manual test quarantine")
        reloaded = session.get(MdmRelationshipInstance, other.instance_id)
        assert reloaded is not None
        assert reloaded.quarantined is True
        assert reloaded.quarantine_reason == "manual test quarantine"
