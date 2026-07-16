"""Tests for Phase 7 Plan 02: exhaustive relationship coverage/exclusion policy
(EDGE-07, EDGE-08, RCOV-01, RCOV-02).

Uses an in-memory SQLite store (schema via Base.metadata.create_all), matching
the existing MDM test convention. A tiny StubSilver stands in for the real
DuckDB silver reader, mirroring tests/mdm/test_pipeline_relationships.py's
StubSilver pattern.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.mdm import coverage
from edgar_warehouse.mdm.database import (
    Base,
    MdmEntity,
    MdmEntityTypeDefinition,
    MdmRelationshipType,
)


class StubSilver:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def fetch(self, sql: str, params: Optional[list[Any]] = None) -> list[dict]:
        return list(self._rows)


ALL_11_RELATIONSHIP_TYPES = [
    ("IS_INSIDER", "person", "company"),
    ("HOLDS", "person", "security"),
    ("COMPANY_HOLDS", "company", "security"),
    ("ISSUED_BY", "security", "company"),
    ("IS_ENTITY_OF", "adviser", "company"),
    ("HAS_PARENT_COMPANY", "company", "company"),
    ("MANAGES_FUND", "adviser", "fund"),
    ("IS_PERSON_OF", "adviser", "person"),
    ("EMPLOYED_BY", "person", "company"),
    ("AUDITED_BY", "company", "audit_firm"),
    ("INSTITUTIONAL_HOLDS", "adviser", "security"),
]


def _seed_all_relationship_types(session: Session) -> dict[str, str]:
    for et in ("person", "company", "security", "fund", "adviser", "audit_firm"):
        session.add(MdmEntityTypeDefinition(
            entity_type=et, neo4j_label=et.title(), domain_table=f"mdm_{et}",
            api_path_prefix=f"/{et}s", primary_id_field="entity_id",
            display_name=et.title(), is_active=True,
        ))
    rel_types = {}
    for name, src, tgt in ALL_11_RELATIONSHIP_TYPES:
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
    rel_types = _seed_all_relationship_types(session)
    return {"rel_types": rel_types, "session": session}


# ---------------------------------------------------------------------------
# Task 1: fingerprint determinism + EDGE-07/EDGE-08 exclusion classification
# ---------------------------------------------------------------------------

class TestPopulatedTypesConsistency:
    def test_matches_snowflake_graph_populated_relationship_types(self):
        from edgar_warehouse.mdm.snowflake_graph import (
            POPULATED_RELATIONSHIP_TYPES as SNOWFLAKE_GRAPH_POPULATED,
        )
        assert set(coverage.POPULATED_RELATIONSHIP_TYPES) == set(SNOWFLAKE_GRAPH_POPULATED)


class TestFingerprint:
    def test_fingerprint_is_stable_for_same_sorted_input(self):
        a = coverage._fingerprint(["b", "a"], ["1"])
        b = coverage._fingerprint(["a", "b"], ["1"])
        assert a == b

    def test_fingerprint_changes_when_population_changes(self):
        a = coverage._fingerprint(["105958"])
        b = coverage._fingerprint(["105958", "749044"])
        assert a != b

    def test_fingerprint_is_deterministic_across_calls(self):
        first = coverage._fingerprint(["x", "y"], ["z"])
        second = coverage._fingerprint(["x", "y"], ["z"])
        assert first == second


class TestEdge07ManagesFundCoverage:
    def test_supported_empty_source_is_valid_zero(self, world, session):
        record = coverage.compute_edge07_manages_fund_coverage(StubSilver([]), session)
        assert record["status"] == "valid_zero"
        assert record["evidence_category"] == "supported_source_population"
        assert record["expected_edge_count"] == 0

    def test_source_rows_without_mdm_edges_fail_closed(self, world, session):
        silver = StubSilver([{
            "adviser_crd_number": "129052", "private_fund_id": "805-1", "filing_id": "1"
        }])
        with pytest.raises(RuntimeError, match="zero active MDM edges"):
            coverage.compute_edge07_manages_fund_coverage(silver, session)


class TestEdge08HasParentCompanyCoverage:
    def test_supported_empty_source_is_valid_zero(self, world, session):
        record = coverage.compute_edge08_has_parent_company_coverage(StubSilver([]), session)
        assert record["status"] == "valid_zero"
        assert record["evidence_category"] == "supported_source_population"
        assert record["expected_edge_count"] == 0


class TestNoExclusionWritesGraphData:
    def test_exclusion_functions_write_no_relationship_instance_rows(self, world, session):
        from edgar_warehouse.mdm.database import MdmRelationshipInstance

        silver = StubSilver([])
        coverage.compute_edge05_is_entity_of_coverage(session)
        coverage.compute_edge06_is_person_of_coverage(session)
        coverage.compute_edge07_manages_fund_coverage(silver, session)
        coverage.compute_edge08_has_parent_company_coverage(silver, session)
        coverage.compute_edge10_audited_by_coverage(silver, session)
        coverage.compute_deferred_fix_coverage("EMPLOYED_BY", evidence_query_version="v1")
        session.flush()
        count = session.scalar(select(MdmRelationshipInstance).limit(1))
        assert count is None


# ---------------------------------------------------------------------------
# Task 2: exhaustive manifest + fail-closed verification
# ---------------------------------------------------------------------------

class TestExhaustiveManifest:
    def test_all_11_active_types_appear_exactly_once(self, world, session):
        silver = StubSilver([])
        manifest = coverage.compute_relationship_coverage_manifest(silver, session, "gen-1")
        names = [r["rel_type_name"] for r in manifest]
        assert sorted(names) == sorted(name for name, _, _ in ALL_11_RELATIONSHIP_TYPES)
        assert len(names) == len(set(names))

    def test_populated_types_get_populated_status(self, world, session):
        silver = StubSilver([])
        manifest = coverage.compute_relationship_coverage_manifest(
            silver, session, "gen-1",
            relationship_active_counts={"IS_INSIDER": 42, "HOLDS": 10, "COMPANY_HOLDS": 5, "ISSUED_BY": 3},
        )
        by_name = {r["rel_type_name"]: r for r in manifest}
        assert by_name["IS_INSIDER"]["status"] == "populated"
        assert by_name["IS_INSIDER"]["expected_edge_count"] == 42

    def test_edge09_edge11_are_valid_zero_not_excluded(self, world, session):
        silver = StubSilver([])
        manifest = coverage.compute_relationship_coverage_manifest(silver, session, "gen-1")
        by_name = {r["rel_type_name"]: r for r in manifest}
        assert by_name["EMPLOYED_BY"]["status"] == "valid_zero"
        assert by_name["INSTITUTIONAL_HOLDS"]["status"] == "valid_zero"

    def test_unclassified_active_type_raises(self, world, session):
        session.add(MdmRelationshipType(
            rel_type_id=str(uuid.uuid4()), rel_type_name="SOME_NEW_TYPE",
            source_node_type="company", target_node_type="company",
            direction="outbound", is_temporal=True,
            merge_strategy="extend_temporal", is_active=True,
        ))
        session.commit()
        silver = StubSilver([])
        with pytest.raises(KeyError):
            coverage.compute_relationship_coverage_manifest(silver, session, "gen-1")


class TestVerifyCoverageManifest:
    def _manifest(self, world, session):
        silver = StubSilver([])
        return coverage.compute_relationship_coverage_manifest(
            silver, session, "gen-1",
            relationship_active_counts={"IS_INSIDER": 1, "HOLDS": 1, "COMPANY_HOLDS": 1, "ISSUED_BY": 1},
        )

    def test_complete_manifest_passes(self, world, session):
        manifest = self._manifest(world, session)
        active_names = [name for name, _, _ in ALL_11_RELATIONSHIP_TYPES]
        violations = coverage.verify_relationship_coverage_manifest(manifest, active_names)
        assert violations == []

    def test_omitted_relationship_type_fails(self, world, session):
        manifest = self._manifest(world, session)
        active_names = [name for name, _, _ in ALL_11_RELATIONSHIP_TYPES] + ["SOME_UNCOVERED_TYPE"]
        violations = coverage.verify_relationship_coverage_manifest(manifest, active_names)
        assert any("SOME_UNCOVERED_TYPE" in v for v in violations)

    def test_stale_exclusion_fingerprint_fails(self, world, session):
        manifest = self._manifest(world, session)
        active_names = [name for name, _, _ in ALL_11_RELATIONSHIP_TYPES]
        violations = coverage.verify_relationship_coverage_manifest(
            manifest, active_names,
            stale_fingerprints={"MANAGES_FUND": "a-freshly-recomputed-different-hash"},
        )
        assert any("MANAGES_FUND" in v and "stale" in v for v in violations)

    def test_nonzero_excluded_type_fails(self, world, session):
        manifest = self._manifest(world, session)
        active_names = [name for name, _, _ in ALL_11_RELATIONSHIP_TYPES]
        violations = coverage.verify_relationship_coverage_manifest(
            manifest, active_names,
            live_active_counts={"MANAGES_FUND": 3},
        )
        assert any("MANAGES_FUND" in v for v in violations)

    def test_zero_populated_type_fails(self, world, session):
        silver = StubSilver([])
        manifest = coverage.compute_relationship_coverage_manifest(
            silver, session, "gen-1",
            relationship_active_counts={"IS_INSIDER": 0, "HOLDS": 1, "COMPANY_HOLDS": 1, "ISSUED_BY": 1},
        )
        # Force the contradiction directly: a populated-status record with zero edges.
        for record in manifest:
            if record["rel_type_name"] == "IS_INSIDER":
                record["expected_edge_count"] = 0
        active_names = [name for name, _, _ in ALL_11_RELATIONSHIP_TYPES]
        violations = coverage.verify_relationship_coverage_manifest(manifest, active_names)
        assert any("IS_INSIDER" in v for v in violations)

    def test_contradictory_duplicate_statuses_fail(self, world, session):
        manifest = self._manifest(world, session)
        duplicate = dict(manifest[0])
        duplicate["status"] = "excluded" if duplicate["status"] != "excluded" else "populated"
        manifest.append(duplicate)
        active_names = [name for name, _, _ in ALL_11_RELATIONSHIP_TYPES]
        violations = coverage.verify_relationship_coverage_manifest(manifest, active_names)
        assert any("contradictory" in v for v in violations)

    def test_valid_zero_recomputed_fingerprint_detects_staleness(self, world, session):
        """A valid_zero record (EDGE-09/11) cannot be reused for a later generation
        without recomputation: if the gate's form set changes, a freshly
        recomputed fingerprint must differ from the stored one and fail closed."""
        manifest = self._manifest(world, session)
        by_name = {r["rel_type_name"]: r for r in manifest}
        stored = by_name["EMPLOYED_BY"]["population_fingerprint"]

        # Simulate a later generation where the underlying gate widened (a
        # different, freshly recomputed fingerprint is now the truth).
        fresh_fingerprint = coverage._fingerprint(["3", "3/A", "4", "4/A", "5", "5/A", "DEF 14A"])
        assert fresh_fingerprint != stored

        active_names = [name for name, _, _ in ALL_11_RELATIONSHIP_TYPES]
        violations = coverage.verify_relationship_coverage_manifest(
            manifest, active_names,
            stale_fingerprints={"EMPLOYED_BY": fresh_fingerprint},
        )
        assert any("EMPLOYED_BY" in v and "stale" in v for v in violations)


# ---------------------------------------------------------------------------
# snowflake_graph.py integration: exhaustive named-check mode
# ---------------------------------------------------------------------------

class TestNamedRelationshipParityChecksExhaustiveMode:
    """_named_relationship_parity_checks accepts an optional coverage map
    (07-02) that replaces POPULATED_RELATIONSHIP_TYPES-only scoping with
    exhaustive evaluation. Default (no coverage arg) behavior is unchanged --
    covered already by tests/mdm/test_cli_snowflake_graph.py."""

    def _relationship_parity(self, rows: list[dict]) -> dict:
        return {"by_relationship_type": rows}

    def test_default_unchanged_scopes_to_populated_only(self):
        from edgar_warehouse.mdm.snowflake_graph import _named_relationship_parity_checks

        parity = self._relationship_parity([
            {"relationship_type": "HOLDS", "mdm_active_count": 1,
             "snowflake_graph_edge_count": 1, "mdm_minus_graph": 0, "graph_minus_mdm": 0},
            {"relationship_type": "MANAGES_FUND", "mdm_active_count": 0,
             "snowflake_graph_edge_count": 0, "mdm_minus_graph": 0, "graph_minus_mdm": 0},
        ])
        checks = _named_relationship_parity_checks(parity)
        names = {c["relationship_type"] for c in checks}
        assert "MANAGES_FUND" not in names
        assert "HOLDS" in names

    def test_exhaustive_mode_checks_excluded_type_is_zero(self):
        from edgar_warehouse.mdm.snowflake_graph import _named_relationship_parity_checks

        parity = self._relationship_parity([
            {"relationship_type": "MANAGES_FUND", "mdm_active_count": 0,
             "snowflake_graph_edge_count": 0, "mdm_minus_graph": 0, "graph_minus_mdm": 0},
        ])
        checks = _named_relationship_parity_checks(
            parity, {"MANAGES_FUND": "excluded"}
        )
        assert len(checks) == 1
        assert checks[0]["status"] == "ok"
        assert checks[0]["coverage_status"] == "excluded"

    def test_exhaustive_mode_fails_on_nonzero_excluded_type(self):
        """Synthetic/unexpected data for an excluded type is now a hard failure,
        not silence -- this is the key behavior change from 07-02."""
        from edgar_warehouse.mdm.snowflake_graph import _named_relationship_parity_checks

        parity = self._relationship_parity([
            {"relationship_type": "MANAGES_FUND", "mdm_active_count": 3,
             "snowflake_graph_edge_count": 3, "mdm_minus_graph": 0, "graph_minus_mdm": 0},
        ])
        checks = _named_relationship_parity_checks(
            parity, {"MANAGES_FUND": "excluded"}
        )
        assert checks[0]["status"] == "failed"
        assert "remediation" in checks[0]

    def test_exhaustive_mode_fails_on_nonzero_valid_zero_type(self):
        from edgar_warehouse.mdm.snowflake_graph import _named_relationship_parity_checks

        parity = self._relationship_parity([
            {"relationship_type": "EMPLOYED_BY", "mdm_active_count": 5,
             "snowflake_graph_edge_count": 0, "mdm_minus_graph": 5, "graph_minus_mdm": 0},
        ])
        checks = _named_relationship_parity_checks(
            parity, {"EMPLOYED_BY": "valid_zero"}
        )
        assert checks[0]["status"] == "failed"

    def test_exhaustive_mode_still_requires_populated_types_at_parity(self):
        from edgar_warehouse.mdm.snowflake_graph import _named_relationship_parity_checks

        parity = self._relationship_parity([
            {"relationship_type": "HOLDS", "mdm_active_count": 2,
             "snowflake_graph_edge_count": 1, "mdm_minus_graph": 1, "graph_minus_mdm": 0},
        ])
        checks = _named_relationship_parity_checks(
            parity, {"HOLDS": "populated"}
        )
        assert checks[0]["status"] == "failed"

    def test_exhaustive_mode_covers_all_11_types_when_given_full_manifest(self, world, session):
        from edgar_warehouse.mdm.snowflake_graph import _named_relationship_parity_checks

        silver = StubSilver([])
        manifest = coverage.compute_relationship_coverage_manifest(
            silver, session, "gen-1",
            relationship_active_counts={"IS_INSIDER": 1, "HOLDS": 1, "COMPANY_HOLDS": 1, "ISSUED_BY": 1},
        )
        coverage_map = {r["rel_type_name"]: r["status"] for r in manifest}
        parity = self._relationship_parity([
            {"relationship_type": name, "mdm_active_count": 0,
             "snowflake_graph_edge_count": 0, "mdm_minus_graph": 0, "graph_minus_mdm": 0}
            for name, _, _ in ALL_11_RELATIONSHIP_TYPES
        ])
        checks = _named_relationship_parity_checks(parity, coverage_map)
        assert len(checks) == 11
        assert {c["relationship_type"] for c in checks} == {
            name for name, _, _ in ALL_11_RELATIONSHIP_TYPES
        }
