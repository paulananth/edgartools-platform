"""Integration tests for MDMPipeline.run_relationships().

Exercises the bronze-layer relationship ingestion code added on top of the
existing resolver-based pipeline:

  * IS_INSIDER       (person  -> company,  Form 3/4/5)
  * IS_ENTITY_OF     (adviser -> company,  via MdmAdviser.linked_company_entity_id)
  * IS_PERSON_OF     (adviser -> person,   adviser CIK matches person owner_cik)

The test seeds an in-memory SQLite store with all five MDM entity-type
definitions, all five relationship types (matching the production seed
in edgar_warehouse/mdm/migrations/runtime.py), and a small amount of
domain data. A stub SilverReader returns canned rows for the two queries
issued by run_relationships.

No Neo4j is involved — sync_pending() is exercised separately in
test_graph.py with a real Neo4jGraphClient. Here we verify only the
PostgreSQL/SQL-mirror layer.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.mdm.database import (
    Base,
    MdmAdviser,
    MdmCompany,
    MdmEntity,
    MdmEntityTypeDefinition,
    MdmFund,
    MdmPerson,
    MdmRelationshipInstance,
    MdmRelationshipType,
    MdmSecurity,
    MdmSourceRef,
)
from edgar_warehouse.mdm.pipeline import MDMPipeline, _derive_role


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class StubSilver:
    """Returns canned rows keyed by a substring of the SQL."""

    def __init__(self, fixtures: dict[str, list[dict]]):
        self._fixtures = fixtures

    def fetch(self, sql: str, params: Optional[list[Any]] = None) -> list[dict]:
        for needle, rows in self._fixtures.items():
            if needle in sql:
                return list(rows)
        return []


def _seed_registry(session: Session) -> dict[str, str]:
    """Seed all 5 entity-type definitions + all 5 rel types."""
    entity_types = [
        ("company",  "Company",  "mdm_company"),
        ("adviser",  "Adviser",  "mdm_adviser"),
        ("person",   "Person",   "mdm_person"),
        ("security", "Security", "mdm_security"),
        ("fund",     "Fund",     "mdm_fund"),
    ]
    for et, label, table in entity_types:
        session.add(MdmEntityTypeDefinition(
            entity_type=et, neo4j_label=label, domain_table=table,
            api_path_prefix=f"/{et}s", primary_id_field="entity_id",
            display_name=label, is_active=True,
        ))

    rel_types = {}
    for name, src, tgt, strategy in [
        ("IS_INSIDER",   "person",   "company", "extend_temporal"),
        ("HOLDS",        "person",   "security", "extend_temporal"),
        ("ISSUED_BY",    "security", "company", "extend_temporal"),
        ("IS_ENTITY_OF", "adviser",  "company", "replace"),
        ("MANAGES_FUND", "adviser",  "fund",    "extend_temporal"),
        ("IS_PERSON_OF", "adviser",  "person",  "replace"),
    ]:
        rt_id = str(uuid.uuid4())
        session.add(MdmRelationshipType(
            rel_type_id=rt_id, rel_type_name=name,
            source_node_type=src, target_node_type=tgt,
            direction="outbound", is_temporal=True,
            merge_strategy=strategy, is_active=True,
        ))
        rel_types[name] = rt_id
    session.commit()
    return rel_types


def _add_entity(session: Session, entity_type: str) -> str:
    eid = str(uuid.uuid4())
    session.add(MdmEntity(entity_id=eid, entity_type=entity_type))
    session.flush()
    return eid


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sess = Session(engine)
    _seed_registry(sess)
    yield sess
    sess.close()


@pytest.fixture
def fixture_world(session: Session) -> dict:
    """Seed a small fixed world:
      * 2 companies (synthetic CIKs 910001 = Issuer Corp, 910002 = Linked Corp)
      * 1 individual adviser linked to no company, synthetic CIK 910101
      * 1 firm-style adviser linked to Linked Corp (linked_company_entity_id)
      * 1 person whose owner_cik == 910101 (matches the individual adviser)
      * 1 person whose owner_cik == 910102 (insider only, no adviser link)
    """
    issuer_company_id = _add_entity(session, "company")
    linked_company_id  = _add_entity(session, "company")
    session.add_all([
        MdmCompany(entity_id=issuer_company_id, cik=910001, canonical_name="Issuer Corp"),
        MdmCompany(entity_id=linked_company_id,  cik=910002, canonical_name="Linked Corp"),
    ])

    individual_adviser_id = _add_entity(session, "adviser")
    firm_adviser_id  = _add_entity(session, "adviser")
    session.add_all([
        MdmAdviser(entity_id=individual_adviser_id, cik=910101,
                   canonical_name="Individual Adviser (RIA)",
                   linked_company_entity_id=None),
        MdmAdviser(entity_id=firm_adviser_id, cik=910002,
                   canonical_name="Linked Asset Mgmt",
                   linked_company_entity_id=linked_company_id),
    ])
    # Source ref so _adviser_entity_id() can resolve from accession_number
    session.add(MdmSourceRef(
        entity_id=firm_adviser_id, source_system="adv_filing",
        source_id="0001-linked-adv", source_priority=2,
    ))

    reporting_person_id = _add_entity(session, "person")
    individual_person_id   = _add_entity(session, "person")
    session.add_all([
        MdmPerson(entity_id=reporting_person_id, owner_cik=910102,
                  canonical_name="Reporting Person"),
        MdmPerson(entity_id=individual_person_id, owner_cik=910101,
                  canonical_name="Individual Person"),
    ])

    fund_entity_id = _add_entity(session, "fund")
    session.add(MdmFund(
        entity_id=fund_entity_id,
        adviser_entity_id=firm_adviser_id,
        canonical_name="Linked Growth Fund",
    ))
    security_entity_id = _add_entity(session, "security")
    session.add(MdmSecurity(
        entity_id=security_entity_id,
        issuer_entity_id=issuer_company_id,
        canonical_title="Common Stock",
    ))

    session.commit()
    return {
        "issuer_company_id": issuer_company_id, "linked_company_id": linked_company_id,
        "individual_adviser_id": individual_adviser_id, "firm_adviser_id": firm_adviser_id,
        "reporting_person_id": reporting_person_id,
        "individual_person_id": individual_person_id,
        "fund_entity_id": fund_entity_id,
        "security_entity_id": security_entity_id,
    }


# ---------------------------------------------------------------------------
# Helper-method tests
# ---------------------------------------------------------------------------

class TestPipelineHelpers:
    def test_company_cik_set(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=StubSilver({}))
        assert pipe._company_cik_set() == {910001, 910002}

    def test_company_entity_id_resolves(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=StubSilver({}))
        assert pipe._company_entity_id(910001) == fixture_world["issuer_company_id"]
        assert pipe._company_entity_id(999999) is None
        assert pipe._company_entity_id(None)   is None

    def test_person_entity_id_by_cik(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=StubSilver({}))
        assert pipe._person_entity_id(910102, "Reporting Person") == fixture_world["reporting_person_id"]

    def test_person_entity_id_by_name_fallback(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=StubSilver({}))
        # No CIK match -> falls back to canonical_name
        assert pipe._person_entity_id(None, "Individual Person") == fixture_world["individual_person_id"]
        assert pipe._person_entity_id(None, "No Such Person") is None

    def test_adviser_entity_id_via_source_ref(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=StubSilver({}))
        assert pipe._adviser_entity_id("0001-linked-adv") == fixture_world["firm_adviser_id"]
        assert pipe._adviser_entity_id("nonexistent-acc") is None
        assert pipe._adviser_entity_id(None) is None

    def test_adviser_company_pairs(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=StubSilver({}))
        pairs = list(pipe._adviser_company_pairs())
        assert len(pairs) == 1
        adv_id, co_id = pairs[0]
        assert adv_id == fixture_world["firm_adviser_id"]
        assert co_id  == fixture_world["linked_company_id"]

    def test_adviser_person_pairs_only_unlinked(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=StubSilver({}))
        pairs = list(pipe._adviser_person_pairs())
        # firm adviser is excluded (linked_company_entity_id is set)
        assert len(pairs) == 1
        adv_id, person_id = pairs[0]
        assert adv_id    == fixture_world["individual_adviser_id"]
        assert person_id == fixture_world["individual_person_id"]


# ---------------------------------------------------------------------------
# _derive_role
# ---------------------------------------------------------------------------

class TestDeriveRole:
    @pytest.mark.parametrize("flags, expected", [
        ({"is_director": True}, "director"),
        ({"is_director": False, "is_officer": True}, "officer"),
        ({"is_director": False, "is_officer": False, "is_ten_percent_owner": True}, "10pct_owner"),
        ({"is_director": False, "is_officer": False, "is_ten_percent_owner": False, "is_other": True}, "other"),
        ({}, "other"),
    ])
    def test_role_precedence(self, flags, expected):
        assert _derive_role(flags) == expected


# ---------------------------------------------------------------------------
# run_relationships()
# ---------------------------------------------------------------------------

class TestRunRelationships:
    def _stub(self) -> StubSilver:
        # Two SQL queries land in run_relationships:
        #  - SELECT ... FROM sec_ownership_reporting_owner ... (for IS_INSIDER)
        # The MANAGES_FUND/ISSUED_BY backfill is a no-op without funds/securities.
        owner_rows = [
            # Reporting Person -> Issuer Corp, director
            {
                "accession_number": "0000-issuer-1",
                "owner_index": 0,
                "owner_cik": 910102,
                "owner_name": "Reporting Person",
                "is_director": True,
                "is_officer": False,
                "is_ten_percent_owner": False,
                "is_other": False,
                "officer_title": None,
                "issuer_cik": 910001,
                "period_of_report": None,
            },
            # Individual Person -> Linked Corp, officer
            {
                "accession_number": "0000-linked-1",
                "owner_index": 0,
                "owner_cik": 910101,
                "owner_name": "Individual Person",
                "is_director": False,
                "is_officer": True,
                "is_ten_percent_owner": False,
                "is_other": False,
                "officer_title": "CFO",
                "issuer_cik": 910002,
                "period_of_report": None,
            },
            # Corporate beneficial owner — owner_cik IS a known company. Must skip.
            {
                "accession_number": "0000-corp-1",
                "owner_index": 1,
                "owner_cik": 910001,        # Issuer Corp's synthetic CIK
                "owner_name": "Issuer Corp",
                "is_director": False,
                "is_officer": False,
                "is_ten_percent_owner": True,
                "is_other": False,
                "officer_title": None,
                "issuer_cik": 910002,
                "period_of_report": None,
            },
        ]
        return StubSilver({
            "FROM sec_ownership_reporting_owner": owner_rows,
        })

    def test_writes_is_insider_for_natural_persons(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=self._stub())
        written = pipe.run_relationships()

        rows = list(session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "IS_INSIDER")
        ))
        # Two natural-person rows, corporate beneficial owner skipped
        assert len(rows) == 2
        assert written >= 2

        pairs = {(r.source_entity_id, r.target_entity_id) for r in rows}
        assert (fixture_world["reporting_person_id"], fixture_world["issuer_company_id"]) in pairs
        assert (fixture_world["individual_person_id"],   fixture_world["linked_company_id"])  in pairs

    def test_skips_corporate_beneficial_owner(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=self._stub())
        pipe.run_relationships()

        rows = list(session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "IS_INSIDER")
        ))
        # No row should target_entity = linked company from owner_cik = Issuer Corp
        assert all(
            not (r.source_entity_id == fixture_world["issuer_company_id"]
                 and r.target_entity_id == fixture_world["linked_company_id"])
            for r in rows
        )

    def test_writes_is_entity_of(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=self._stub())
        pipe.run_relationships()

        rows = list(session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "IS_ENTITY_OF")
        ))
        assert len(rows) == 1
        assert rows[0].source_entity_id == fixture_world["firm_adviser_id"]
        assert rows[0].target_entity_id == fixture_world["linked_company_id"]

    def test_writes_is_person_of(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=self._stub())
        pipe.run_relationships()

        rows = list(session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "IS_PERSON_OF")
        ))
        assert len(rows) == 1
        assert rows[0].source_entity_id == fixture_world["individual_adviser_id"]
        assert rows[0].target_entity_id == fixture_world["individual_person_id"]

    def test_returned_count_matches_inserts(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=self._stub())
        written = pipe.run_relationships()
        # 2 IS_INSIDER + 1 IS_ENTITY_OF + 1 IS_PERSON_OF + 1 MANAGES_FUND + 1 ISSUED_BY = 6
        assert written == 6

    def test_properties_include_role_and_title(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=self._stub())
        pipe.run_relationships()

        rows = list(session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "IS_INSIDER")
        ))
        by_source = {r.source_entity_id: r for r in rows}
        director_row = by_source[fixture_world["reporting_person_id"]]
        officer_row = by_source[fixture_world["individual_person_id"]]

        assert director_row.properties.get("role") == "director"
        assert officer_row.properties.get("role") == "officer"
        assert officer_row.properties.get("title") == "CFO"
        assert director_row.source_system == "ownership_filing"
        assert director_row.source_accession == "0000-issuer-1"

    def test_writes_holds_from_non_derivative_transactions(self, session, fixture_world):
        security_id = _add_entity(session, "security")
        session.add(MdmSecurity(
            entity_id=security_id,
            issuer_entity_id=fixture_world["issuer_company_id"],
            canonical_title="Common Stock",
            security_type="common_stock",
        ))
        session.add(MdmSourceRef(
            entity_id=security_id,
            source_system="ownership_filing",
            source_id="0000-issuer-1:0:0",
            source_priority=3,
        ))
        session.commit()
        pipe = MDMPipeline(session=session, silver=StubSilver({
            "FROM sec_ownership_reporting_owner": [],
            "FROM sec_ownership_non_derivative_txn": [
                {
                    "accession_number": "0000-issuer-1",
                    "owner_index": 0,
                    "txn_index": 0,
                    "security_title": "Common Stock",
                    "transaction_date": None,
                    "shares_owned_after": 10,
                    "ownership_direct_indirect": "D",
                    "owner_cik": 910102,
                    "owner_name": "Reporting Person",
                    "issuer_cik": 910001,
                }
            ],
        }))

        summary = pipe.derive_relationships(target_per_type=1, relationship_types=["HOLDS"])

        rows = list(session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "HOLDS")
        ))
        assert summary["HOLDS"]["inserted"] == 1
        assert len(rows) == 1
        assert rows[0].source_entity_id == fixture_world["reporting_person_id"]
        assert rows[0].target_entity_id == security_id
        assert rows[0].properties["shares_owned"] == 10
        assert rows[0].properties["direct_indirect"] == "D"

    def test_relationship_derivation_is_idempotent(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=self._stub())

        first = pipe.run_relationships()
        second = pipe.run_relationships()

        assert first == 6
        assert second == 0
        rows = list(session.scalars(select(MdmRelationshipInstance)))
        assert len(rows) == 6

    def test_target_per_type_counts_existing_rows(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=self._stub())

        first = pipe.derive_relationships(target_per_type=1, relationship_types=["IS_INSIDER"])
        second = pipe.derive_relationships(target_per_type=1, relationship_types=["IS_INSIDER"])

        assert first["IS_INSIDER"]["inserted"] == 1
        assert first["IS_INSIDER"]["total"] == 1
        assert second["IS_INSIDER"]["existing"] == 1
        assert second["IS_INSIDER"]["inserted"] == 0

    def test_writes_manages_fund_relationship(self, session, fixture_world):
        """MANAGES_FUND deriver inserts exactly 1 row when fixture_world has 1 MdmFund. (D-01, D-02, REL-03)"""
        pipe = MDMPipeline(session=session, silver=StubSilver({}))
        summary = pipe.derive_relationships(relationship_types=["MANAGES_FUND"])
        assert summary["MANAGES_FUND"]["inserted"] == 1
        assert summary["MANAGES_FUND"]["skipped_existing"] == 0
        assert summary["MANAGES_FUND"]["skipped"] == (
            summary["MANAGES_FUND"]["skipped_corporate"]
            + summary["MANAGES_FUND"]["skipped_unresolved_source"]
            + summary["MANAGES_FUND"]["skipped_unresolved_target"]
            + summary["MANAGES_FUND"]["skipped_existing"]
        )

    def test_writes_issued_by_relationship(self, session, fixture_world):
        """ISSUED_BY deriver inserts exactly 1 row when fixture_world has 1 qualifying MdmSecurity. (D-01, D-02, REL-02)"""
        pipe = MDMPipeline(session=session, silver=StubSilver({}))
        summary = pipe.derive_relationships(relationship_types=["ISSUED_BY"])
        assert summary["ISSUED_BY"]["inserted"] == 1
        assert summary["ISSUED_BY"]["skipped_existing"] == 0
        assert summary["ISSUED_BY"]["skipped"] == (
            summary["ISSUED_BY"]["skipped_corporate"]
            + summary["ISSUED_BY"]["skipped_unresolved_source"]
            + summary["ISSUED_BY"]["skipped_unresolved_target"]
            + summary["ISSUED_BY"]["skipped_existing"]
        )

    def test_all_six_types_idempotent(self, session, fixture_world):
        """Running derive_relationships() twice inserts 0 rows on second run for all 6 types. (D-04, REL-04)"""
        session.add(MdmSourceRef(
            entity_id=fixture_world["security_entity_id"],
            source_system="ownership_filing",
            source_id="0000-issuer-1:0:0",
            source_priority=3,
        ))
        session.commit()

        silver = StubSilver({
            "FROM sec_ownership_reporting_owner": [
                {
                    "accession_number": "0000-issuer-1", "owner_index": 0,
                    "owner_cik": 910102, "owner_name": "Reporting Person",
                    "is_director": True, "is_officer": False,
                    "is_ten_percent_owner": False, "is_other": False,
                    "officer_title": None, "issuer_cik": 910001, "period_of_report": None,
                },
            ],
            "FROM sec_ownership_non_derivative_txn": [
                {
                    "accession_number": "0000-issuer-1", "owner_index": 0, "txn_index": 0,
                    "security_title": "Common Stock", "transaction_date": None,
                    "shares_owned_after": 10, "ownership_direct_indirect": "D",
                    "owner_cik": 910102, "owner_name": "Reporting Person",
                    "issuer_cik": 910001,
                },
            ],
        })
        pipe = MDMPipeline(session=session, silver=silver)

        ALL_SIX = ["IS_INSIDER", "HOLDS", "ISSUED_BY", "MANAGES_FUND", "IS_ENTITY_OF", "IS_PERSON_OF"]
        first = pipe.derive_relationships()
        second = pipe.derive_relationships()

        assert first["IS_INSIDER"]["inserted"] >= 1
        assert first["HOLDS"]["inserted"] == 1
        assert first["ISSUED_BY"]["inserted"] == 1
        assert first["MANAGES_FUND"]["inserted"] == 1
        assert first["IS_ENTITY_OF"]["inserted"] == 1
        assert first["IS_PERSON_OF"]["inserted"] == 1

        for rt in ALL_SIX:
            assert second[rt]["inserted"] == 0, (
                f"Expected 0 inserts on second run for {rt}, got {second[rt]['inserted']}"
            )

        for rt in ALL_SIX:
            assert second[rt]["skipped"] == (
                second[rt]["skipped_corporate"]
                + second[rt]["skipped_unresolved_source"]
                + second[rt]["skipped_unresolved_target"]
                + second[rt]["skipped_existing"]
            ), f"skipped backward-compat broken for {rt}"
