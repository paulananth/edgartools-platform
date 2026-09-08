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

import itertools
import re
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pytest
from sqlalchemy import create_engine, event, func, select
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
    MdmRelationshipDerivationCheckpoint,
    MdmRelationshipInstance,
    MdmRelationshipType,
    MdmSecurity,
    MdmSourcePriority,
    MdmSourceRef,
    get_session,
)
from edgar_warehouse.mdm.graph import GraphSyncEngine
from edgar_warehouse.mdm.pipeline import MDMPipeline, _derive_role

from tests.mdm.test_run_companies_concurrency import _StubBookkeeping


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class StubSilver:
    """Returns canned rows keyed by a substring of the SQL.

    Also emulates the two SQL shapes used by INSTITUTIONAL_HOLDS CIK-range
    batching (06-01, D-03):
      * an aggregate ``SELECT MIN(cik) AS min_cik, MAX(cik) AS max_cik ...``
        bounds query -- answered by scanning the substring-matched fixture
        rows for their CIK range;
      * a parameterized ``... AND cik BETWEEN ? AND ? ...`` batch query --
        answered by filtering the substring-matched rows to the CIK range
        supplied via ``params`` (never parsed out of the SQL text itself,
        so tests can assert bound-param usage per T-06-01).
    """

    def __init__(self, fixtures: dict[str, list[dict]]):
        self._fixtures = fixtures
        self.queries: list[str] = []
        # (sql, params) for every fetch() call -- lets batching tests assert
        # CIK bounds arrive via bound params rather than interpolated SQL.
        self.calls: list[tuple[str, Optional[list[Any]]]] = []

    def fetch(self, sql: str, params: Optional[list[Any]] = None) -> list[dict]:
        self.queries.append(sql)
        self.calls.append((sql, params))
        matched = self._matched_rows(sql)
        if "MIN(cik)" in sql and "MAX(cik)" in sql:
            ciks = [r["cik"] for r in matched if r.get("cik") is not None]
            if not ciks:
                return [{"min_cik": None, "max_cik": None}]
            return [{"min_cik": min(ciks), "max_cik": max(ciks)}]
        if "MAX(f.period_of_report)" in sql and params:
            # INSTITUTIONAL_HOLDS deactivation's own latest-period lookup
            # (mdm-relationship-incremental-filters Ticket 04) -- scoped to
            # exactly one manager CIK (params[0]), never parsed out of the
            # SQL text, mirroring the MIN/MAX(cik) case above.
            cik = params[0]
            periods = [
                r["period_of_report"] for r in matched
                if r.get("cik") == cik and r.get("period_of_report") is not None
            ]
            return [{"latest_period": max(periods) if periods else None}]
        if "DISTINCT h.cusip" in sql and params:
            # Same ticket's follow-up cusip-set lookup, scoped to
            # (cik, period_of_report) -- params[0], params[1].
            cik, period = params[0], params[1]
            cusips = {
                r["cusip"] for r in matched
                if r.get("cik") == cik and r.get("period_of_report") == period
                and r.get("cusip")
            }
            return [{"cusip": cusip} for cusip in cusips]
        if params and "BETWEEN" in sql.upper():
            lo, hi = params[0], params[1]
            matched = [r for r in matched if r.get("cik") is not None and lo <= r["cik"] <= hi]
        elif params and " IN (" in sql.upper():
            # MANAGES_FUND CRD-batch scoping (mdm-oom-manages-fund fix), or
            # IS_INSIDER's issuer_ciks-scoped targeted resync (Ticket 21) --
            # filter by whichever ID-shaped field the matched rows carry --
            # never parsed out of the SQL text, mirroring the BETWEEN case
            # above so batching tests can assert bound-param usage too.
            # issuer_cik is checked last since it only ever applies to rows
            # with no CRD field at all (a MANAGES_FUND row never carries it).
            wanted = {str(p) for p in params}
            matched = [
                r for r in matched
                if str(r.get("crd_number", r.get("adviser_crd_number", r.get("issuer_cik", "")))) in wanted
            ]
        return matched

    def _matched_rows(self, sql: str) -> list[dict]:
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
def fk_enforced_session() -> Session:
    """Same as `session`, but with SQLite foreign-key enforcement turned on.

    The plain `session` fixture leaves SQLite's default (FKs unenforced), which
    is why the ForeignKeyViolation in _ensure_thirteenf_manager/
    _ensure_disclosed_subsidiary/_audit_firm_entity_id (MdmEntity inserted after
    its FK-dependent row, because no relationship() links them so the ORM can't
    auto-order the flush) was invisible to this suite and only surfaced against
    real Postgres in prod. Use this fixture for any test of a code path that
    creates an MdmEntity + a dependent row in the same flush.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
        dbapi_conn.create_function("NOW", 0, lambda: datetime.utcnow().isoformat())

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
                   crd_number="129052",
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
        private_fund_id="805-123",
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

    def test_source_backed_parent_relationship_uses_valid_reported_date(self, session, fixture_world):
        silver = StubSilver({
            "sec_subsidiary_evidence": [{
                "accession_number": "annual-2024",
                "registrant_cik": 910001,
                "document_name": "ex21.htm",
                "row_ordinal": 1,
                "legal_name": "Reported Subsidiary LLC",
                "jurisdiction": "Delaware",
                "parent_scope": "registrant_disclosed",
                "immediate_parent_known": False,
                "effective_date": date(2024, 12, 31),
                "source_sha256": "ex21-sha",
            }],
        })

        summary = MDMPipeline(session=session, silver=silver).derive_relationships(
            relationship_types=["HAS_PARENT_COMPANY"]
        )

        assert summary["HAS_PARENT_COMPANY"]["inserted"] == 1
        relationship = session.scalar(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "HAS_PARENT_COMPANY")
        )
        assert relationship is not None
        assert relationship.date_provenance == "reported"

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

    def test_company_holds_batches_entity_id_lookups_across_rows(self, session, fixture_world):
        """Two COMPANY_HOLDS candidate rows sharing the same owner_cik and
        issuer_cik, each resolving to a *different* security via
        _security_entity_id's canonical_title+issuer fallback path (no
        MdmSourceRef seeded for either security, forcing both through that
        fallback). Regression guard for the bulk-prefetch fix: asserts both
        relationships resolve correctly from one shared
        company_entity_id_by_cik dict, and that the number of
        mdm_company-touching SQL statements issued stays flat as row count
        grows (2 rows -> same query count as 1 row would need), not O(rows).
        """
        preferred_security_id = _add_entity(session, "security")
        session.add(MdmSecurity(
            entity_id=preferred_security_id,
            issuer_entity_id=fixture_world["issuer_company_id"],
            canonical_title="Preferred Stock",
        ))
        session.commit()

        pipe = MDMPipeline(session=session, silver=StubSilver({
            "FROM sec_ownership_non_derivative_txn": [
                {
                    "accession_number": "0000-corp-batch",
                    "owner_index": 1,
                    "txn_index": 0,
                    "security_title": "Common Stock",
                    "transaction_date": None,
                    "shares_owned_after": 25,
                    "ownership_direct_indirect": "I",
                    "owner_cik": 910002,
                    "owner_name": "Linked Corp",
                    "issuer_cik": 910001,
                },
                {
                    "accession_number": "0000-corp-batch",
                    "owner_index": 1,
                    "txn_index": 1,
                    "security_title": "Preferred Stock",
                    "transaction_date": None,
                    "shares_owned_after": 10,
                    "ownership_direct_indirect": "I",
                    "owner_cik": 910002,
                    "owner_name": "Linked Corp",
                    "issuer_cik": 910001,
                },
            ],
        }))

        company_queries = []
        engine = session.get_bind()

        def _count_company_queries(conn, cursor, statement, *_args):
            if "mdm_company" in statement:
                company_queries.append(statement)

        event.listen(engine, "before_cursor_execute", _count_company_queries)
        try:
            summary = pipe.derive_relationships(target_per_type=2, relationship_types=["COMPANY_HOLDS"])
        finally:
            event.remove(engine, "before_cursor_execute", _count_company_queries)

        rows = list(session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "COMPANY_HOLDS")
            .order_by(MdmRelationshipInstance.target_entity_id)
        ))
        assert summary["COMPANY_HOLDS"]["inserted"] == 2
        assert len(rows) == 2
        targets = {r.target_entity_id for r in rows}
        assert targets == {fixture_world["security_entity_id"], preferred_security_id}
        for r in rows:
            assert r.source_entity_id == fixture_world["linked_company_id"]

        # Exactly 2 mdm_company-touching queries total for 2 rows: one is
        # _company_cik_set()'s pre-existing whole-table membership check
        # (unrelated to this fix, runs once regardless of row count), the
        # other is the new bulk `WHERE cik IN (...)` prefetch that now
        # serves *both* rows from a single round-trip. Before this fix, the
        # second row would have added a 3rd, row-scoped query -- this count
        # would grow with row count instead of staying flat at 2.
        assert len(company_queries) == 2, company_queries

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

    def test_proxy_person_stub_writes_change_log_for_export(self, session, fixture_world):
        """Ticket 20: proxy stubs must enter mdm_change_log so export can drain them."""
        from edgar_warehouse.mdm.database import MdmChangeLog, MdmEntity, MdmPerson

        silver = StubSilver({
            "sec_executive_record": [
                {
                    "cik": 910001, "accession_number": "0000-issuer-1",
                    "fiscal_year": 2023, "exec_name": "Proxy Only Exec", "exec_role": "CFO",
                    "total_comp": 1000000, "base_salary": 400000, "bonus": None,
                    "stock_awards": None, "option_awards": None,
                    "non_equity_incentive": None, "tenure_start_year": 2021,
                },
            ],
        })
        MDMPipeline(session=session, silver=silver).derive_relationships(
            relationship_types=["EMPLOYED_BY"]
        )
        person = session.scalar(
            select(MdmPerson).where(MdmPerson.canonical_name == "Proxy Only Exec")
        )
        assert person is not None
        entity = session.get(MdmEntity, person.entity_id)
        assert entity is not None
        assert entity.resolution_method == "uuid5_proxy_stub"
        change = session.scalar(
            select(MdmChangeLog).where(MdmChangeLog.entity_id == person.entity_id)
        )
        assert change is not None
        assert change.entity_type == "person"
        assert change.exported_at is None

    def test_item_502_appointment_opens_employment_version(self, session, fixture_world):
        silver = StubSilver({
            "sec_employment_event": [{
                "accession_number": "item-502-appointment",
                "cik": 910001,
                "event_type": "appointment",
                "person_name": "New Executive",
                "exec_role": "Chief Operating Officer",
                "previous_role": None,
                "compensation_amount": None,
                "effective_date": date(2025, 3, 1),
            }],
        })

        summary = MDMPipeline(session=session, silver=silver).derive_relationships(
            relationship_types=["EMPLOYED_BY"]
        )

        assert summary["EMPLOYED_BY"]["inserted"] == 1
        relationship = session.scalar(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "EMPLOYED_BY")
        )
        assert relationship is not None
        assert relationship.effective_from == date(2025, 3, 1)
        assert relationship.properties["role"] == "Chief Operating Officer"

    def test_item_502_event_predating_proxy_baseline_is_skipped_not_crashed(
        self, session, fixture_world
    ):
        """Regression: prod run edge09-employed-by-forced-1785099117 (2026-07-26).

        Proxy baselines (source_system=proxy_filing) are inserted with
        effective_from = Jan 1 of the DEF 14A fiscal_year -- a coarse
        placeholder, not a true start date. Item 5.02 events are walked in a
        separate pass ordered by their own real effective_date. When a
        person/company pair has both, and the event's effective_date lands
        *before* the baseline's placeholder effective_from, closing the
        baseline at the event's date used to set effective_to < effective_from
        and crash the whole derive with a Postgres/SQLite
        ck_rel_instance_valid_interval CheckViolation. It must now be skipped
        instead.
        """
        silver = StubSilver({
            "sec_executive_record": [
                {
                    "cik": 910001, "accession_number": "proxy-1",
                    "fiscal_year": 2025, "exec_name": "Pat Officer", "exec_role": "President",
                    "total_comp": 2000000, "base_salary": 800000, "bonus": None,
                    "stock_awards": None, "option_awards": None,
                    "non_equity_incentive": None, "tenure_start_year": 2020,
                },
            ],
            "sec_employment_event": [{
                "accession_number": "item-502-role-change",
                "cik": 910001,
                "event_type": "role_change",
                "person_name": "Pat Officer",
                "exec_role": "Executive Chairman",
                "previous_role": "President",
                "compensation_amount": None,
                "effective_date": date(2024, 7, 5),
            }],
        })

        summary = MDMPipeline(session=session, silver=silver).derive_relationships(
            relationship_types=["EMPLOYED_BY"]
        )

        # Only the proxy baseline lands; the out-of-order event is skipped, not crashed.
        assert summary["EMPLOYED_BY"]["inserted"] == 1
        assert summary["EMPLOYED_BY"]["skipped_unresolved_source"] == 1

        relationships = session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "EMPLOYED_BY")
        ).all()
        assert len(relationships) == 1
        baseline = relationships[0]
        assert baseline.effective_from == date(2025, 1, 1)
        # The skipped close must never have touched the baseline's end date.
        assert baseline.effective_to is None
        assert baseline.valid_to_date is None

    def test_item_502_same_day_events_are_skipped_not_crashed(self, session, fixture_world):
        """Regression: prod run edge09-employed-by-postfix2-1785105042 (2026-07-26).

        The first date-ordering fix (test above) only guarded a strictly-earlier
        event date against an already-open version's effective_from. It missed the
        equal-date case: ck_rel_instance_valid_interval requires a *strictly*
        positive interval (valid_to_date > valid_from_date), so closing a version
        at the exact same date it opened on -- e.g. two Item 5.02 events for the
        same person/company both effective on the same day, common when a single
        accession or same-day amendment reports more than one personnel change --
        also violates the constraint and crashed the derive with the identical
        CheckViolation. Must now be skipped instead.
        """
        silver = StubSilver({
            "sec_employment_event": [
                {
                    "accession_number": "item-502-a",
                    "cik": 910001,
                    "event_type": "appointment",
                    "person_name": "Sam Director",
                    "exec_role": "Director",
                    "previous_role": None,
                    "compensation_amount": None,
                    "effective_date": date(2024, 8, 1),
                },
                {
                    "accession_number": "item-502-b",
                    "cik": 910001,
                    "event_type": "role_change",
                    "person_name": "Sam Director",
                    "exec_role": "Lead Director",
                    "previous_role": "Director",
                    "compensation_amount": None,
                    "effective_date": date(2024, 8, 1),
                },
            ],
        })

        summary = MDMPipeline(session=session, silver=silver).derive_relationships(
            relationship_types=["EMPLOYED_BY"]
        )

        # Only the first same-day event opens a version; the second is skipped, not crashed.
        assert summary["EMPLOYED_BY"]["inserted"] == 1
        assert summary["EMPLOYED_BY"]["skipped_unresolved_source"] == 1

        relationships = session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "EMPLOYED_BY")
        ).all()
        assert len(relationships) == 1
        opened = relationships[0]
        assert opened.effective_from == date(2024, 8, 1)
        assert opened.properties["role"] == "Director"
        assert opened.effective_to is None
        assert opened.valid_to_date is None

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

    def test_direct_auditor_evidence_creates_long_tail_firm_at_report_date(
        self, session, fixture_world
    ):
        silver = StubSilver({
            "sec_auditor_report_evidence": [{
                "cik": 910001, "accession_number": "annual-2024",
                "fiscal_year": 2024, "period_end": date(2024, 12, 31),
                "report_date": date(2025, 2, 14), "auditor_pcaob_id": "1042",
                "auditor_name": "Long Tail CPAs", "icfr_attestation": None,
                "evidence_source": "sec_ixbrl", "evidence_fingerprint": "fp-1",
                "form_ap_filing_id": "ap-9",
            }],
        })
        summary = MDMPipeline(session=session, silver=silver).derive_relationships(
            relationship_types=["AUDITED_BY"]
        )
        assert summary["AUDITED_BY"]["inserted"] == 1
        firm = session.scalar(
            select(MdmAuditFirm).where(MdmAuditFirm.pcaob_firm_id == "1042")
        )
        assert firm is not None
        relationship = session.scalar(select(MdmRelationshipInstance).where(
            MdmRelationshipInstance.target_entity_id == firm.entity_id
        ))
        assert relationship.effective_from == date(2025, 2, 14)
        assert relationship.properties["evidence_fingerprint"] == "fp-1"

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
        assert fy2022.valid_to_date == date(2023, 1, 1)
        assert fy2023.valid_to_date is None
        assert fy2023.is_active is True

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

    def test_thirteenf_manager_outside_adv_universe_is_created(self, session):
        silver = StubSilver({
            "sec_thirteenf_holding": [{
                "cik": 999001, "accession_number": "manager-only",
                "period_of_report": "2024-03-31", "cusip": "037833100",
                "issuer_name": "Apple Inc", "security_title": "Common Stock",
                "shares_held": 1, "market_value": 100, "put_call": None,
                "discretion_type": "SOLE", "security_class": "equity",
            }],
            "FROM sec_company WHERE cik": [{"entity_name": "Manager Only LLC"}],
        })
        summary = MDMPipeline(session=session, silver=silver).derive_relationships(
            relationship_types=["INSTITUTIONAL_HOLDS"]
        )
        assert summary["INSTITUTIONAL_HOLDS"]["inserted"] == 1
        from edgar_warehouse.mdm.database import MdmAdviser
        manager = session.scalar(select(MdmAdviser).where(MdmAdviser.cik == 999001))
        assert manager is not None
        assert manager.canonical_name == "Manager Only LLC"

    def test_thirteenf_manager_resolves_name_against_real_silver_schema(self, fk_enforced_session, tmp_path):
        """Regression: _ensure_thirteenf_manager's sec_company query must match the
        real schema (entity_name), not a StubSilver fixture that can silently drift
        from it. A prior version of this file's StubSilver fixture used the same
        wrong column name ("company_name") as a since-fixed production bug in
        pipeline.py, so the stub-based test above passed while prod raised
        duckdb.BinderException: column "company_name" not found (real column is
        entity_name). This test runs the same code path against a real
        SilverDatabase-backed DuckDB file instead of a stub, so a future rename of
        either side would fail here.

        Uses fk_enforced_session (not the plain `session` fixture) because a
        second, independent prod bug shared this exact code path: MdmEntity was
        inserted after its FK-dependent MdmAdviser row (ForeignKeyViolation on
        real Postgres), invisible under SQLite's default no-FK-enforcement.
        """
        session = fk_enforced_session
        from edgar_warehouse.silver_store import SilverDatabase

        silver_path = tmp_path / "silver.duckdb"
        db = SilverDatabase(str(silver_path))
        db._conn.execute(
            "INSERT INTO sec_company (cik, entity_name) VALUES (?, ?)",
            [999002, "Real Schema Manager LLC"],
        )
        db.merge_thirteenf_filings([{
            "accession_number": "real-schema-manager",
            "cik": 999002, "period_of_report": "2024-03-31",
            "filing_date": "2024-05-15", "form": "13F-HR",
            "amendment_type": None, "confidential_omission": False,
            "parser_version": "1",
        }], "test-run")
        db.merge_thirteenf_holdings([{
            "cik": 999002, "accession_number": "real-schema-manager",
            "holding_index": 1, "period_of_report": "2024-03-31",
            "cusip": "037833100", "issuer_name": "Apple Inc",
            "security_title": "Common Stock", "shares_held": 1,
            "market_value": 100, "security_class": "equity",
            "put_call": None, "discretion_type": "SOLE",
            "voting_auth_sole": None, "voting_auth_shared": None,
            "voting_auth_none": None, "parser_version": "1",
        }], "test-run")
        db.close()

        summary = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path))).derive_relationships(
            relationship_types=["INSTITUTIONAL_HOLDS"]
        )
        assert summary["INSTITUTIONAL_HOLDS"]["inserted"] == 1
        from edgar_warehouse.mdm.database import MdmAdviser
        manager = session.scalar(select(MdmAdviser).where(MdmAdviser.cik == 999002))
        assert manager is not None
        assert manager.canonical_name == "Real Schema Manager LLC"

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

    def test_manages_fund_uses_latest_effective_adv_filing_only(self, session, fixture_world):
        second_fund_id = _add_entity(session, "fund")
        session.add(MdmFund(
            entity_id=second_fund_id,
            adviser_entity_id=fixture_world["firm_adviser_id"],
            private_fund_id="805-999",
            canonical_name="Current Fund",
        ))
        session.commit()
        silver = StubSilver({
            "sec_adv_filing": [
                {
                    "accession_number": "iapd-adv:100",
                    "crd_number": "129052",
                    "effective_date": date(2024, 1, 1),
                    "filing_action": "annual_amendment",
                },
                {
                    "accession_number": "iapd-adv:200",
                    "crd_number": "129052",
                    "effective_date": date(2025, 1, 1),
                    "filing_action": "annual_amendment",
                },
            ],
            "sec_adv_private_fund": [
                {
                    "accession_number": "iapd-adv:100",
                    "adviser_crd_number": "129052",
                    "private_fund_id": "805-123",
                    "filing_id": "100",
                    "schedule_section": "7B1",
                    "reporting_role": "detailed_reporter",
                    "effective_date": date(2024, 1, 1),
                    "filing_action": "annual_amendment",
                    "source_sha256": "old",
                },
                {
                    "accession_number": "iapd-adv:200",
                    "adviser_crd_number": "129052",
                    "private_fund_id": "805-999",
                    "filing_id": "200",
                    "schedule_section": "7B1",
                    "reporting_role": "detailed_reporter",
                    "effective_date": date(2025, 1, 1),
                    "filing_action": "annual_amendment",
                    "source_sha256": "current",
                },
            ],
        })

        summary = MDMPipeline(session=session, silver=silver).derive_relationships(
            relationship_types=["MANAGES_FUND"]
        )

        assert summary["MANAGES_FUND"]["inserted"] == 1
        relationships = session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "MANAGES_FUND")
        ).all()
        assert [row.target_entity_id for row in relationships] == [second_fund_id]

    def test_final_adv_filing_closes_prior_manages_fund_relationship(self, session, fixture_world):
        old_filing = {
            "accession_number": "iapd-adv:100", "crd_number": "129052",
            "effective_date": date(2024, 1, 1), "filing_action": "annual_amendment",
        }
        old_fund = {
            "accession_number": "iapd-adv:100", "adviser_crd_number": "129052",
            "private_fund_id": "805-123", "filing_id": "100",
            "schedule_section": "7B1", "reporting_role": "detailed_reporter",
            "effective_date": date(2024, 1, 1), "filing_action": "annual_amendment",
            "source_sha256": "old",
        }
        MDMPipeline(session=session, silver=StubSilver({
            "sec_adv_filing": [old_filing], "sec_adv_private_fund": [old_fund],
        })).derive_relationships(relationship_types=["MANAGES_FUND"])

        final_filing = {
            "accession_number": "iapd-adv:200", "crd_number": "129052",
            "effective_date": date(2025, 1, 1), "filing_action": "final_sec_era_report",
        }
        MDMPipeline(session=session, silver=StubSilver({
            "sec_adv_filing": [old_filing, final_filing],
            "sec_adv_private_fund": [old_fund],
        })).derive_relationships(relationship_types=["MANAGES_FUND"])

        relationship = session.scalar(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "MANAGES_FUND")
        )
        assert relationship is not None
        assert relationship.valid_to_date == date(2025, 1, 1)

    def test_manages_fund_uses_bounded_database_round_trips(
        self, session, monkeypatch
    ):
        """ADV-scale derivation must not issue adviser/fund/edge lookups per row."""
        filings = []
        funds = []
        for index in range(12):
            adviser_id = _add_entity(session, "adviser")
            fund_id = _add_entity(session, "fund")
            crd_number = str(700000 + index)
            private_fund_id = f"805-{700000 + index}"
            accession = f"iapd-adv:{700000 + index}"
            session.add(MdmAdviser(
                entity_id=adviser_id,
                crd_number=crd_number,
                canonical_name=f"Bulk Adviser {index}",
            ))
            session.add(MdmFund(
                entity_id=fund_id,
                adviser_entity_id=adviser_id,
                private_fund_id=private_fund_id,
                canonical_name=f"Bulk Fund {index}",
            ))
            filings.append({
                "accession_number": accession,
                "crd_number": crd_number,
                "effective_date": date(2025, 1, 1),
                "filing_action": "annual_amendment",
            })
            funds.append({
                "accession_number": accession,
                "adviser_crd_number": crd_number,
                "private_fund_id": private_fund_id,
                "filing_id": str(700000 + index),
                "schedule_section": "7B1",
                "reporting_role": "detailed_reporter",
                "effective_date": date(2025, 1, 1),
                "filing_action": "annual_amendment",
                "source_sha256": f"sha-{index}",
            })
        session.commit()

        statements: list[str] = []

        def capture_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
            normalized = " ".join(statement.lower().split())
            if (
                "mdm_adviser" in normalized
                or "mdm_fund" in normalized
                or "mdm_relationship_instance" in normalized
            ):
                statements.append(normalized)

        bind = session.get_bind()
        write_flush_calls = 0
        original_flush = session.flush

        def count_flush(*args, **kwargs):
            nonlocal write_flush_calls
            if session.new:
                write_flush_calls += 1
            return original_flush(*args, **kwargs)

        monkeypatch.setattr(session, "flush", count_flush)
        event.listen(bind, "before_cursor_execute", capture_statement)
        try:
            summary = MDMPipeline(
                session=session,
                silver=StubSilver({
                    "sec_adv_filing": filings,
                    "sec_adv_private_fund": funds,
                }),
            ).derive_relationships(relationship_types=["MANAGES_FUND"])
        finally:
            event.remove(bind, "before_cursor_execute", capture_statement)

        assert summary["MANAGES_FUND"]["inserted"] == 12
        lookup_selects = [
            statement for statement in statements if statement.startswith("select ")
        ]
        assert len(lookup_selects) <= 6, lookup_selects
        assert write_flush_calls <= 2

    def test_manages_fund_processes_advisers_in_bounded_crd_batches(
        self, session, monkeypatch
    ):
        """mdm-oom-manages-fund fix: a universe spanning multiple CRD batches
        must be fully processed, and no single prime() call may ever see more
        than one batch's advisers primed at once -- the whole point of
        batching is bounding what's resident at any one time."""
        import edgar_warehouse.mdm.pipeline as pipeline_module

        monkeypatch.setattr(pipeline_module, "_MANAGES_FUND_CRD_BATCH_SIZE", 2)

        filings = []
        funds = []
        crd_by_index = {}
        for index in range(5):  # 5 advisers, batch size 2 -> 3 batches (2/2/1)
            adviser_id = _add_entity(session, "adviser")
            fund_id = _add_entity(session, "fund")
            crd_number = str(700000 + index)
            crd_by_index[index] = crd_number
            private_fund_id = f"805-{700000 + index}"
            accession = f"iapd-adv:{700000 + index}"
            session.add(MdmAdviser(
                entity_id=adviser_id, crd_number=crd_number,
                canonical_name=f"Batch Adviser {index}",
            ))
            session.add(MdmFund(
                entity_id=fund_id, adviser_entity_id=adviser_id,
                private_fund_id=private_fund_id, canonical_name=f"Batch Fund {index}",
            ))
            filings.append({
                "accession_number": accession, "crd_number": crd_number,
                "effective_date": date(2025, 1, 1), "filing_action": "annual_amendment",
            })
            funds.append({
                "accession_number": accession, "adviser_crd_number": crd_number,
                "private_fund_id": private_fund_id, "filing_id": str(700000 + index),
                "schedule_section": "7B1", "reporting_role": "detailed_reporter",
                "effective_date": date(2025, 1, 1), "filing_action": "annual_amendment",
                "source_sha256": f"sha-{index}",
            })
        session.commit()

        prime_calls: list[frozenset] = []
        original_prime = GraphSyncEngine.prime_relationship_type

        def spy_prime(self, rel_type_name, **kwargs):
            if rel_type_name == "MANAGES_FUND":
                prime_calls.append(frozenset(kwargs.get("source_entity_ids") or []))
            return original_prime(self, rel_type_name, **kwargs)

        monkeypatch.setattr(GraphSyncEngine, "prime_relationship_type", spy_prime)

        summary = MDMPipeline(
            session=session,
            silver=StubSilver({
                "sec_adv_filing": filings,
                "sec_adv_private_fund": funds,
            }),
        ).derive_relationships(relationship_types=["MANAGES_FUND"])

        assert summary["MANAGES_FUND"]["inserted"] == 5

        # 3 batches (ceil(5/2)), each priming a disjoint, non-empty adviser set.
        assert len(prime_calls) == 3
        assert all(prime_calls), prime_calls
        union = frozenset().union(*prime_calls)
        assert len(union) == 5, "every adviser must be primed exactly once across all batches"
        for a, b in itertools.combinations(prime_calls, 2):
            assert a.isdisjoint(b), (a, b, "batches must never overlap")

    def test_manages_fund_commits_periodically_at_each_crd_batch_boundary(
        self, session, monkeypatch
    ):
        """mdm-run-throughput Ticket 06: same periodic-commit fix as
        INSTITUTIONAL_HOLDS' CIK-range loop, applied to MANAGES_FUND's CRD-range
        loop for consistency -- 5 advisers, batch size 2 -> 3 batches (2/2/1) ->
        expect at least 3 periodic commits, not just one at the very end."""
        import edgar_warehouse.mdm.pipeline as pipeline_module

        monkeypatch.setattr(pipeline_module, "_MANAGES_FUND_CRD_BATCH_SIZE", 2)

        filings = []
        funds = []
        for index in range(5):
            adviser_id = _add_entity(session, "adviser")
            fund_id = _add_entity(session, "fund")
            crd_number = str(700000 + index)
            private_fund_id = f"805-{700000 + index}"
            accession = f"iapd-adv:{700000 + index}"
            session.add(MdmAdviser(
                entity_id=adviser_id, crd_number=crd_number,
                canonical_name=f"Batch Adviser {index}",
            ))
            session.add(MdmFund(
                entity_id=fund_id, adviser_entity_id=adviser_id,
                private_fund_id=private_fund_id, canonical_name=f"Batch Fund {index}",
            ))
            filings.append({
                "accession_number": accession, "crd_number": crd_number,
                "effective_date": date(2025, 1, 1), "filing_action": "annual_amendment",
            })
            funds.append({
                "accession_number": accession, "adviser_crd_number": crd_number,
                "private_fund_id": private_fund_id, "filing_id": str(700000 + index),
                "schedule_section": "7B1", "reporting_role": "detailed_reporter",
                "effective_date": date(2025, 1, 1), "filing_action": "annual_amendment",
                "source_sha256": f"sha-{index}",
            })
        session.commit()

        commit_count = [0]

        def _on_commit(_conn):
            commit_count[0] += 1

        event.listen(session.get_bind(), "commit", _on_commit)

        summary = MDMPipeline(
            session=session,
            silver=StubSilver({
                "sec_adv_filing": filings,
                "sec_adv_private_fund": funds,
            }),
        ).derive_relationships(relationship_types=["MANAGES_FUND"])

        assert summary["MANAGES_FUND"]["inserted"] == 5
        assert commit_count[0] >= 3, (
            f"expected at least 3 periodic commits (one per CRD batch), got {commit_count[0]} -- "
            "periodic mid-type commit is not firing"
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

    def test_node_resolution_is_idempotent_across_entity_types(self, session):
        """Node-side companion to test_all_relationship_types_idempotent (GVER-03, D-04).

        The relationship half of GVER-03 is already proven above via a real
        SQLAlchemy session (not mocks) -- the pattern that caught the
        plateau-fix regression a mock could not have surfaced. This test
        extends that same real-DB pattern to the 5 silver-resolved node
        types (company, adviser, person, security, fund): running each
        run_* resolver method a second time over unchanged StubSilver rows
        must add zero net-new active MdmEntity rows per type. The 6th node
        type (audit_firm) is seeded, not silver-resolved, and gets its own
        idempotency test immediately below.

        Uses a fresh `session` (not `fixture_world`) with its own unique CIKs
        so this test's resolution counts are not polluted by fixture_world's
        pre-seeded entities.
        """
        # resolve_one -> _stage_attrs -> survivorship needs source-priority rules
        # (mdm_source_priority, entity_type='all') to resolve get_source_priority()
        # for edgar_cik/adv_filing/ownership_filing -- matches the canonical seed
        # in edgar_warehouse/mdm/migrations/002_seed_data.sql.
        for source_system, priority in [
            ("edgar_cik", 1), ("adv_filing", 2), ("ownership_filing", 3), ("derived", 4),
        ]:
            session.add(MdmSourcePriority(
                entity_type="all", source_system=source_system, priority=priority,
            ))
        session.commit()

        silver = StubSilver({
            "FROM sec_company": [
                {
                    "cik": 920001, "entity_name": "Node Issuer Corp", "ein": None,
                    "sic": None, "sic_description": None,
                    "state_of_incorporation": None, "fiscal_year_end": None,
                },
                {
                    "cik": 920002, "entity_name": "Node Linked Corp", "ein": None,
                    "sic": None, "sic_description": None,
                    "state_of_incorporation": None, "fiscal_year_end": None,
                },
            ],
            "FROM sec_adv_filing": [
                {
                    "accession_number": "0002-linked-adv", "cik": 920002,
                    "crd_number": "CRD-2", "adviser_name": "Node Linked Asset Mgmt",
                    "sec_file_number": None, "filing_status": None,
                    "aum_total": None, "fund_count": None,
                    "effective_date": None,
                },
            ],
            "FROM sec_ownership_reporting_owner": [
                {
                    "accession_number": "0000-node-1", "owner_index": 0,
                    "owner_cik": 920102, "owner_name": "Node Reporting Person",
                    "officer_title": None, "is_director": True, "is_officer": False,
                    "is_ten_percent_owner": False, "is_other": False,
                    "issuer_cik": 920001,
                },
            ],
            "FROM sec_ownership_non_derivative_txn": [
                {
                    "accession_number": "0000-node-1", "owner_index": 0, "txn_index": 0,
                    "security_title": "Common Stock", "issuer_cik": 920001,
                    "is_derivative": False,
                },
            ],
            "FROM sec_ownership_derivative_txn": [],
            "sec_adv_private_fund": [
                {
                    "accession_number": "0002-linked-adv", "fund_index": 0,
                    "fund_name": "Node Linked Growth Fund", "fund_type": None,
                    "jurisdiction": None, "aum_amount": None,
                    "effective_date": None,
                },
            ],
        })
        pipe = MDMPipeline(session=session, silver=silver)

        def _snapshot() -> dict[str, int]:
            # MdmEntity has no is_active column (unlike MdmRelationshipInstance /
            # MdmRelationshipType) -- resolvers upsert-by-identity rather than
            # soft-delete, so every row present here is a live entity and a
            # net-new row in the second pass is exactly the duplicate this
            # test guards against.
            rows = session.execute(
                select(MdmEntity.entity_type, func.count())
                .where(MdmEntity.is_quarantined.is_(False))
                .group_by(MdmEntity.entity_type)
            ).all()
            return {entity_type: count for entity_type, count in rows}

        pipe.run_companies(bookkeeping=_StubBookkeeping())
        pipe.run_advisers()
        pipe.run_securities()
        pipe.run_persons()
        pipe.run_funds()
        first_counts = _snapshot()

        pipe.run_companies(bookkeeping=_StubBookkeeping())
        pipe.run_advisers()
        pipe.run_securities()
        pipe.run_persons()
        pipe.run_funds()
        second_counts = _snapshot()

        for entity_type in ("company", "adviser", "person", "security", "fund"):
            assert first_counts.get(entity_type, 0) > 0, (
                f"fixture produced zero {entity_type} entities on the first pass -- "
                f"test setup is not exercising this resolver"
            )
            assert second_counts.get(entity_type, 0) == first_counts.get(entity_type, 0), (
                f"entity_type={entity_type}: second resolution pass added "
                f"{second_counts.get(entity_type, 0) - first_counts.get(entity_type, 0)} "
                f"net-new active entities (first={first_counts.get(entity_type, 0)}, "
                f"second={second_counts.get(entity_type, 0)}) -- node resolution must be "
                f"idempotent over unchanged silver rows (GVER-03)"
            )

    def test_audit_firm_seed_is_idempotent(self, session):
        """6th node type (audit_firm is seeded, not silver-resolved) idempotency, GVER-03.

        seed_audit_firms uses a lookup-before-insert pattern keyed by
        pcaob_firm_id then canonical_name (edgar_warehouse/mdm/seed/audit_firms.py:108).
        Calling it twice against the same real session must not duplicate any
        of the 10 seeded firms -- the second call's summary must report zero
        newly-inserted firms and all 10 as skipped (already present).
        """
        from edgar_warehouse.mdm.seed.audit_firms import PCAOB_SEED, seed_audit_firms

        def _audit_firm_counts() -> tuple[int, int]:
            firm_rows = session.execute(select(func.count()).select_from(MdmAuditFirm)).scalar_one()
            # MdmEntity has no is_active column -- is_quarantined.is_(False) is the
            # correct "live" filter (see test_node_resolution_is_idempotent_across_entity_types).
            entity_rows = session.execute(
                select(func.count())
                .select_from(MdmEntity)
                .where(MdmEntity.entity_type == "audit_firm", MdmEntity.is_quarantined.is_(False))
            ).scalar_one()
            return firm_rows, entity_rows

        first_summary = seed_audit_firms(session)
        first_firm_count, first_entity_count = _audit_firm_counts()

        second_summary = seed_audit_firms(session)
        second_firm_count, second_entity_count = _audit_firm_counts()

        assert first_summary["inserted"] == len(PCAOB_SEED)
        assert first_firm_count == len(PCAOB_SEED)
        assert first_entity_count == len(PCAOB_SEED)

        assert second_summary["inserted"] == 0, (
            f"second seed_audit_firms() call inserted {second_summary['inserted']} new firms -- "
            f"expected 0 (lookup-before-insert should skip all already-seeded firms)"
        )
        assert second_summary["skipped"] == len(PCAOB_SEED)
        assert second_firm_count == first_firm_count == len(PCAOB_SEED)
        assert second_entity_count == first_entity_count == len(PCAOB_SEED)


# ---------------------------------------------------------------------------
# INSTITUTIONAL_HOLDS CIK-range batching (06-01, D-03, EDGE-11)
#
# _derive_institutional_holds reads sec_thirteenf_holding -- the largest
# silver table -- in bounded CIK-range chunks (`WHERE cik BETWEEN ? AND ?`)
# instead of one unbounded silver.fetch() that loads every row into memory.
# These tests use their own isolated session-per-run helper (rather than the
# shared `session`/`fixture_world` fixtures) because equivalence/idempotency
# assertions need independent before/after state across multiple full
# derive_relationships() runs.
# ---------------------------------------------------------------------------

_BATCH_THIRTEENF_ROWS: list[dict] = [
    {
        "cik": 910002, "accession_number": "acc-a",
        "period_of_report": "2023-12-31", "cusip": "037833100",
        "issuer_name": "Apple Inc", "security_title": "Common Stock",
        "shares_held": 1000, "market_value": 15000000,
        "put_call": None, "discretion_type": "SOLE", "security_class": None,
    },
    {
        "cik": 910003, "accession_number": "acc-b",
        "period_of_report": "2023-12-31", "cusip": "594918104",
        "issuer_name": "Microsoft Corp", "security_title": "Common Stock",
        "shares_held": 500, "market_value": 7000000,
        "put_call": None, "discretion_type": "SOLE", "security_class": None,
    },
    {
        "cik": 910004, "accession_number": "acc-c",
        "period_of_report": "2023-12-31", "cusip": "023135106",
        "issuer_name": "Amazon.com Inc", "security_title": "Common Stock",
        "shares_held": 200, "market_value": 3000000,
        "put_call": None, "discretion_type": "SOLE", "security_class": None,
    },
]


def _fresh_batching_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sess = Session(engine)
    _seed_registry(sess)
    return sess


def _seed_batching_advisers(session: Session, ciks: list[int]) -> dict[int, str]:
    adviser_ids: dict[int, str] = {}
    for cik in ciks:
        eid = _add_entity(session, "adviser")
        session.add(MdmAdviser(entity_id=eid, cik=cik, canonical_name=f"Batch Adviser {cik}"))
        adviser_ids[cik] = eid
    session.commit()
    return adviser_ids


class TestInstitutionalHoldsBatching:
    """CIK-range batching regression tests for _derive_institutional_holds."""

    def _run(
        self,
        monkeypatch,
        batch_size: int,
        rows: Optional[list[dict]] = None,
        target_per_type: Optional[int] = None,
    ) -> tuple[dict, set, StubSilver]:
        rows = rows if rows is not None else _BATCH_THIRTEENF_ROWS
        session = _fresh_batching_session()
        _seed_batching_advisers(session, sorted({r["cik"] for r in rows}))
        monkeypatch.setattr(
            "edgar_warehouse.mdm.pipeline._INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE", batch_size
        )
        silver = StubSilver({"sec_thirteenf_holding": rows})
        pipe = MDMPipeline(session=session, silver=silver)
        summary = pipe.derive_relationships(
            target_per_type=target_per_type, relationship_types=["INSTITUTIONAL_HOLDS"]
        )
        # Compare edges by (adviser CIK, security CUSIP) rather than raw
        # entity_id -- entity_ids are freshly-generated UUIDs per independent
        # session, so single-batch and multi-batch runs (each its own session)
        # never share entity_id values even when they represent the same
        # logical edge.
        adviser_cik_by_id = dict(session.execute(select(MdmAdviser.entity_id, MdmAdviser.cik)).all())
        security_cusip_by_id = dict(session.execute(select(MdmSecurity.entity_id, MdmSecurity.cusip)).all())
        edges = {
            (adviser_cik_by_id.get(r.source_entity_id), security_cusip_by_id.get(r.target_entity_id))
            for r in session.scalars(
                select(MdmRelationshipInstance)
                .join(MdmRelationshipType)
                .where(MdmRelationshipType.rel_type_name == "INSTITUTIONAL_HOLDS")
            )
        }
        session.close()
        return summary["INSTITUTIONAL_HOLDS"], edges, silver

    def test_batch_equivalence_single_vs_multi_batch(self, monkeypatch):
        """Test A: batched output equals single-query output for identical source
        data, and CIK bounds are supplied via bound params, not interpolated into
        the SQL text (T-06-01)."""
        single_summary, single_edges, _ = self._run(monkeypatch, batch_size=100_000)
        multi_summary, multi_edges, silver = self._run(monkeypatch, batch_size=1)

        assert single_summary["inserted"] == multi_summary["inserted"] == 3
        assert single_edges == multi_edges

        between_calls = [c for c in silver.calls if c[1] is not None and len(c[1]) == 2]
        assert between_calls, "expected at least one CIK-range BETWEEN batch call"
        for sql, params in between_calls:
            assert "BETWEEN ? AND ?" in sql, "CIK bounds must be bound placeholders, not literals"
            assert isinstance(params[0], int) and isinstance(params[1], int)

    def test_accumulation_across_batches(self, monkeypatch):
        """Test B: inserted/skipped counters accumulate across batches, not reset
        per batch -- assert inserted == sum of per-batch new rows."""
        summary, edges, silver = self._run(monkeypatch, batch_size=1)
        between_calls = [c for c in silver.calls if c[1] is not None and len(c[1]) == 2]
        # 3 distinct CIKs with batch_size=1 -> one BETWEEN-bounded call per CIK.
        assert len(between_calls) == 3
        # If counters reset per batch, `inserted` would reflect only the final
        # batch's own contribution (1); accumulation must sum all 3 batches.
        assert summary["inserted"] == 3 == len(edges)

    def test_cross_batch_early_exit(self, monkeypatch):
        """Test C: with target_per_type/remaining set below the total available,
        derivation stops at the target and does not over-insert across batch
        boundaries."""
        summary, edges, _ = self._run(monkeypatch, batch_size=1, target_per_type=2)
        assert summary["inserted"] == 2
        assert len(edges) == 2

    def test_missing_source_table_single_skip(self, monkeypatch, session):
        """Test D: missing sec_thirteenf_holding -> (0,0,0,0,0), raises no
        exception, and the missing-table skip path is exercised exactly once
        (not once per CIK batch)."""
        monkeypatch.setattr(
            "edgar_warehouse.mdm.pipeline._INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE", 1
        )
        silver = MissingTableSilver("sec_thirteenf_holding")
        pipe = MDMPipeline(session=session, silver=silver)
        summary = pipe.derive_relationships(
            target_per_type=1, relationship_types=["INSTITUTIONAL_HOLDS"]
        )
        assert summary["INSTITUTIONAL_HOLDS"]["inserted"] == 0
        assert summary["INSTITUTIONAL_HOLDS"]["skipped"] == 0
        # Exactly one query attempted (the CIK-bounds lookup) -- not one skip
        # event per would-be CIK batch.
        assert len(silver.queries) == 1
        assert "sec_thirteenf_holding" in silver.queries[0]

    def test_missing_source_table_second_joined_table_skip(self, monkeypatch, session):
        """Regression (2026-07-22): bounds_sql/base_sql for INSTITUTIONAL_HOLDS
        joins sec_thirteenf_holding AND sec_thirteenf_filing, but the graceful
        missing-source-table skip only checked for sec_thirteenf_holding in the
        error message. A real prod run where sec_thirteenf_filing (not
        sec_thirteenf_holding) was the absent table hit an uncaught
        CatalogException and crashed the whole `mdm mastering` command instead of
        emitting the same skip. Declaring both joined table names must catch
        either one being reported missing."""
        monkeypatch.setattr(
            "edgar_warehouse.mdm.pipeline._INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE", 1
        )
        silver = MissingTableSilver("sec_thirteenf_filing")
        pipe = MDMPipeline(session=session, silver=silver)
        summary = pipe.derive_relationships(
            target_per_type=1, relationship_types=["INSTITUTIONAL_HOLDS"]
        )
        assert summary["INSTITUTIONAL_HOLDS"]["inserted"] == 0
        assert summary["INSTITUTIONAL_HOLDS"]["skipped"] == 0
        assert len(silver.queries) == 1

    def test_commits_periodically_at_each_cik_batch_boundary(self, monkeypatch):
        """mdm-run-throughput Ticket 06: _derive_institutional_holds must commit
        after every CIK-range batch, not just once at the very end of the whole
        type (derive_relationships'/_derive_one's single final commit) -- the
        same durability/visibility gap Ticket 04 fixed for _run_grouped_concurrent,
        found live in prod sitting on one uncommitted transaction for 3h24min+ on
        INSTITUTIONAL_HOLDS specifically (sec_thirteenf_holding, 6.8M rows).

        3 distinct CIKs, batch_size=1 -> 3 CIK-range batches -> expect 3 commits
        from this type's own periodic-commit path (plus the final
        worker_session.commit() from _derive_one, which fires on an
        already-clean session and is a safe no-op event-wise here since SQLite
        emits a commit event only when there's something to commit)."""
        session = _fresh_batching_session()
        ciks = sorted({r["cik"] for r in _BATCH_THIRTEENF_ROWS})
        _seed_batching_advisers(session, ciks)
        monkeypatch.setattr(
            "edgar_warehouse.mdm.pipeline._INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE", 1
        )
        silver = StubSilver({"sec_thirteenf_holding": _BATCH_THIRTEENF_ROWS})
        pipe = MDMPipeline(session=session, silver=silver)

        commit_count = [0]

        def _on_commit(_conn):
            commit_count[0] += 1

        event.listen(session.get_bind(), "commit", _on_commit)

        summary = pipe.derive_relationships(relationship_types=["INSTITUTIONAL_HOLDS"])

        assert summary["INSTITUTIONAL_HOLDS"]["inserted"] == 3
        assert commit_count[0] >= 3, (
            f"expected at least 3 periodic commits (one per CIK batch), got {commit_count[0]} -- "
            "periodic mid-type commit is not firing"
        )
        session.close()

    def test_ensure_security_by_cusip_cache_batches_round_trips_not_one_per_row(
        self, monkeypatch
    ):
        """mdm-run-throughput Ticket 07: repeated CUSIPs across many holding rows
        must not each pay a fresh entity_id SELECT round trip -- real measurement,
        2026-09-08: sec_thirteenf_holding has 6,799,919 rows across only 41,225
        distinct CUSIPs (~165x repetition). 3 rows, 2 sharing one CUSIP, batch_size
        large enough to keep them in one batch -> the shared CUSIP's entity_id
        SELECT must fire once, not twice."""
        session = _fresh_batching_session()
        rows = [
            {
                "cik": 920001, "accession_number": "acc-x1",
                "period_of_report": "2023-12-31", "cusip": "999999999",
                "issuer_name": "Repeat Co", "security_title": "Common Stock",
                "shares_held": 100, "market_value": 1000,
                "put_call": None, "discretion_type": "SOLE", "security_class": None,
            },
            {
                "cik": 920002, "accession_number": "acc-x2",
                "period_of_report": "2023-12-31", "cusip": "999999999",
                "issuer_name": "Repeat Co", "security_title": "Common Stock",
                "shares_held": 200, "market_value": 2000,
                "put_call": None, "discretion_type": "SOLE", "security_class": None,
            },
            {
                "cik": 920003, "accession_number": "acc-x3",
                "period_of_report": "2023-12-31", "cusip": "888888888",
                "issuer_name": "Other Co", "security_title": "Common Stock",
                "shares_held": 300, "market_value": 3000,
                "put_call": None, "discretion_type": "SOLE", "security_class": None,
            },
        ]
        _seed_batching_advisers(session, [920001, 920002, 920003])
        monkeypatch.setattr(
            "edgar_warehouse.mdm.pipeline._INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE", 10_000
        )
        silver = StubSilver({"sec_thirteenf_holding": rows})
        pipe = MDMPipeline(session=session, silver=silver)

        entity_id_select_count = [0]

        def _count_security_lookups(conn, cursor, statement, parameters, context, executemany):
            if "mdm_security" in statement and "cusip" in statement and "SELECT" in statement.upper():
                entity_id_select_count[0] += 1

        event.listen(session.get_bind(), "before_cursor_execute", _count_security_lookups)

        summary = pipe.derive_relationships(relationship_types=["INSTITUTIONAL_HOLDS"])

        assert summary["INSTITUTIONAL_HOLDS"]["inserted"] == 3
        # 2 distinct CUSIPs -> exactly 2 real by-cusip entity_id lookups. Without
        # the cache this would be 3 (one per row); this precise bound is what
        # actually distinguishes cached from uncached behavior -- a looser bound
        # would pass either way and prove nothing.
        assert entity_id_select_count[0] == 2, (
            f"expected exactly 2 by-cusip SELECTs (one per distinct CUSIP), got "
            f"{entity_id_select_count[0]} for 3 rows / 2 distinct CUSIPs -- "
            "the repeated CUSIP's second row did not hit the cache"
        )

    def test_ensure_security_by_cusip_cache_preserves_backfill_correctness(
        self, monkeypatch
    ):
        """mdm-run-throughput Ticket 07: a CUSIP first seen with no security_class
        (cached as unsatisfied) must still get backfilled when a LATER row for the
        same CUSIP supplies one -- the cache must not silently skip a real
        backfill the unmemoized code would have performed."""
        session = _fresh_batching_session()
        rows = [
            {
                "cik": 920001, "accession_number": "acc-y1",
                "period_of_report": "2023-12-31", "cusip": "777777777",
                "issuer_name": "Backfill Co", "security_title": "Common Stock",
                "shares_held": 100, "market_value": 1000,
                "put_call": None, "discretion_type": "SOLE",
                "security_class": None,  # first row: no class to offer
            },
            {
                "cik": 920002, "accession_number": "acc-y2",
                "period_of_report": "2023-12-31", "cusip": "777777777",
                "issuer_name": "Backfill Co", "security_title": "Common Stock",
                "shares_held": 200, "market_value": 2000,
                "put_call": None, "discretion_type": "SOLE",
                "security_class": "COM",  # second row: offers a class
            },
        ]
        _seed_batching_advisers(session, [920001, 920002])
        monkeypatch.setattr(
            "edgar_warehouse.mdm.pipeline._INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE", 10_000
        )
        silver = StubSilver({"sec_thirteenf_holding": rows})
        pipe = MDMPipeline(session=session, silver=silver)

        summary = pipe.derive_relationships(relationship_types=["INSTITUTIONAL_HOLDS"])
        assert summary["INSTITUTIONAL_HOLDS"]["inserted"] == 2

        security_class = session.scalar(
            select(MdmSecurity.security_class).where(MdmSecurity.cusip == "777777777")
        )
        assert security_class == "COM", (
            "second row's security_class was not backfilled onto the security "
            "created by the first (cache-unsatisfied) row"
        )

    def test_batching_idempotent_on_rerun(self, monkeypatch):
        """Test E: running derive twice over the same batched fixture inserts 0
        rows on the second run."""
        session = _fresh_batching_session()
        ciks = sorted({r["cik"] for r in _BATCH_THIRTEENF_ROWS})
        _seed_batching_advisers(session, ciks)
        monkeypatch.setattr(
            "edgar_warehouse.mdm.pipeline._INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE", 1
        )
        silver = StubSilver({"sec_thirteenf_holding": _BATCH_THIRTEENF_ROWS})
        pipe = MDMPipeline(session=session, silver=silver)

        first = pipe.derive_relationships(relationship_types=["INSTITUTIONAL_HOLDS"])
        second = pipe.derive_relationships(relationship_types=["INSTITUTIONAL_HOLDS"])

        assert first["INSTITUTIONAL_HOLDS"]["inserted"] == 3
        assert second["INSTITUTIONAL_HOLDS"]["inserted"] == 0
        session.close()

    def test_institutional_holds_primes_scoped_to_each_cik_batchs_advisers(
        self, monkeypatch
    ):
        """mdm-oom-institutional-holds-guard fix: each CIK-range batch must
        prime only its own advisers, not the whole INSTITUTIONAL_HOLDS type
        -- the same per-batch bound the mdm-oom-manages-fund fix proved for
        MANAGES_FUND's CRD batching. No single prime() call may ever see
        another batch's advisers primed at the same time."""
        import edgar_warehouse.mdm.pipeline as pipeline_module
        from edgar_warehouse.mdm.graph import GraphSyncEngine

        monkeypatch.setattr(
            pipeline_module, "_INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE", 1
        )

        session = _fresh_batching_session()
        ciks = sorted({r["cik"] for r in _BATCH_THIRTEENF_ROWS})
        adviser_id_by_cik = _seed_batching_advisers(session, ciks)

        prime_calls: list[frozenset] = []
        original_prime = GraphSyncEngine.prime_relationship_type

        def spy_prime(self, rel_type_name, **kwargs):
            if rel_type_name == "INSTITUTIONAL_HOLDS":
                prime_calls.append(frozenset(kwargs.get("source_entity_ids") or []))
            return original_prime(self, rel_type_name, **kwargs)

        monkeypatch.setattr(GraphSyncEngine, "prime_relationship_type", spy_prime)

        silver = StubSilver({"sec_thirteenf_holding": _BATCH_THIRTEENF_ROWS})
        pipe = MDMPipeline(session=session, silver=silver)
        summary = pipe.derive_relationships(relationship_types=["INSTITUTIONAL_HOLDS"])
        session.close()

        assert summary["INSTITUTIONAL_HOLDS"]["inserted"] == 3

        # 3 distinct CIKs, batch size 1 -> 3 batches, each priming exactly
        # one adviser and no batch's set overlapping another's.
        assert len(prime_calls) == 3
        assert all(prime_calls), prime_calls
        assert set.union(*(set(c) for c in prime_calls)) == set(adviser_id_by_cik.values())
        for i, a in enumerate(prime_calls):
            for b in prime_calls[i + 1:]:
                assert not (a & b), f"overlapping prime scopes: {a} and {b}"


def _checkpoint(session: Session, key: str) -> Optional[MdmRelationshipDerivationCheckpoint]:
    # Not session.get(): its identity-map shortcut would return a
    # previously-loaded (and, across this file's multi-call tests, now
    # stale) object without re-querying. A plain select always re-reads.
    session.expire_all()
    return session.execute(
        select(MdmRelationshipDerivationCheckpoint).where(
            MdmRelationshipDerivationCheckpoint.checkpoint_key == key
        )
    ).scalar_one_or_none()


class TestInstitutionalHoldsResumableCursor:
    """mdm-relationship-versioning-gap Ticket 01: a target_per_type-capped
    run must persist a resume cursor (not just fail to advance the
    watermark) so the NEXT call continues from where it left off instead
    of restarting CIK-range iteration from min_cik every time."""

    def test_capped_run_persists_cursor_and_resumes_without_rescanning(self, monkeypatch):
        monkeypatch.setattr(
            "edgar_warehouse.mdm.pipeline._INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE", 1
        )
        session = _fresh_batching_session()
        ciks = sorted({r["cik"] for r in _BATCH_THIRTEENF_ROWS})  # 910002, 910003, 910004
        _seed_batching_advisers(session, ciks)
        silver = StubSilver({"sec_thirteenf_holding": _BATCH_THIRTEENF_ROWS})
        pipe = MDMPipeline(session=session, silver=silver)

        first = pipe.derive_relationships(
            target_per_type=2, relationship_types=["INSTITUTIONAL_HOLDS"]
        )
        assert first["INSTITUTIONAL_HOLDS"]["inserted"] == 2

        # Only 2 of 3 CIKs were ever visited -- the sweep is not complete,
        # so watermark_value must stay unset and cursor_value must point
        # exactly one past the last CIK actually processed (910003).
        checkpoint = _checkpoint(session, "INSTITUTIONAL_HOLDS")
        assert checkpoint is not None
        assert checkpoint.watermark_value is None
        assert checkpoint.cursor_value == "910004"

        # A second, unbounded call must resume at CIK 910004 -- not
        # rescan 910002/910003, which the first call already covered.
        between_calls_before = [c for c in silver.calls if c[1] is not None and len(c[1]) == 2]
        second = pipe.derive_relationships(relationship_types=["INSTITUTIONAL_HOLDS"])
        assert second["INSTITUTIONAL_HOLDS"]["inserted"] == 1
        between_calls_after = [c for c in silver.calls if c[1] is not None and len(c[1]) == 2]
        new_between_calls = between_calls_after[len(between_calls_before):]
        assert len(new_between_calls) == 1
        _, params = new_between_calls[0]
        assert params == [910004, 910004], (
            "resumed call must fetch only the unswept CIK, not restart from min_cik"
        )

        # The sweep is now complete (910004 was the true max_cik) -- the
        # cursor must reset so the NEXT sweep starts fresh from the
        # beginning again.
        checkpoint = _checkpoint(session, "INSTITUTIONAL_HOLDS")
        assert checkpoint.cursor_value is None
        session.close()

    def test_reconciliation_pass_never_reads_or_writes_the_cursor(self, monkeypatch):
        """A reconciliation pass always scans the full range from
        min_cik, regardless of an in-progress ordinary-pass cursor, and
        must leave that cursor untouched for the ordinary pass to resume
        later."""
        monkeypatch.setattr(
            "edgar_warehouse.mdm.pipeline._INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE", 1
        )
        session = _fresh_batching_session()
        ciks = sorted({r["cik"] for r in _BATCH_THIRTEENF_ROWS})
        _seed_batching_advisers(session, ciks)
        silver = StubSilver({"sec_thirteenf_holding": _BATCH_THIRTEENF_ROWS})
        pipe = MDMPipeline(session=session, silver=silver)

        pipe.derive_relationships(target_per_type=2, relationship_types=["INSTITUTIONAL_HOLDS"])
        checkpoint_before = _checkpoint(session, "INSTITUTIONAL_HOLDS")
        assert checkpoint_before.cursor_value == "910004"

        pipe.derive_relationships(
            relationship_types=["INSTITUTIONAL_HOLDS"], reconciliation_pass=True
        )
        checkpoint_after = _checkpoint(session, "INSTITUTIONAL_HOLDS")
        assert checkpoint_after.cursor_value == "910004", (
            "a reconciliation pass must not disturb the ordinary pass's in-progress cursor"
        )
        session.close()

    def _rows_with_ingested_at(self) -> list[dict]:
        base = {
            "issuer_name": "Apple Inc", "security_title": "Common Stock",
            "shares_held": 1000, "market_value": 15000000,
            "put_call": None, "discretion_type": "SOLE", "security_class": None,
            "period_of_report": "2024-03-31",
        }
        return [
            {**base, "cik": 910002, "accession_number": "acc-a", "cusip": "037833100",
             "ingested_at": datetime(2024, 1, 1, tzinfo=timezone.utc)},
            {**base, "cik": 910003, "accession_number": "acc-b", "cusip": "594918104",
             "ingested_at": datetime(2024, 3, 1, tzinfo=timezone.utc)},
            {**base, "cik": 910004, "accession_number": "acc-c", "cusip": "023135106",
             "ingested_at": datetime(2024, 6, 1, tzinfo=timezone.utc)},
        ]

    def test_reconciliation_pass_advances_watermark_when_it_completes_a_full_scan(
        self, monkeypatch
    ):
        """Regression for a real bug this ticket's own code review found:
        the diff's first draft unconditionally suppressed watermark writes
        during reconciliation, an unstated behavior change from the
        pre-existing (pre-Ticket-01) contract -- every other relationship
        type still advances its watermark during reconciliation. A
        genuinely complete (uncapped) reconciliation scan must still
        advance the watermark, exactly as it did before this ticket."""
        rows = self._rows_with_ingested_at()
        session = _fresh_batching_session()
        _seed_batching_advisers(session, [r["cik"] for r in rows])
        silver = StubSilver({"sec_thirteenf_holding": rows})
        pipe = MDMPipeline(session=session, silver=silver)

        summary = pipe.derive_relationships(
            relationship_types=["INSTITUTIONAL_HOLDS"], reconciliation_pass=True
        )
        assert summary["INSTITUTIONAL_HOLDS"]["inserted"] == 3

        checkpoint = _checkpoint(session, "INSTITUTIONAL_HOLDS")
        assert checkpoint is not None
        assert checkpoint.watermark_value == datetime(2024, 6, 1, tzinfo=timezone.utc).isoformat()
        assert checkpoint.cursor_value is None
        session.close()

    def test_reconciliation_pass_does_not_advance_watermark_when_capped(self, monkeypatch):
        """The other half of the same regression: a reconciliation run
        that itself gets cut short by `remaining` must NOT advance the
        watermark off a partial scan -- that would reintroduce this exact
        ticket's bug on the reconciliation path, just with no cursor to
        recover from it."""
        rows = self._rows_with_ingested_at()
        monkeypatch.setattr(
            "edgar_warehouse.mdm.pipeline._INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE", 1
        )
        session = _fresh_batching_session()
        _seed_batching_advisers(session, [r["cik"] for r in rows])
        silver = StubSilver({"sec_thirteenf_holding": rows})
        pipe = MDMPipeline(session=session, silver=silver)

        summary = pipe.derive_relationships(
            target_per_type=2, relationship_types=["INSTITUTIONAL_HOLDS"],
            reconciliation_pass=True,
        )
        assert summary["INSTITUTIONAL_HOLDS"]["inserted"] == 2

        checkpoint = _checkpoint(session, "INSTITUTIONAL_HOLDS")
        assert checkpoint is None, (
            "a capped reconciliation pass must not create a checkpoint row at all -- "
            "no watermark write, and reconciliation never persists cursor state"
        )
        session.close()


class TestManagesFundResumableCursor:
    """Same resumable-cursor fix as INSTITUTIONAL_HOLDS above, applied to
    MANAGES_FUND's CRD-range batching."""

    def _seed_advisers_and_funds(self, session: Session, count: int) -> list[str]:
        crds = []
        for index in range(count):
            adviser_id = _add_entity(session, "adviser")
            fund_id = _add_entity(session, "fund")
            crd_number = str(700000 + index)
            crds.append(crd_number)
            session.add(MdmAdviser(
                entity_id=adviser_id, crd_number=crd_number,
                canonical_name=f"Cursor Adviser {index}",
            ))
            session.add(MdmFund(
                entity_id=fund_id, adviser_entity_id=adviser_id,
                private_fund_id=f"805-{700000 + index}", canonical_name=f"Cursor Fund {index}",
            ))
        session.commit()
        return sorted(crds)

    def _filings_and_funds(self, crds: list[str]) -> tuple[list[dict], list[dict]]:
        filings, funds = [], []
        for crd in crds:
            accession = f"iapd-adv:{crd}"
            filings.append({
                "accession_number": accession, "crd_number": crd,
                "effective_date": date(2025, 1, 1), "filing_action": "annual_amendment",
            })
            funds.append({
                "accession_number": accession, "adviser_crd_number": crd,
                "private_fund_id": f"805-{crd}", "filing_id": crd,
                "schedule_section": "7B1", "reporting_role": "detailed_reporter",
                "effective_date": date(2025, 1, 1), "filing_action": "annual_amendment",
                "source_sha256": f"sha-{crd}",
            })
        return filings, funds

    def test_capped_run_persists_cursor_and_resumes_without_rescanning(self, session, monkeypatch):
        monkeypatch.setattr("edgar_warehouse.mdm.pipeline._MANAGES_FUND_CRD_BATCH_SIZE", 2)
        crds = self._seed_advisers_and_funds(session, 5)  # batch size 2 -> 2/2/1
        filings, funds = self._filings_and_funds(crds)
        silver = StubSilver({"sec_adv_filing": filings, "sec_adv_private_fund": funds})
        pipe = MDMPipeline(session=session, silver=silver)

        first = pipe.derive_relationships(target_per_type=2, relationship_types=["MANAGES_FUND"])
        assert first["MANAGES_FUND"]["inserted"] == 2

        # Only the first CRD batch (crds[0], crds[1]) was ever visited --
        # the sweep is not complete, so cursor_value must point exactly at
        # the first unswept CRD (crds[2]).
        checkpoint = _checkpoint(session, "MANAGES_FUND")
        assert checkpoint is not None
        assert checkpoint.watermark_value is None
        assert checkpoint.cursor_value == crds[2]

        # A second, unbounded call must resume at crds[2:] -- not rescan
        # crds[0]/crds[1], which the first call already covered.
        in_calls_before = [c for c in silver.calls if c[1] is not None and " IN (" in c[0].upper()]
        second = pipe.derive_relationships(relationship_types=["MANAGES_FUND"])
        assert second["MANAGES_FUND"]["inserted"] == 3
        in_calls_after = [c for c in silver.calls if c[1] is not None and " IN (" in c[0].upper()]
        new_in_calls = in_calls_after[len(in_calls_before):]
        touched_crds = {crd for _, params in new_in_calls for crd in params}
        assert touched_crds == set(crds[2:]), (
            "resumed call must fetch only the unswept CRDs, not restart from the beginning"
        )

        # The sweep is now complete -- the cursor must reset so the NEXT
        # sweep starts fresh from the beginning again.
        checkpoint = _checkpoint(session, "MANAGES_FUND")
        assert checkpoint.cursor_value is None

    def test_reconciliation_pass_never_reads_or_writes_the_cursor(self, session, monkeypatch):
        monkeypatch.setattr("edgar_warehouse.mdm.pipeline._MANAGES_FUND_CRD_BATCH_SIZE", 2)
        crds = self._seed_advisers_and_funds(session, 5)
        filings, funds = self._filings_and_funds(crds)
        silver = StubSilver({"sec_adv_filing": filings, "sec_adv_private_fund": funds})
        pipe = MDMPipeline(session=session, silver=silver)

        pipe.derive_relationships(target_per_type=2, relationship_types=["MANAGES_FUND"])
        checkpoint_before = _checkpoint(session, "MANAGES_FUND")
        assert checkpoint_before.cursor_value == crds[2]

        pipe.derive_relationships(relationship_types=["MANAGES_FUND"], reconciliation_pass=True)
        checkpoint_after = _checkpoint(session, "MANAGES_FUND")
        assert checkpoint_after.cursor_value == crds[2], (
            "a reconciliation pass must not disturb the ordinary pass's in-progress cursor"
        )


class TestIsInsiderDeactivation:
    """mdm-relationship-versioning-gap Ticket 02: a role/title change for
    an already-known (person, issuer) pair must close the prior open
    version instead of colliding with it as an unresolvable same-source
    conflict."""

    def _seed_pair(self, session: Session) -> tuple[str, str]:
        person_id = _add_entity(session, "person")
        company_id = _add_entity(session, "company")
        session.add(MdmPerson(entity_id=person_id, owner_cik=910102, canonical_name="Reporting Person"))
        session.add(MdmCompany(entity_id=company_id, cik=910001, canonical_name="Issuer Corp"))
        session.commit()
        return person_id, company_id

    @staticmethod
    def _owner_row(
        *, accession_number: str, period_of_report: date,
        is_director: bool = False, is_officer: bool = False, officer_title: Optional[str] = None,
    ) -> dict:
        return {
            "accession_number": accession_number, "owner_index": 0,
            "owner_cik": 910102, "owner_name": "Reporting Person",
            "is_director": is_director, "is_officer": is_officer,
            "is_ten_percent_owner": False, "is_other": False,
            "officer_title": officer_title,
            "issuer_cik": 910001, "period_of_report": period_of_report,
        }

    def test_role_change_closes_prior_open_version_and_opens_new_one(self, session):
        self._seed_pair(session)
        rows = [
            self._owner_row(
                accession_number="0001", period_of_report=date(2024, 10, 16), is_officer=True,
            ),
            self._owner_row(
                accession_number="0002", period_of_report=date(2025, 10, 8), is_director=True,
            ),
        ]
        pipe = MDMPipeline(session=session, silver=StubSilver({"FROM sec_ownership_reporting_owner": rows}))

        summary = pipe.derive_relationships(relationship_types=["IS_INSIDER"])
        assert summary["IS_INSIDER"]["inserted"] == 2

        all_rows = list(session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "IS_INSIDER")
        ))
        assert len(all_rows) == 2
        closed = [r for r in all_rows if r.valid_to_date is not None]
        open_versions = [r for r in all_rows if r.valid_to_date is None]
        assert len(closed) == 1
        assert len(open_versions) == 1
        assert closed[0].properties == {"role": "officer", "title": ""}
        assert closed[0].valid_to_date == date(2025, 10, 8)
        assert open_versions[0].properties == {"role": "director", "title": ""}
        # The whole point of this fix: the newer, more accurate role must
        # actually be visible as current -- not quarantined or superseded.
        assert open_versions[0].quarantined is False
        assert open_versions[0].superseded_by_version_id is None

    def test_identical_role_refiled_leaves_prior_version_open_and_does_not_close(self, session):
        """A re-filing that reports the SAME role/title at a later date is
        not a role change -- ensure_relationship's own identical-properties
        handling applies (no conflict), and this fix must not close
        anything just because the dates differ."""
        self._seed_pair(session)
        rows = [
            self._owner_row(
                accession_number="0001", period_of_report=date(2024, 10, 16), is_officer=True,
                officer_title="CFO",
            ),
            self._owner_row(
                accession_number="0002", period_of_report=date(2025, 10, 8), is_officer=True,
                officer_title="CFO",
            ),
        ]
        pipe = MDMPipeline(session=session, silver=StubSilver({"FROM sec_ownership_reporting_owner": rows}))

        pipe.derive_relationships(relationship_types=["IS_INSIDER"])

        all_rows = list(session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "IS_INSIDER")
        ))
        # Both rows carry identical properties -- nothing here should ever
        # be closed by this fix; whether ensure_relationship treats the
        # second as a fresh open version or merges it is out of this
        # fix's scope, but no row may have a valid_to_date set.
        assert all(r.valid_to_date is None for r in all_rows)

    def test_reprocessing_an_older_row_does_not_close_a_newer_open_version(self, session):
        """The chronological guard: reprocessing a row with an OLDER
        period_of_report than the currently open version (e.g. a
        full-history issuer_ciks resync revisiting historical filings, or
        an out-of-order late-filed amendment) must never close the newer,
        already-correct version using a stale date."""
        person_id, company_id = self._seed_pair(session)
        # Insert the NEWER (director) version directly, as if an earlier
        # run had already correctly derived and left it open.
        from edgar_warehouse.mdm.database import MdmRelationshipInstance as MRI
        from edgar_warehouse.mdm.database import relationship_logical_id
        rel_type_id = session.execute(
            select(MdmRelationshipType.rel_type_id).where(MdmRelationshipType.rel_type_name == "IS_INSIDER")
        ).scalar_one()
        existing = MRI(
            relationship_id=relationship_logical_id(rel_type_id, person_id, company_id),
            rel_type_id=rel_type_id,
            source_entity_id=person_id,
            target_entity_id=company_id,
            properties={"role": "director", "title": ""},
            effective_from=date(2025, 10, 8),
            valid_from_date=date(2025, 10, 8),
            valid_to_date=None,
            source_system="ownership_filing",
            source_accession="0002",
        )
        session.add(existing)
        session.commit()

        # Now reprocess an OLDER officer row for the same pair (as a
        # full-history resync would).
        rows = [
            self._owner_row(
                accession_number="0001", period_of_report=date(2024, 10, 16), is_officer=True,
            ),
        ]
        pipe = MDMPipeline(session=session, silver=StubSilver({"FROM sec_ownership_reporting_owner": rows}))
        pipe.derive_relationships(relationship_types=["IS_INSIDER"], issuer_ciks=[910001])

        session.expire_all()
        director_row = session.get(MRI, existing.instance_id)
        assert director_row.valid_to_date is None, (
            "the newer, already-open director version must not be closed by "
            "reprocessing an older, already-superseded officer row"
        )
        assert director_row.properties == {"role": "director", "title": ""}

    def test_issuer_ciks_scoped_resync_also_closes_on_role_change(self, session):
        """Deactivation must apply in the issuer_ciks-scoped targeted-resync
        branch too, not just the ordinary incremental path."""
        self._seed_pair(session)
        rows = [
            self._owner_row(
                accession_number="0001", period_of_report=date(2024, 10, 16), is_officer=True,
            ),
            self._owner_row(
                accession_number="0002", period_of_report=date(2025, 10, 8), is_director=True,
            ),
        ]
        pipe = MDMPipeline(session=session, silver=StubSilver({"FROM sec_ownership_reporting_owner": rows}))

        pipe.derive_relationships(relationship_types=["IS_INSIDER"], issuer_ciks=[910001])

        all_rows = list(session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "IS_INSIDER")
        ))
        closed = [r for r in all_rows if r.valid_to_date is not None]
        open_versions = [r for r in all_rows if r.valid_to_date is None]
        assert len(closed) == 1
        assert len(open_versions) == 1
        assert open_versions[0].properties == {"role": "director", "title": ""}
        assert open_versions[0].quarantined is False


class TestEmployedByExecDeactivation:
    """mdm-relationship-versioning-gap Ticket 03: a company reporting a
    NEW fiscal year's DEF 14A comp record for an already-known executive
    must close the prior open EMPLOYED_BY version instead of colliding
    with it as an unresolvable same-source conflict (fiscal_year/
    source_accession are always part of ``properties``, so they always
    differ across years). Only the exec/``sec_executive_record`` branch is
    covered here -- the event/Item 5.02 branch already has its own,
    separately-tested closing mechanism, untouched by this ticket."""

    @staticmethod
    def _exec_row(
        *, accession_number: str, fiscal_year: int, exec_role: str,
        total_comp: Optional[int] = 1000000, cik: int = 920401,
    ) -> dict:
        return {
            "cik": cik, "accession_number": accession_number,
            "fiscal_year": fiscal_year, "exec_name": "Career Officer",
            "exec_role": exec_role, "total_comp": total_comp,
            "base_salary": None, "bonus": None, "stock_awards": None,
            "option_awards": None, "non_equity_incentive": None,
        }

    @staticmethod
    def _seed_company(session: Session, cik: int = 920401) -> str:
        company_id = _add_entity(session, "company")
        session.add(MdmCompany(entity_id=company_id, cik=cik, canonical_name="Career Corp"))
        session.commit()
        return company_id

    def test_new_fiscal_year_closes_prior_open_version_and_opens_new_one(self, session):
        self._seed_company(session)
        rows = [
            self._exec_row(
                accession_number="fy2023", fiscal_year=2023, exec_role="CFO",
                total_comp=1000000,
            ),
            self._exec_row(
                accession_number="fy2024", fiscal_year=2024, exec_role="President",
                total_comp=1500000,
            ),
        ]
        pipe = MDMPipeline(session=session, silver=StubSilver({"sec_executive_record": rows}))

        summary = pipe.derive_relationships(relationship_types=["EMPLOYED_BY"])
        assert summary["EMPLOYED_BY"]["inserted"] == 2

        all_rows = list(session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "EMPLOYED_BY")
        ))
        assert len(all_rows) == 2
        closed = [r for r in all_rows if r.valid_to_date is not None]
        open_versions = [r for r in all_rows if r.valid_to_date is None]
        assert len(closed) == 1
        assert len(open_versions) == 1
        assert closed[0].properties["fiscal_year"] == 2023
        assert closed[0].valid_to_date == date(2024, 1, 1)
        assert open_versions[0].properties["fiscal_year"] == 2024
        assert open_versions[0].properties["role"] == "President"
        # The whole point of this fix: the newer, more accurate comp record
        # must actually be visible as current -- not quarantined.
        assert open_versions[0].quarantined is False
        assert open_versions[0].superseded_by_version_id is None

    def test_reprocessing_an_identical_row_does_not_close_anything(self, session):
        """An idempotent rerun of the exact same DEF 14A row (same
        accession_number, same fiscal_year, same role/comp) is not a
        change -- ensure_relationship's own identical-evidence handling
        applies, and this fix must not close anything."""
        self._seed_company(session)
        row = self._exec_row(accession_number="fy2023", fiscal_year=2023, exec_role="CFO")
        pipe = MDMPipeline(
            session=session,
            silver=StubSilver({"sec_executive_record": [row, dict(row)]}),
        )

        summary = pipe.derive_relationships(relationship_types=["EMPLOYED_BY"])
        assert summary["EMPLOYED_BY"]["inserted"] == 1

        all_rows = list(session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "EMPLOYED_BY")
        ))
        assert len(all_rows) == 1
        assert all_rows[0].valid_to_date is None

    def test_reprocessing_an_older_fiscal_year_does_not_close_a_newer_open_version(self, session):
        """The chronological guard: reprocessing an OLDER fiscal year's row
        (e.g. a full-history backfill revisiting historical DEF 14A
        filings) after a NEWER version is already open must never close
        the newer, already-correct version using a stale date."""
        from edgar_warehouse.mdm.database import relationship_logical_id

        company_id = self._seed_company(session)
        # Derive the proxy-stub person id via the real production helper
        # (not a hand-reimplemented UUID5 calculation) -- as if an earlier
        # run had already correctly derived and left the 2024 version open.
        seed_pipe = MDMPipeline(session=session, silver=StubSilver({}))
        person_id = seed_pipe._ensure_proxy_person("Career Officer", 920401, "seed-accession")
        session.commit()

        rel_type_id = session.execute(
            select(MdmRelationshipType.rel_type_id)
            .where(MdmRelationshipType.rel_type_name == "EMPLOYED_BY")
        ).scalar_one()
        existing = MdmRelationshipInstance(
            relationship_id=relationship_logical_id(rel_type_id, person_id, company_id),
            rel_type_id=rel_type_id,
            source_entity_id=person_id,
            target_entity_id=company_id,
            properties={
                "role": "President", "title": "President", "fiscal_year": 2024,
                "total_compensation": 1500000, "stock_awards": None,
                "option_awards": None, "non_equity_incentive": None,
                "source_accession": "fy2024",
            },
            effective_from=date(2024, 1, 1),
            valid_from_date=date(2024, 1, 1),
            valid_to_date=None,
            source_system="proxy_filing",
            source_accession="fy2024",
        )
        session.add(existing)
        session.commit()

        # Reprocess an OLDER fiscal-year row for the same pair.
        row = self._exec_row(accession_number="fy2023", fiscal_year=2023, exec_role="CFO")
        pipe = MDMPipeline(session=session, silver=StubSilver({"sec_executive_record": [row]}))
        pipe.derive_relationships(relationship_types=["EMPLOYED_BY"])

        session.expire_all()
        newer_row = session.get(MdmRelationshipInstance, existing.instance_id)
        assert newer_row.valid_to_date is None, (
            "the newer, already-open 2024 version must not be closed by "
            "reprocessing an older, already-superseded 2023 row"
        )
        assert newer_row.properties["fiscal_year"] == 2024


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

        Also covers EMPLOYED_BY's second source, sec_employment_event: it
        must receive the identical growing-window LIMIT as
        sec_executive_record, not the pre-fix hardcoded `remaining=None`
        (an always-unbounded full table scan on every call, regardless of
        the method's own budget -- found live during mdm-relationship-
        incremental-filters Ticket 01). No sec_employment_event fixture
        rows are needed to prove this: the LIMIT is emitted from the SQL
        text itself before any fixture matching happens, so an empty
        result set for that table doesn't affect this assertion or any of
        the `inserted`/`existing` counts above.
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

        assert len(silver.limits) == 4, (
            "expected two bounded fetches per run -- sec_executive_record and "
            "sec_employment_event, once EMPLOYED_BY's event sub-query is bounded too"
        )
        first_exec_limit, first_event_limit, second_exec_limit, second_event_limit = silver.limits
        existing_at_run2 = second["EMPLOYED_BY"]["existing"]
        remaining_at_run2 = 5 - existing_at_run2

        # `existing` itself must be live (reflect what run 1 created), not a
        # stale/constant value -- otherwise the additive term below is a no-op
        # and the bug resurfaces silently even though the formula "looks" fixed.
        assert existing_at_run2 == first["EMPLOYED_BY"]["inserted"] == 2

        # The precise invariant that distinguishes fixed vs. broken: the second
        # LIMIT must equal existing + max(remaining * 50, 100) -- i.e. it must
        # include the live `existing` addend. A bare assertion that
        # `second_exec_limit > existing` is NOT sufficient to catch the regression
        # here: at this fixture's scale the pre-fix flat limit
        # (max(remaining*50, 100) == 150) already exceeds existing (2), so a
        # looser check would pass against the broken code too (false
        # confidence). The exact value 152 only comes out of existing(2) +
        # max(3*50, 100); the pre-fix formula would emit 150.
        expected_limit = existing_at_run2 + max(remaining_at_run2 * 50, 100)
        assert second_exec_limit == expected_limit == 152, (
            f"second-run sec_executive_record LIMIT ({second_exec_limit}) != existing + "
            f"windowed-remaining ({expected_limit}) -- the `existing` addend is missing "
            f"from the emitted LIMIT, so a stable-order rescan would plateau on the same "
            f"leading slice instead of advancing past converted rows"
        )

        # The bug this test was extended to catch: sec_employment_event must
        # get the SAME formula, not a hardcoded unbounded scan. Before the
        # fix, this sub-query emitted no LIMIT clause at all, so it would
        # never appear in silver.limits -- the len(silver.limits) == 4
        # assertion above already fails first in that case; this assertion
        # additionally locks in that the value itself matches its sibling
        # query exactly, not just "some" limit.
        assert second_event_limit == expected_limit == 152, (
            f"EMPLOYED_BY's sec_employment_event sub-query LIMIT ({second_event_limit}) "
            f"!= the same growing-window formula ({expected_limit}) used by "
            f"sec_executive_record -- the event sub-query must not silently do a full "
            f"unbounded scan while its sibling query is properly bounded"
        )


# ---------------------------------------------------------------------------
# Bulk-loading + multi-threading (make-mdm-path-multi-threaded fix)
#
# Live evidence for this fix (CloudWatch overlap-counting against a real prod
# `mdm mastering --entity-type all` execution, shard-fix-verify-1787134405): company
# resolution showed up to 16 concurrently-open SQL calls (the already-fixed
# mdm-run-throughput map), but the relationship-derivation tail of the same
# command showed exactly 1 -- strictly sequential -- for the entire ~5.6h+
# runtime observed. Root cause, confirmed by reading every _derive_* method:
# only MANAGES_FUND primed its relationship type (prime_relationship_type +
# deferred flush); every other type paid one existing-version SELECT plus one
# session.flush() round trip *per relationship row*, and several types
# (IS_INSIDER, HOLDS, HAS_PARENT_COMPANY, EMPLOYED_BY, AUDITED_BY) also paid a
# fresh MdmPerson/MdmCompany SELECT per row for entity lookups that repeat
# heavily (an issuer's CIK repeats across all its own insiders' rows, etc.).
# Fix: _derive_relationship_type now primes + defers flush for every type
# uniformly, several _derive_* methods bulk-prefetch their entity-ID lookups
# once per batch, and derive_relationships() itself now runs each
# relationship *type* on its own worker thread/session (bounded by
# MDM_RELATIONSHIP_CONCURRENCY), mirroring run_companies' proven
# per-row-worker-session pattern.
# ---------------------------------------------------------------------------

class TestRelationshipDeriveBoundedRoundTrips:
    def test_is_insider_uses_bounded_database_round_trips(self, session, monkeypatch):
        """IS_INSIDER-scale derivation must not issue person/company/edge
        lookups per row. Regression guard mirroring
        test_manages_fund_uses_bounded_database_round_trips: before this fix,
        N inserted IS_INSIDER rows paid N MdmPerson SELECTs (owner lookup),
        N MdmCompany SELECTs (issuer lookup), N mdm_relationship_instance
        SELECTs (existing-version lookup, unprimed), and N session.flush()
        round trips (not deferred) -- all O(rows). This asserts the fixed
        code's SQL/flush counts stay flat as row count grows.
        """
        owners = []
        for index in range(15):
            owner_cik = 950000 + index
            issuer_cik = 910001  # same well-followed issuer for every row
            person_id = _add_entity(session, "person")
            session.add(MdmPerson(
                entity_id=person_id, owner_cik=owner_cik,
                canonical_name=f"Insider {index}",
            ))
            owners.append({
                "accession_number": f"0000-insider-{index}",
                "owner_index": 1,
                "owner_cik": owner_cik,
                "owner_name": f"Insider {index}",
                "is_director": True,
                "is_officer": False,
                "is_ten_percent_owner": False,
                "is_other": False,
                "officer_title": None,
                "issuer_cik": issuer_cik,
                "period_of_report": date(2025, 1, 1),
            })
        issuer_company_id = _add_entity(session, "company")
        session.add(MdmCompany(
            entity_id=issuer_company_id, cik=910001, canonical_name="Issuer Corp",
        ))
        session.commit()

        statements: list[str] = []

        def capture_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
            normalized = " ".join(statement.lower().split())
            if (
                "mdm_person" in normalized
                or "mdm_company" in normalized
                or "mdm_relationship_instance" in normalized
            ):
                statements.append(normalized)

        bind = session.get_bind()
        write_flush_calls = 0
        original_flush = session.flush

        def count_flush(*args, **kwargs):
            nonlocal write_flush_calls
            if session.new:
                write_flush_calls += 1
            return original_flush(*args, **kwargs)

        monkeypatch.setattr(session, "flush", count_flush)
        event.listen(bind, "before_cursor_execute", capture_statement)
        try:
            summary = MDMPipeline(
                session=session,
                silver=StubSilver({"FROM sec_ownership_reporting_owner": owners}),
            ).derive_relationships(relationship_types=["IS_INSIDER"])
        finally:
            event.remove(bind, "before_cursor_execute", capture_statement)

        assert summary["IS_INSIDER"]["inserted"] == 15
        lookup_selects = [
            statement for statement in statements if statement.startswith("select ")
        ]
        assert len(lookup_selects) <= 8, lookup_selects
        assert write_flush_calls <= 2


# ---------------------------------------------------------------------------
# large-profile-unscoped-load-audit, Ticket 01: IS_INSIDER/HOLDS/COMPANY_HOLDS
# still called the shared dispatcher's unconditional, unscoped
# `prime_relationship_type(rel_type_name, defer_flush=True)` (no
# `source_entity_ids`) -- the exact MANAGES_FUND/INSTITUTIONAL_HOLDS OOM
# shape, just not yet at their scale. Live prod measurement 2026-08-22:
# COMPANY_HOLDS grew 3,148 -> 33,398 rows (~10.6x) in roughly 24h, HOLDS grew
# 395 -> 3,093 (~7.8x), IS_INSIDER grew 902 -> 1,552 -- proving "currently
# small" is not a durable safety argument for this specific pattern. Fix
# mirrors _derive_manages_fund_batch/_derive_institutional_holds_batch:
# resolve this invocation's touched source entities first, prime scoped to
# exactly those, run the existing per-row loop, unprime in a finally.
# ---------------------------------------------------------------------------

class TestPrimeScopingForOwnershipDerivedTypes:
    def test_is_insider_primes_scoped_to_touched_persons_not_the_whole_type(
        self, session, fixture_world, monkeypatch
    ):
        # Out-of-scope: an existing IS_INSIDER row for a person this run's
        # source rows never touch. Before the fix, the shared dispatcher's
        # unscoped prime would load this row into the cache regardless.
        sync_engine = GraphSyncEngine.build(session)
        sync_engine.ensure_relationship(
            rel_type_name="IS_INSIDER",
            source_entity_id=fixture_world["individual_person_id"],
            target_entity_id=fixture_world["issuer_company_id"],
            source_system="ownership_filing",
        )
        session.commit()

        prime_calls: list[Optional[frozenset]] = []
        original_prime = GraphSyncEngine.prime_relationship_type

        def spy_prime(self, rel_type_name, **kwargs):
            if rel_type_name == "IS_INSIDER":
                source_entity_ids = kwargs.get("source_entity_ids")
                prime_calls.append(
                    frozenset(source_entity_ids) if source_entity_ids is not None else None
                )
            return original_prime(self, rel_type_name, **kwargs)

        monkeypatch.setattr(GraphSyncEngine, "prime_relationship_type", spy_prime)

        pipe = MDMPipeline(session=session, silver=StubSilver({
            "FROM sec_ownership_reporting_owner": [
                {
                    "accession_number": "0000-new-insider",
                    "owner_index": 0,
                    "owner_cik": 910102,
                    "owner_name": "Reporting Person",
                    "is_director": True,
                    "is_officer": False,
                    "is_ten_percent_owner": False,
                    "is_other": False,
                    "officer_title": None,
                    "issuer_cik": 910001,
                    "period_of_report": date(2025, 1, 1),
                },
            ],
        }))
        summary = pipe.derive_relationships(relationship_types=["IS_INSIDER"])

        assert summary["IS_INSIDER"]["inserted"] == 1
        assert len(prime_calls) == 1
        assert prime_calls[0] is not None, "prime must be scoped, not an unscoped whole-type load"
        assert prime_calls[0] == frozenset({fixture_world["reporting_person_id"]})
        assert fixture_world["individual_person_id"] not in prime_calls[0]

    def test_holds_primes_scoped_to_touched_persons_not_the_whole_type(
        self, session, fixture_world, monkeypatch
    ):
        sync_engine = GraphSyncEngine.build(session)
        sync_engine.ensure_relationship(
            rel_type_name="HOLDS",
            source_entity_id=fixture_world["individual_person_id"],
            target_entity_id=fixture_world["security_entity_id"],
            source_system="ownership_filing",
        )
        session.commit()

        prime_calls: list[Optional[frozenset]] = []
        original_prime = GraphSyncEngine.prime_relationship_type

        def spy_prime(self, rel_type_name, **kwargs):
            if rel_type_name == "HOLDS":
                source_entity_ids = kwargs.get("source_entity_ids")
                prime_calls.append(
                    frozenset(source_entity_ids) if source_entity_ids is not None else None
                )
            return original_prime(self, rel_type_name, **kwargs)

        monkeypatch.setattr(GraphSyncEngine, "prime_relationship_type", spy_prime)

        pipe = MDMPipeline(session=session, silver=StubSilver({
            "FROM sec_ownership_non_derivative_txn": [
                {
                    "accession_number": "0000-new-holds",
                    "owner_index": 0,
                    "txn_index": 0,
                    "security_title": "Common Stock",
                    "transaction_date": None,
                    "shares_owned_after": 100,
                    "ownership_direct_indirect": "D",
                    "owner_cik": 910102,
                    "owner_name": "Reporting Person",
                    "issuer_cik": 910001,
                },
            ],
        }))
        summary = pipe.derive_relationships(relationship_types=["HOLDS"])

        assert summary["HOLDS"]["inserted"] == 1
        assert len(prime_calls) == 1
        assert prime_calls[0] is not None, "prime must be scoped, not an unscoped whole-type load"
        assert prime_calls[0] == frozenset({fixture_world["reporting_person_id"]})
        assert fixture_world["individual_person_id"] not in prime_calls[0]

    def test_company_holds_primes_scoped_to_touched_companies_not_the_whole_type(
        self, session, fixture_world, monkeypatch
    ):
        # Out-of-scope: an existing COMPANY_HOLDS row for the *issuer*
        # company acting as a corporate holder elsewhere -- not touched by
        # this run's new source row, whose only corporate owner is
        # linked_company_id.
        sync_engine = GraphSyncEngine.build(session)
        sync_engine.ensure_relationship(
            rel_type_name="COMPANY_HOLDS",
            source_entity_id=fixture_world["issuer_company_id"],
            target_entity_id=fixture_world["security_entity_id"],
            source_system="ownership_filing",
        )
        session.commit()

        prime_calls: list[Optional[frozenset]] = []
        original_prime = GraphSyncEngine.prime_relationship_type

        def spy_prime(self, rel_type_name, **kwargs):
            if rel_type_name == "COMPANY_HOLDS":
                source_entity_ids = kwargs.get("source_entity_ids")
                prime_calls.append(
                    frozenset(source_entity_ids) if source_entity_ids is not None else None
                )
            return original_prime(self, rel_type_name, **kwargs)

        monkeypatch.setattr(GraphSyncEngine, "prime_relationship_type", spy_prime)

        pipe = MDMPipeline(session=session, silver=StubSilver({
            "FROM sec_ownership_non_derivative_txn": [
                {
                    "accession_number": "0000-new-company-holds",
                    "owner_index": 0,
                    "txn_index": 0,
                    "security_title": "Common Stock",
                    "transaction_date": None,
                    "shares_owned_after": 50,
                    "ownership_direct_indirect": "I",
                    "owner_cik": 910002,
                    "owner_name": "Linked Corp",
                    "issuer_cik": 910001,
                },
            ],
        }))
        summary = pipe.derive_relationships(relationship_types=["COMPANY_HOLDS"])

        assert summary["COMPANY_HOLDS"]["inserted"] == 1
        assert len(prime_calls) == 1
        assert prime_calls[0] is not None, "prime must be scoped, not an unscoped whole-type load"
        assert prime_calls[0] == frozenset({fixture_world["linked_company_id"]})
        assert fixture_world["issuer_company_id"] not in prime_calls[0]


class TestRelationshipTypesConcurrency:
    def test_concurrent_type_worker_sessions_create_no_duplicates_or_deadlocks(self):
        """The actual safety property derive_relationships()'s per-type
        worker concurrency depends on: each relationship type only ever
        writes rows scoped to its own rel_type_id (relationship_id is a
        deterministic hash of (rel_type_id, source, target), so two types
        can never collide on the same row), so concurrent worker sessions
        deriving *different* types never share mutable match state.
        Exercised directly against a real multi-connection engine (not the
        StaticPool test fixture, which derive_relationships() itself
        deliberately avoids concurrency against for SQLite -- see
        pipeline.py's dialect check) to prove worker sessions genuinely
        don't collide, mirroring
        test_concurrent_workers_create_no_duplicates_or_deadlocks in
        test_run_companies_concurrency.py for run_companies' identical
        per-row worker-session pattern.
        """
        db_path = Path(tempfile.mkstemp(suffix=".db")[1])
        engine = create_engine(f"sqlite:///{db_path}")

        @event.listens_for(engine, "connect")
        def _register_now(dbapi_conn, _record):
            dbapi_conn.create_function("NOW", 0, lambda: datetime.utcnow().isoformat())

        Base.metadata.create_all(engine)
        seed_session = Session(engine)
        rel_type_ids = _seed_registry(seed_session)

        n = 10
        adviser_fund_ids: list[tuple[str, str]] = []
        for index in range(n):
            adviser_id = _add_entity(seed_session, "adviser")
            fund_id = _add_entity(seed_session, "fund")
            seed_session.add(MdmAdviser(
                entity_id=adviser_id, cik=920000 + index,
                canonical_name=f"Concurrency Adviser {index}",
            ))
            seed_session.add(MdmFund(
                entity_id=fund_id, adviser_entity_id=adviser_id,
                canonical_name=f"Concurrency Fund {index}",
            ))
            adviser_fund_ids.append((adviser_id, fund_id))
        issuer_company_id = _add_entity(seed_session, "company")
        seed_session.add(MdmCompany(
            entity_id=issuer_company_id, cik=930000, canonical_name="Concurrency Issuer",
        ))
        security_id = _add_entity(seed_session, "security")
        seed_session.add(MdmSecurity(
            entity_id=security_id, issuer_entity_id=issuer_company_id,
            canonical_title="Concurrency Stock",
        ))
        seed_session.commit()
        seed_session.close()

        # Two independent relationship types, each with its own source data,
        # driven directly on separate worker sessions/threads -- the same
        # shape derive_relationships()'s _derive_one does internally, but
        # exercised directly (like test_run_companies_concurrency.py does
        # for run_companies) so this test isn't gated by the dialect check
        # that forces derive_relationships() itself to 1 worker for SQLite.
        def _derive_manages_fund_worker() -> None:
            worker_session = get_session(engine)
            try:
                worker_pipeline = MDMPipeline(
                    session=worker_session,
                    silver=StubSilver({}),
                )
                worker_sync_engine = GraphSyncEngine.build(worker_session)
                worker_pipeline._derive_relationship_type(
                    worker_sync_engine, "MANAGES_FUND", None
                )
                worker_session.commit()
            finally:
                worker_session.close()

        def _derive_issued_by_worker() -> None:
            worker_session = get_session(engine)
            try:
                worker_pipeline = MDMPipeline(
                    session=worker_session,
                    silver=StubSilver({}),
                )
                worker_sync_engine = GraphSyncEngine.build(worker_session)
                worker_pipeline._derive_relationship_type(
                    worker_sync_engine, "ISSUED_BY", None
                )
                worker_session.commit()
            finally:
                worker_session.close()

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(_derive_manages_fund_worker) for _ in range(1)
            ] + [
                executor.submit(_derive_issued_by_worker) for _ in range(1)
            ]
            for future in futures:
                future.result()

        verify_session = Session(engine)
        manages_fund_rows = list(verify_session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "MANAGES_FUND")
        ))
        issued_by_rows = list(verify_session.scalars(
            select(MdmRelationshipInstance)
            .join(MdmRelationshipType)
            .where(MdmRelationshipType.rel_type_name == "ISSUED_BY")
        ))
        assert len(manages_fund_rows) == n, "expected one MANAGES_FUND edge per adviser/fund pair"
        assert len(issued_by_rows) == 1, "expected one ISSUED_BY edge for the seeded security"
        # No duplicate/cross-type instance_id collisions.
        all_ids = [r.instance_id for r in manages_fund_rows + issued_by_rows]
        assert len(set(all_ids)) == len(all_ids)
        verify_session.close()
        engine.dispose()
        db_path.unlink(missing_ok=True)

    def test_derive_relationships_forces_single_worker_under_sqlite(self, session, fixture_world):
        """End-to-end sanity check that derive_relationships() itself (not
        the direct-drive test above) still produces correct combined
        results when its own dialect guard forces it through the same
        single-worker code path as before this fix -- i.e. the new
        ThreadPoolExecutor-based implementation is behaviorally identical
        to the old sequential loop for the test suite's StaticPool fixture.
        """
        summary = MDMPipeline(session=session, silver=StubSilver({})).derive_relationships(
            relationship_types=["MANAGES_FUND", "ISSUED_BY", "IS_ENTITY_OF"]
        )
        assert set(summary.keys()) == {"MANAGES_FUND", "ISSUED_BY", "IS_ENTITY_OF"}
        assert summary["IS_ENTITY_OF"]["inserted"] == 1  # fixture_world's one adviser/company pair
