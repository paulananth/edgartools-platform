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
    MdmPerson,
    MdmRelationshipInstance,
    MdmRelationshipType,
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
      * 2 companies (CIK 320193 = Apple, CIK 789019 = Microsoft)
      * 1 individual adviser linked to no company, CIK 111111
      * 1 firm-style adviser linked to Microsoft (linked_company_entity_id)
      * 1 person whose owner_cik == 111111 (matches the individual adviser)
      * 1 person whose owner_cik == 222222 (insider only, no adviser link)
    """
    apple_id = _add_entity(session, "company")
    msft_id  = _add_entity(session, "company")
    session.add_all([
        MdmCompany(entity_id=apple_id, cik=320193, canonical_name="Apple Inc"),
        MdmCompany(entity_id=msft_id,  cik=789019, canonical_name="Microsoft Corp"),
    ])

    indiv_adv_id = _add_entity(session, "adviser")
    firm_adv_id  = _add_entity(session, "adviser")
    session.add_all([
        MdmAdviser(entity_id=indiv_adv_id, cik=111111,
                   canonical_name="Jane Doe (RIA)",
                   linked_company_entity_id=None),
        MdmAdviser(entity_id=firm_adv_id, cik=789019,
                   canonical_name="Microsoft Asset Mgmt",
                   linked_company_entity_id=msft_id),
    ])
    # Source ref so _adviser_entity_id() can resolve from accession_number
    session.add(MdmSourceRef(
        entity_id=firm_adv_id, source_system="adv_filing",
        source_id="0001-msft-adv", source_priority=2,
    ))

    insider_person_id = _add_entity(session, "person")
    indiv_person_id   = _add_entity(session, "person")
    session.add_all([
        MdmPerson(entity_id=insider_person_id, owner_cik=222222,
                  canonical_name="Tim Cook"),
        MdmPerson(entity_id=indiv_person_id, owner_cik=111111,
                  canonical_name="Jane Doe"),
    ])

    session.commit()
    return {
        "apple_id": apple_id, "msft_id": msft_id,
        "indiv_adv_id": indiv_adv_id, "firm_adv_id": firm_adv_id,
        "insider_person_id": insider_person_id,
        "indiv_person_id": indiv_person_id,
    }


# ---------------------------------------------------------------------------
# Helper-method tests
# ---------------------------------------------------------------------------

class TestPipelineHelpers:
    def test_company_cik_set(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=StubSilver({}))
        assert pipe._company_cik_set() == {320193, 789019}

    def test_company_entity_id_resolves(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=StubSilver({}))
        assert pipe._company_entity_id(320193) == fixture_world["apple_id"]
        assert pipe._company_entity_id(999999) is None
        assert pipe._company_entity_id(None)   is None

    def test_person_entity_id_by_cik(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=StubSilver({}))
        assert pipe._person_entity_id(222222, "Tim Cook") == fixture_world["insider_person_id"]

    def test_person_entity_id_by_name_fallback(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=StubSilver({}))
        # No CIK match -> falls back to canonical_name
        assert pipe._person_entity_id(None, "Jane Doe") == fixture_world["indiv_person_id"]
        assert pipe._person_entity_id(None, "No Such Person") is None

    def test_adviser_entity_id_via_source_ref(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=StubSilver({}))
        assert pipe._adviser_entity_id("0001-msft-adv") == fixture_world["firm_adv_id"]
        assert pipe._adviser_entity_id("nonexistent-acc") is None
        assert pipe._adviser_entity_id(None) is None

    def test_adviser_company_pairs(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=StubSilver({}))
        pairs = list(pipe._adviser_company_pairs())
        assert len(pairs) == 1
        adv_id, co_id = pairs[0]
        assert adv_id == fixture_world["firm_adv_id"]
        assert co_id  == fixture_world["msft_id"]

    def test_adviser_person_pairs_only_unlinked(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=StubSilver({}))
        pairs = list(pipe._adviser_person_pairs())
        # firm adviser is excluded (linked_company_entity_id is set)
        assert len(pairs) == 1
        adv_id, person_id = pairs[0]
        assert adv_id    == fixture_world["indiv_adv_id"]
        assert person_id == fixture_world["indiv_person_id"]


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
            # Tim Cook -> Apple, director
            {
                "accession_number": "0000-apple-1",
                "owner_index": 0,
                "owner_cik": 222222,
                "owner_name": "Tim Cook",
                "is_director": True,
                "is_officer": False,
                "is_ten_percent_owner": False,
                "is_other": False,
                "officer_title": None,
                "issuer_cik": 320193,
                "period_of_report": None,
            },
            # Jane Doe -> Microsoft, officer
            {
                "accession_number": "0000-msft-1",
                "owner_index": 0,
                "owner_cik": 111111,
                "owner_name": "Jane Doe",
                "is_director": False,
                "is_officer": True,
                "is_ten_percent_owner": False,
                "is_other": False,
                "officer_title": "CFO",
                "issuer_cik": 789019,
                "period_of_report": None,
            },
            # Corporate beneficial owner — owner_cik IS a known company. Must skip.
            {
                "accession_number": "0000-corp-1",
                "owner_index": 1,
                "owner_cik": 320193,        # Apple's CIK
                "owner_name": "Apple Inc",
                "is_director": False,
                "is_officer": False,
                "is_ten_percent_owner": True,
                "is_other": False,
                "officer_title": None,
                "issuer_cik": 789019,
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
        assert (fixture_world["insider_person_id"], fixture_world["apple_id"]) in pairs
        assert (fixture_world["indiv_person_id"],   fixture_world["msft_id"])  in pairs

    def test_skips_corporate_beneficial_owner(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=self._stub())
        pipe.run_relationships()

        rows = list(session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "IS_INSIDER")
        ))
        # No row should target_entity = msft from owner_cik = Apple
        assert all(
            not (r.source_entity_id == fixture_world["apple_id"]
                 and r.target_entity_id == fixture_world["msft_id"])
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
        assert rows[0].source_entity_id == fixture_world["firm_adv_id"]
        assert rows[0].target_entity_id == fixture_world["msft_id"]

    def test_writes_is_person_of(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=self._stub())
        pipe.run_relationships()

        rows = list(session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "IS_PERSON_OF")
        ))
        assert len(rows) == 1
        assert rows[0].source_entity_id == fixture_world["indiv_adv_id"]
        assert rows[0].target_entity_id == fixture_world["indiv_person_id"]

    def test_returned_count_matches_inserts(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=self._stub())
        written = pipe.run_relationships()
        # 2 IS_INSIDER + 1 IS_ENTITY_OF + 1 IS_PERSON_OF = 4
        assert written == 4

    def test_properties_include_role_and_title(self, session, fixture_world):
        pipe = MDMPipeline(session=session, silver=self._stub())
        pipe.run_relationships()

        rows = list(session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "IS_INSIDER")
        ))
        by_source = {r.source_entity_id: r for r in rows}
        cook_row = by_source[fixture_world["insider_person_id"]]
        jane_row = by_source[fixture_world["indiv_person_id"]]

        assert cook_row.properties.get("role") == "director"
        assert jane_row.properties.get("role") == "officer"
        assert jane_row.properties.get("title") == "CFO"
        assert cook_row.source_system == "ownership_filing"
        assert cook_row.source_accession == "0000-apple-1"
