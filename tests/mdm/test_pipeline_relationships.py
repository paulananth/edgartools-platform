"""Integration tests for MDMPipeline.run_relationships().

Exercises the bronze-layer relationship ingestion code added on top of the
existing resolver-based pipeline:

  * IS_INSIDER       (person  -> company,  Form 3/4/5)
  * IS_ENTITY_OF     (adviser -> company,  via MdmAdviser.linked_company_entity_id)
  * IS_PERSON_OF     (adviser -> person,   adviser CIK matches person owner_cik)

The test seeds an in-memory SQLite store with all five MDM entity-type
definitions and graph relationship types (matching the production seed
in edgar_warehouse/mdm/migrations/runtime.py), and a small amount of
domain data. A stub SilverReader returns canned rows for the two queries
issued by run_relationships.

No Neo4j is involved — sync_pending() is exercised separately in
test_graph.py with a real Neo4jGraphClient. Here we verify only the
PostgreSQL/SQL-mirror layer.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Optional

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.mdm.database import (
    Base,
    MdmAdviser,
    MdmAuditFirm,
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
        self.queries: list[str] = []

    def fetch(self, sql: str, params: Optional[list[Any]] = None) -> list[dict]:
        self.queries.append(sql)
        matched: list[dict] = []
        transaction_query = (
            "sec_ownership_non_derivative_txn" in sql
            or "sec_ownership_derivative_txn" in sql
        )
        for needle, rows in self._fixtures.items():
            if transaction_query and needle == "FROM sec_ownership_reporting_owner":
                continue
            if needle in sql:
                matched.extend(rows)
        return matched


class MissingTableSilver(StubSilver):
    def __init__(self, table_name: str):
        super().__init__({})
        self._table_name = table_name

    def fetch(self, sql: str, params: Optional[list[Any]] = None) -> list[dict]:
        if self._table_name in sql:
            self.queries.append(sql)
            raise RuntimeError(f"Catalog Error: Table with name {self._table_name} does not exist!")
        return super().fetch(sql, params)


def _seed_registry(session: Session) -> dict[str, str]:
    """Seed all 5 entity-type definitions + graph relationship types."""
    entity_types = [
        ("company",    "Company",    "mdm_company"),
        ("adviser",    "Adviser",    "mdm_adviser"),
        ("person",     "Person",     "mdm_person"),
        ("security",   "Security",   "mdm_security"),
        ("fund",       "Fund",       "mdm_fund"),
        ("audit_firm", "AuditFirm",  "mdm_audit_firm"),
    ]
    for et, label, table in entity_types:
        session.add(MdmEntityTypeDefinition(
            entity_type=et, neo4j_label=label, domain_table=table,
            api_path_prefix=f"/{et}s", primary_id_field="entity_id",
            display_name=label, is_active=True,
        ))

    rel_types = {}
    for name, src, tgt, strategy in [
        ("IS_INSIDER",          "person",   "company",     "extend_temporal"),
        ("HOLDS",               "person",   "security",    "extend_temporal"),
        ("COMPANY_HOLDS",       "company",  "security",    "extend_temporal"),
        ("ISSUED_BY",           "security", "company",     "extend_temporal"),
        ("IS_ENTITY_OF",        "adviser",  "company",     "replace"),
        ("HAS_PARENT_COMPANY",  "company",  "company",     "replace"),
        ("MANAGES_FUND",        "adviser",  "fund",        "extend_temporal"),
        ("IS_PERSON_OF",        "adviser",  "person",      "replace"),
        # Fundamentals-sourced types (sec_executive_record, sec_accounting_flag, sec_thirteenf_holding)
        ("EMPLOYED_BY",         "person",   "company",     "extend_temporal"),
        ("AUDITED_BY",          "company",  "audit_firm",  "extend_temporal"),
        ("INSTITUTIONAL_HOLDS", "adviser",  "security",    "extend_temporal"),
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

    # Seed one audit firm so _audit_firm_entity_id(pcaob_id="E1") resolves in AUDITED_BY tests
    audit_firm_entity_id = _add_entity(session, "audit_firm")
    session.add(MdmAuditFirm(
        entity_id=audit_firm_entity_id,
        firm_name="Deloitte LLP",
        canonical_name="Deloitte LLP",
        pcaob_firm_id="E1",
        big4=True,
    ))

    session.commit()
    return {
        "issuer_company_id": issuer_company_id, "linked_company_id": linked_company_id,
        "individual_adviser_id": individual_adviser_id, "firm_adviser_id": firm_adviser_id,
        "reporting_person_id": reporting_person_id,
        "individual_person_id": individual_person_id,
        "fund_entity_id": fund_entity_id,
        "security_entity_id": security_entity_id,
        "audit_firm_entity_id": audit_firm_entity_id,
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

    def test_writes_has_parent_company_relationship(self, session, fixture_world):
        child_id = _add_entity(session, "company")
        session.add(MdmCompany(
            entity_id=child_id,
            cik=910003,
            canonical_name="Child Corp",
            ticker="CHLD",
            parent_company_entity_id=fixture_world["linked_company_id"],
        ))
        session.commit()
        pipe = MDMPipeline(session=session, silver=StubSilver({}))

        summary = pipe.derive_relationships(relationship_types=["HAS_PARENT_COMPANY"])

        rows = list(session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "HAS_PARENT_COMPANY")
        ))
        assert summary["HAS_PARENT_COMPANY"]["inserted"] == 1
        assert len(rows) == 1
        assert rows[0].source_entity_id == child_id
        assert rows[0].target_entity_id == fixture_world["linked_company_id"]

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
        assert rows[0].properties["is_derivative"] is False

    def test_writes_company_holds_for_corporate_reporting_owner(self, session, fixture_world):
        session.add(MdmSourceRef(
            entity_id=fixture_world["security_entity_id"],
            source_system="ownership_filing",
            source_id="0000-corp-1:1:0",
            source_priority=3,
        ))
        session.commit()
        pipe = MDMPipeline(session=session, silver=StubSilver({
            "FROM sec_ownership_non_derivative_txn": [
                {
                    "accession_number": "0000-corp-1",
                    "owner_index": 1,
                    "txn_index": 0,
                    "security_title": "Common Stock",
                    "transaction_date": None,
                    "shares_owned_after": 25,
                    "ownership_direct_indirect": "I",
                    "owner_cik": 910002,
                    "owner_name": "Linked Corp",
                    "issuer_cik": 910001,
                }
            ],
        }))

        summary = pipe.derive_relationships(target_per_type=1, relationship_types=["COMPANY_HOLDS"])

        rows = list(session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "COMPANY_HOLDS")
        ))
        assert summary["COMPANY_HOLDS"]["inserted"] == 1
        assert len(rows) == 1
        assert rows[0].source_entity_id == fixture_world["linked_company_id"]
        assert rows[0].target_entity_id == fixture_world["security_entity_id"]
        assert rows[0].properties["shares_owned"] == 25
        assert rows[0].properties["is_derivative"] is False

    def test_writes_holds_from_derivative_transactions(self, session, fixture_world):
        derivative_security_id = _add_entity(session, "security")
        session.add(MdmSecurity(
            entity_id=derivative_security_id,
            issuer_entity_id=fixture_world["issuer_company_id"],
            canonical_title="Option",
            security_type="option",
        ))
        session.add(MdmSourceRef(
            entity_id=derivative_security_id,
            source_system="ownership_filing",
            source_id="0000-issuer-derivative:derivative:0:0",
            source_priority=3,
        ))
        session.commit()
        pipe = MDMPipeline(session=session, silver=StubSilver({
            "FROM sec_ownership_non_derivative_txn": [],
            "FROM sec_ownership_derivative_txn": [
                {
                    "accession_number": "0000-issuer-derivative",
                    "owner_index": 0,
                    "txn_index": 0,
                    "security_title": "Option",
                    "transaction_date": None,
                    "shares_owned_after": 5,
                    "ownership_direct_indirect": "D",
                    "is_derivative": True,
                    "conversion_or_exercise_price": 12.5,
                    "exercise_date": None,
                    "expiration_date": None,
                    "underlying_security_title": "Common Stock",
                    "underlying_security_shares": 5,
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
        assert rows[0].target_entity_id == derivative_security_id
        assert rows[0].properties["is_derivative"] is True
        assert rows[0].properties["conversion_or_exercise_price"] == 12.5
        assert rows[0].properties["underlying_security_title"] == "Common Stock"

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

    def test_target_per_type_bounds_relationship_source_query(self, session, fixture_world):
        silver = self._stub()
        pipe = MDMPipeline(session=session, silver=silver)

        pipe.derive_relationships(target_per_type=1, relationship_types=["IS_INSIDER"])

        source_queries = [
            query for query in silver.queries
            if "FROM sec_ownership_reporting_owner" in query
        ]
        assert source_queries
        assert " LIMIT " in source_queries[0].upper()

    def test_optional_fundamentals_source_table_missing_is_empty(self, session):
        silver = MissingTableSilver("sec_executive_record")
        pipe = MDMPipeline(session=session, silver=silver)

        summary = pipe.derive_relationships(target_per_type=1, relationship_types=["EMPLOYED_BY"])

        assert summary["EMPLOYED_BY"]["inserted"] == 0
        assert summary["EMPLOYED_BY"]["skipped"] == 0
        assert any("sec_executive_record" in query for query in silver.queries)

    # ------------------------------------------------------------------
    # EMPLOYED_BY tests (T2 — 06-02)
    # ------------------------------------------------------------------

    def test_writes_employed_by_relationship(self, session, fixture_world):
        """EMPLOYED_BY inserts 1 row from sec_executive_record for a resolved company. (06-02)"""
        silver = StubSilver({
            "sec_executive_record": [
                {
                    "cik": 910001, "accession_number": "0000-issuer-1",
                    "fiscal_year": 2023, "exec_name": "Jane CEO", "exec_role": "CEO",
                    "total_comp": 5000000, "base_salary": 1000000, "bonus": 500000,
                    "stock_awards": 3000000, "option_awards": None,
                    "non_equity_incentive": 500000, "tenure_start_year": 2020,
                },
            ],
        })
        pipe = MDMPipeline(session=session, silver=silver)
        summary = pipe.derive_relationships(relationship_types=["EMPLOYED_BY"])
        assert summary["EMPLOYED_BY"]["inserted"] == 1
        assert summary["EMPLOYED_BY"]["skipped_unresolved_target"] == 0
        assert summary["EMPLOYED_BY"]["skipped"] == (
            summary["EMPLOYED_BY"]["skipped_corporate"]
            + summary["EMPLOYED_BY"]["skipped_unresolved_source"]
            + summary["EMPLOYED_BY"]["skipped_unresolved_target"]
            + summary["EMPLOYED_BY"]["skipped_existing"]
        )

    # ------------------------------------------------------------------
    # AUDITED_BY tests (T3 — 06-02)
    # ------------------------------------------------------------------

    def test_writes_audited_by_relationship(self, session, fixture_world):
        """AUDITED_BY inserts 1 row when MdmAuditFirm resolves via PCAOB ID. (06-02)"""
        silver = StubSilver({
            "sec_accounting_flag": [
                {
                    "cik": 910001, "accession_number": "0000-issuer-1",
                    "fiscal_year": 2023, "period_end": None,
                    "auditor_pcaob_id": "E1", "auditor_name": "Deloitte LLP",
                    "icfr_attestation": True,
                },
            ],
        })
        pipe = MDMPipeline(session=session, silver=silver)
        summary = pipe.derive_relationships(relationship_types=["AUDITED_BY"])
        assert summary["AUDITED_BY"]["inserted"] == 1
        assert summary["AUDITED_BY"]["skipped_unresolved_target"] == 0
        assert summary["AUDITED_BY"]["skipped"] == (
            summary["AUDITED_BY"]["skipped_corporate"]
            + summary["AUDITED_BY"]["skipped_unresolved_source"]
            + summary["AUDITED_BY"]["skipped_unresolved_target"]
            + summary["AUDITED_BY"]["skipped_existing"]
        )

    def test_audited_by_change_detection(self, session, fixture_world):
        """AUDITED_BY: auditor_changed=True when fiscal_year N+1 has a different auditor. (06-02)"""
        # Seed a second audit firm for the change-detection rows
        pwc_entity_id = _add_entity(session, "audit_firm")
        session.add(MdmAuditFirm(
            entity_id=pwc_entity_id,
            firm_name="PricewaterhouseCoopers LLP",
            canonical_name="PricewaterhouseCoopers LLP",
            pcaob_firm_id="E2",
            big4=True,
        ))
        session.commit()

        silver = StubSilver({
            "sec_accounting_flag": [
                # FY2022: first row for CIK 910001 — no prev, auditor_changed must be False
                {
                    "cik": 910001, "accession_number": "acc-2022",
                    "fiscal_year": 2022, "period_end": None,
                    "auditor_pcaob_id": "E1", "auditor_name": "Deloitte LLP",
                    "icfr_attestation": True,
                },
                # FY2023: same CIK, different auditor — auditor_changed must be True
                {
                    "cik": 910001, "accession_number": "acc-2023",
                    "fiscal_year": 2023, "period_end": None,
                    "auditor_pcaob_id": "E2", "auditor_name": "PricewaterhouseCoopers LLP",
                    "icfr_attestation": True,
                },
            ],
        })
        pipe = MDMPipeline(session=session, silver=silver)
        summary = pipe.derive_relationships(relationship_types=["AUDITED_BY"])
        assert summary["AUDITED_BY"]["inserted"] == 2

        from sqlalchemy import select
        instances = session.scalars(
            select(MdmRelationshipInstance).order_by(MdmRelationshipInstance.effective_from)
        ).all()
        fy2022 = next(i for i in instances if i.properties.get("fiscal_year") == 2022)
        fy2023 = next(i for i in instances if i.properties.get("fiscal_year") == 2023)
        assert fy2022.properties["auditor_changed"] is False
        assert fy2023.properties["auditor_changed"] is True

    def test_optional_fundamentals_source_table_missing_audited_by(self, session):
        """AUDITED_BY: missing sec_accounting_flag → 0 rows, no exception. (06-02)"""
        silver = MissingTableSilver("sec_accounting_flag")
        pipe = MDMPipeline(session=session, silver=silver)
        summary = pipe.derive_relationships(
            target_per_type=1, relationship_types=["AUDITED_BY"]
        )
        assert summary["AUDITED_BY"]["inserted"] == 0
        assert summary["AUDITED_BY"]["skipped"] == 0
        assert any("sec_accounting_flag" in query for query in silver.queries)

    # ------------------------------------------------------------------
    # INSTITUTIONAL_HOLDS tests (T4 + T5 — 06-02)
    # ------------------------------------------------------------------

    def test_writes_institutional_holds_relationship(self, session, fixture_world):
        """INSTITUTIONAL_HOLDS inserts 1 row; security is auto-created via CUSIP. (06-02)"""
        silver = StubSilver({
            "sec_thirteenf_holding": [
                {
                    "cik": 910002, "accession_number": "0000-linked-adv",
                    "period_of_report": "2023-12-31", "cusip": "037833100",
                    "issuer_name": "Apple Inc", "security_title": "Common Stock",
                    "shares_held": 1000, "market_value": 15000000,
                    "put_call": None, "discretion_type": "SOLE", "security_class": None,
                },
            ],
        })
        pipe = MDMPipeline(session=session, silver=silver)
        summary = pipe.derive_relationships(relationship_types=["INSTITUTIONAL_HOLDS"])
        assert summary["INSTITUTIONAL_HOLDS"]["inserted"] == 1
        assert summary["INSTITUTIONAL_HOLDS"]["skipped_unresolved_source"] == 0
        assert summary["INSTITUTIONAL_HOLDS"]["skipped"] == (
            summary["INSTITUTIONAL_HOLDS"]["skipped_corporate"]
            + summary["INSTITUTIONAL_HOLDS"]["skipped_unresolved_source"]
            + summary["INSTITUTIONAL_HOLDS"]["skipped_unresolved_target"]
            + summary["INSTITUTIONAL_HOLDS"]["skipped_existing"]
        )

    def test_optional_fundamentals_source_table_missing_institutional_holds(self, session):
        """INSTITUTIONAL_HOLDS: missing sec_thirteenf_holding → 0 rows, no exception. (06-02)"""
        silver = MissingTableSilver("sec_thirteenf_holding")
        pipe = MDMPipeline(session=session, silver=silver)
        summary = pipe.derive_relationships(
            target_per_type=1, relationship_types=["INSTITUTIONAL_HOLDS"]
        )
        assert summary["INSTITUTIONAL_HOLDS"]["inserted"] == 0
        assert summary["INSTITUTIONAL_HOLDS"]["skipped"] == 0
        assert any("sec_thirteenf_holding" in query for query in silver.queries)

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

    def test_all_relationship_types_idempotent(self, session, fixture_world):
        """Running derive_relationships() twice inserts 0 rows on second run for all 11 types. (D-04, REL-04, 06-02)"""
        session.add(MdmSourceRef(
            entity_id=fixture_world["security_entity_id"],
            source_system="ownership_filing",
            source_id="0000-issuer-1:0:0",
            source_priority=3,
        ))
        session.commit()

        silver = StubSilver({
            # IS_INSIDER + HOLDS (ownership forms)
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
            # EMPLOYED_BY (DEF 14A proxy)
            "sec_executive_record": [
                {
                    "cik": 910001, "accession_number": "0000-issuer-1",
                    "fiscal_year": 2023, "exec_name": "Jane CEO", "exec_role": "CEO",
                    "total_comp": 5000000, "base_salary": 1000000, "bonus": None,
                    "stock_awards": None, "option_awards": None,
                    "non_equity_incentive": None, "tenure_start_year": 2020,
                },
            ],
            # AUDITED_BY (10-K XBRL DEI — resolves to fixture_world audit_firm pcaob_firm_id=E1)
            "sec_accounting_flag": [
                {
                    "cik": 910001, "accession_number": "0000-issuer-1",
                    "fiscal_year": 2023, "period_end": None,
                    "auditor_pcaob_id": "E1", "auditor_name": "Deloitte LLP",
                    "icfr_attestation": True,
                },
            ],
            # INSTITUTIONAL_HOLDS (13F-HR — adviser CIK 910002, auto-creates security by CUSIP)
            "sec_thirteenf_holding": [
                {
                    "cik": 910002, "accession_number": "0000-linked-adv",
                    "period_of_report": "2023-12-31", "cusip": "037833100",
                    "issuer_name": "Apple Inc", "security_title": "Common Stock",
                    "shares_held": 1000, "market_value": 15000000,
                    "put_call": None, "discretion_type": "SOLE", "security_class": None,
                },
            ],
        })
        pipe = MDMPipeline(session=session, silver=silver)

        ALL_TYPES = [
            "IS_INSIDER",
            "HOLDS",
            "COMPANY_HOLDS",
            "ISSUED_BY",
            "MANAGES_FUND",
            "IS_ENTITY_OF",
            "HAS_PARENT_COMPANY",
            "IS_PERSON_OF",
            "EMPLOYED_BY",
            "AUDITED_BY",
            "INSTITUTIONAL_HOLDS",
        ]
        first = pipe.derive_relationships()
        second = pipe.derive_relationships()

        # First-run insert assertions (existing 8 types)
        assert first["IS_INSIDER"]["inserted"] >= 1
        assert first["HOLDS"]["inserted"] == 1
        assert first["COMPANY_HOLDS"]["inserted"] == 0
        assert first["ISSUED_BY"]["inserted"] == 1
        assert first["MANAGES_FUND"]["inserted"] == 1
        assert first["IS_ENTITY_OF"]["inserted"] == 1
        assert first["HAS_PARENT_COMPANY"]["inserted"] == 0
        assert first["IS_PERSON_OF"]["inserted"] == 1
        # First-run insert assertions (3 new fundamentals types — 06-02)
        assert first["EMPLOYED_BY"]["inserted"] >= 1
        assert first["AUDITED_BY"]["inserted"] >= 1
        assert first["INSTITUTIONAL_HOLDS"]["inserted"] >= 1

        # Second run must insert 0 for all 11 types (idempotency gate)
        for rt in ALL_TYPES:
            assert second[rt]["inserted"] == 0, (
                f"Expected 0 inserts on second run for {rt}, got {second[rt]['inserted']}"
            )

        # skipped backward-compat: skipped == sum of four sub-counters for all 11 types
        for rt in ALL_TYPES:
            assert second[rt]["skipped"] == (
                second[rt]["skipped_corporate"]
                + second[rt]["skipped_unresolved_source"]
                + second[rt]["skipped_unresolved_target"]
                + second[rt]["skipped_existing"]
            ), f"skipped backward-compat broken for {rt}"


# ---------------------------------------------------------------------------
# _bounded_relationship_sql / plateau-fix regression
#
# Bug: full-universe-sync.sh --limit 500 reported the same ~500 rows on every
# rerun ("skipped_existing" never decreased, "inserted" plateaued at the first
# run's count). Root cause: the source SQL had no ORDER BY, and the LIMIT was a
# flat function of `remaining` -- so every invocation re-fetched the same
# leading slice of an arbitrarily-ordered table. Rows already converted came
# back as skipped_existing and the scan never advanced into fresh territory.
#
# Fix: _bounded_relationship_sql(sql, remaining, existing) grows the LIMIT by
# `existing` (the live count of relationships of that type), and the six
# affected derivers gained deterministic ORDER BY clauses. Together these
# guarantee the fetch window always extends strictly past the previously
# converted prefix.
# ---------------------------------------------------------------------------

class TestBoundedRelationshipSqlPlateauFix:
    def test_appends_limit_growing_with_remaining_and_existing(self):
        sql = "SELECT * FROM t"

        # remaining=None -> idempotency-check path, full unbounded scan
        assert MDMPipeline._bounded_relationship_sql(sql, None, existing=500) == sql

        # existing=0 -> limit floors at the minimum window (multiplier * remaining)
        assert MDMPipeline._bounded_relationship_sql(sql, 1, existing=0) == f"{sql} LIMIT 100"
        assert MDMPipeline._bounded_relationship_sql(sql, 10, existing=0) == f"{sql} LIMIT 500"

        # `existing` is additive -- this is the plateau fix itself: the window
        # must extend past the count of rows already converted, or repeat runs
        # with the same --limit re-fetch the same leading slice forever.
        assert MDMPipeline._bounded_relationship_sql(sql, 10, existing=2_000) == f"{sql} LIMIT 2500"
        assert MDMPipeline._bounded_relationship_sql(sql, 1, existing=450) == f"{sql} LIMIT 550"

    def test_limit_always_strictly_exceeds_existing_count(self):
        """Falsifiable invariant behind the fix: whatever `existing` is, the
        emitted LIMIT must be strictly greater than it. Combined with a stable
        ORDER BY, that guarantees the fetch reaches past every previously
        converted row into unconverted ones -- the precise mechanism that
        prevents the plateau. If this regresses to `existing` not feeding the
        limit, the LIMIT collapses back to a flat function of `remaining` and
        can again sit below `existing`, reproducing the bug.
        """
        sql = "SELECT * FROM t ORDER BY id"
        for existing in (0, 1, 99, 100, 4_999, 50_000):
            bounded = MDMPipeline._bounded_relationship_sql(sql, remaining=1, existing=existing)
            limit = int(bounded.rsplit("LIMIT", 1)[1].strip())
            assert limit > existing, (
                f"LIMIT {limit} does not exceed existing={existing} -- "
                f"a stable-order rescan would land entirely within already-"
                f"converted rows and plateau at skipped_existing"
            )


class _LimitCapturingSilver(StubSilver):
    """StubSilver that also records the LIMIT clause of each issued query.

    Lets the test observe the exact source-window size the pipeline asks for
    on each invocation -- the thing the plateau bug got wrong.
    """

    def __init__(self, fixtures: dict[str, list[dict]]):
        super().__init__(fixtures)
        self.limits: list[int] = []

    def fetch(self, sql: str, params: Optional[list[Any]] = None) -> list[dict]:
        match = re.search(r"LIMIT\s+(\d+)\s*$", sql.strip())
        if match:
            self.limits.append(int(match.group(1)))
        return super().fetch(sql, params)


class TestRelationshipDerivationPlateauFix:
    def test_employed_by_window_advances_across_repeat_runs(self, session, fixture_world):
        """End-to-end regression test for "always picking the same N rows".

        Two distinct DEF-14A executive records for the same issuer; with
        target_per_type=5 both insert on the first run. The second run must
        compute a strictly larger source LIMIT than the first -- proving the
        fetch window grows with the live relationship count rather than
        re-issuing the same bounded query and plateauing on skipped_existing.
        """
        exec_row = lambda accession, year, name, role: {
            "cik": 910001, "accession_number": accession, "fiscal_year": year,
            "exec_name": name, "exec_role": role, "total_comp": 1_000_000,
            "base_salary": None, "bonus": None, "stock_awards": None,
            "option_awards": None, "non_equity_incentive": None,
            "tenure_start_year": None,
        }
        silver = _LimitCapturingSilver({
            "sec_executive_record": [
                exec_row("0000-issuer-1", 2022, "Jane CEO", "CEO"),
                exec_row("0000-issuer-2", 2023, "John CFO", "CFO"),
            ],
        })
        pipe = MDMPipeline(session=session, silver=silver)

        first = pipe.derive_relationships(target_per_type=5, relationship_types=["EMPLOYED_BY"])
        assert first["EMPLOYED_BY"]["existing"] == 0
        assert first["EMPLOYED_BY"]["inserted"] == 2

        second = pipe.derive_relationships(target_per_type=5, relationship_types=["EMPLOYED_BY"])
        assert second["EMPLOYED_BY"]["existing"] == 2
        assert second["EMPLOYED_BY"]["inserted"] == 0  # both already converted -- idempotent

        assert len(silver.limits) == 2, "expected exactly one bounded fetch per run"
        first_limit, second_limit = silver.limits
        existing_at_run2 = second["EMPLOYED_BY"]["existing"]
        remaining_at_run2 = 5 - existing_at_run2

        # `existing` itself must be live (reflect what run 1 created), not a
        # stale/constant value -- otherwise the additive term below is a no-op
        # and the bug resurfaces silently even though the formula "looks" fixed.
        assert existing_at_run2 == first["EMPLOYED_BY"]["inserted"] == 2

        # The precise invariant that distinguishes fixed vs. broken: the second
        # LIMIT must equal existing + max(remaining * 50, 100) -- i.e. it must
        # include the live `existing` addend. A bare assertion that
        # `second_limit > existing` is NOT sufficient to catch the regression
        # here: at this fixture's scale the pre-fix flat limit
        # (max(remaining*50, 100) == 150) already exceeds existing (2), so a
        # looser check would pass against the broken code too (false
        # confidence). The exact value 152 only comes out of existing(2) +
        # max(3*50, 100); the pre-fix formula would emit 150.
        expected_limit = existing_at_run2 + max(remaining_at_run2 * 50, 100)
        assert second_limit == expected_limit == 152, (
            f"second-run LIMIT ({second_limit}) != existing + windowed-remaining "
            f"({expected_limit}) -- the `existing` addend is missing from the "
            f"emitted LIMIT, so a stable-order rescan would plateau on the same "
            f"leading slice instead of advancing past converted rows"
        )
        assert first_limit == 0 + max(5 * 50, 100) == 250
