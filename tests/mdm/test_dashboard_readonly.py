from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from edgar_warehouse.mdm.database import (
    MdmAdviser,
    MdmCompany,
    MdmEntity,
    MdmEntityTypeDefinition,
    MdmFund,
    MdmPerson,
    MdmRelationshipInstance,
    MdmRelationshipType,
    MdmSecurity,
)


MDM_UNAVAILABLE_COPY = (
    "MDM database unavailable. Check `MDM_DATABASE_URL`, confirm the database "
    "is reachable, and restart the dashboard."
)


def _seed_company(session, cik: int = 320193, name: str = "Apple Inc.") -> None:
    entity = MdmEntity(entity_type="company", resolution_method="test", confidence=1.0)
    session.add(entity)
    session.flush()
    session.add(MdmCompany(entity_id=entity.entity_id, cik=cik, canonical_name=name))
    session.flush()


def _seed_domain_entity(session, entity_type: str, name: str, *, cik: int | None = None) -> str:
    entity = MdmEntity(entity_type=entity_type, resolution_method="test", confidence=1.0)
    session.add(entity)
    session.flush()
    if entity_type == "company":
        session.add(
            MdmCompany(
                entity_id=entity.entity_id,
                cik=cik or 100000,
                canonical_name=name,
            )
        )
    elif entity_type == "adviser":
        session.add(
            MdmAdviser(
                entity_id=entity.entity_id,
                cik=cik,
                crd_number=f"CRD-{entity.entity_id[:8]}",
                canonical_name=name,
            )
        )
    elif entity_type == "person":
        session.add(MdmPerson(entity_id=entity.entity_id, canonical_name=name))
    elif entity_type == "security":
        session.add(MdmSecurity(entity_id=entity.entity_id, canonical_title=name))
    elif entity_type == "fund":
        session.add(MdmFund(entity_id=entity.entity_id, canonical_name=name))
    else:
        raise ValueError(f"unsupported test entity type: {entity_type}")
    session.flush()
    return str(entity.entity_id)


def _ensure_person_registry(session) -> None:
    exists = session.get(MdmEntityTypeDefinition, "person")
    if exists is None:
        session.add(
            MdmEntityTypeDefinition(
                entity_type="person",
                neo4j_label="Person",
                domain_table="mdm_person",
                api_path_prefix="/persons",
                primary_id_field="entity_id",
                display_name="Person",
                is_active=True,
            )
        )
        session.flush()


def _seed_relationship_type(
    session,
    name: str,
    source_type: str,
    target_type: str,
    *,
    active: bool = True,
) -> str:
    rel_type_id = str(uuid.uuid4())
    session.add(
        MdmRelationshipType(
            rel_type_id=rel_type_id,
            rel_type_name=name,
            source_node_type=source_type,
            target_node_type=target_type,
            direction="outbound",
            is_temporal=True,
            merge_strategy="extend_temporal",
            is_active=active,
        )
    )
    session.flush()
    return rel_type_id


def _seed_relationship_instance(
    session,
    rel_type_id: str,
    source_entity_id: str,
    target_entity_id: str,
    *,
    created_at: datetime,
    graph_synced_at: datetime | None = None,
    active: bool = True,
    properties: dict[str, object] | None = None,
) -> str:
    instance_id = str(uuid.uuid4())
    session.add(
        MdmRelationshipInstance(
            instance_id=instance_id,
            rel_type_id=rel_type_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            properties=properties or {"secret_note": "raw properties must stay hidden"},
            graph_synced_at=graph_synced_at,
            is_active=active,
            created_at=created_at,
        )
    )
    session.flush()
    return instance_id


def test_check_mdm_status_returns_structured_connected_status(db_session):
    from edgar_warehouse.mdm.dashboard_readonly import (
        MdmDashboardStatus,
        check_mdm_status,
    )

    status = check_mdm_status(session=db_session)

    assert isinstance(status, MdmDashboardStatus)
    assert status.connected is True
    assert status.message == "MDM database connected."
    assert status.env_var == "MDM_DATABASE_URL"
    assert status.details["entity_types"] >= 4


def test_run_mdm_smoke_query_returns_bounded_structured_rows(db_session):
    from edgar_warehouse.mdm.dashboard_readonly import MdmSmokeResult, run_mdm_smoke_query

    _seed_company(db_session, cik=320193, name="Apple Inc.")
    _seed_company(db_session, cik=789019, name="Microsoft Corp.")

    result = run_mdm_smoke_query(session=db_session, limit=1)

    assert isinstance(result, MdmSmokeResult)
    assert result.available is True
    assert result.limit == 1
    assert len(result.rows) == 1
    assert result.rows[0]["entity_type"] == "company"
    assert result.rows[0]["cik"] == 320193
    assert result.rows[0]["canonical_name"] == "Apple Inc."


def test_mdm_dashboard_metrics_include_all_required_domain_counts(db_session):
    from edgar_warehouse.mdm.dashboard_readonly import get_mdm_dashboard_metrics

    _ensure_person_registry(db_session)
    _seed_domain_entity(db_session, "company", "Apple Inc.", cik=320193)
    _seed_domain_entity(db_session, "adviser", "Example Adviser LLC", cik=100001)
    _seed_domain_entity(db_session, "person", "Jane Officer")
    _seed_domain_entity(db_session, "security", "Class A Common Stock")
    _seed_domain_entity(db_session, "fund", "Example Growth Fund")

    metrics = get_mdm_dashboard_metrics(session=db_session)
    payload = metrics.as_dict()

    assert payload["available"] is True
    assert set(payload["entity_counts"]) == {
        "company",
        "adviser",
        "person",
        "security",
        "fund",
    }
    assert payload["entity_counts"]["company"]["label"] == "Companies"
    assert payload["entity_counts"]["company"]["count"] == 1
    assert payload["entity_counts"]["adviser"]["count"] == 1
    assert payload["entity_counts"]["person"]["count"] == 1
    assert payload["entity_counts"]["security"]["count"] == 1
    assert payload["entity_counts"]["fund"]["count"] == 1
    assert payload["registry"]["neo4j_labels"] == [
        "Adviser",
        "Company",
        "Fund",
        "Person",
        "Security",
    ]
    assert {
        row["entity_type"]: row["neo4j_label"]
        for row in payload["registry"]["entity_type_details"]
    } == {
        "adviser": "Adviser",
        "company": "Company",
        "fund": "Fund",
        "person": "Person",
        "security": "Security",
    }
    assert payload["last_refreshed"]


def test_mdm_relationship_metrics_include_active_zero_rows_and_pending_counts(db_session):
    from edgar_warehouse.mdm.dashboard_readonly import get_mdm_dashboard_metrics

    _ensure_person_registry(db_session)
    adviser_id = _seed_domain_entity(db_session, "adviser", "Example Adviser LLC")
    fund_id = _seed_domain_entity(db_session, "fund", "Example Fund")
    person_id = _seed_domain_entity(db_session, "person", "Jane Owner")
    company_id = _seed_domain_entity(db_session, "company", "Example Issuer", cik=100002)
    owns_type_id = _seed_relationship_type(db_session, "OWNS_COMPANY", "person", "company")
    inactive_type_id = _seed_relationship_type(
        db_session,
        "INACTIVE_TYPE",
        "person",
        "company",
        active=False,
    )
    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    _seed_relationship_instance(
        db_session,
        owns_type_id,
        person_id,
        company_id,
        created_at=now,
        graph_synced_at=None,
    )
    _seed_relationship_instance(
        db_session,
        owns_type_id,
        person_id,
        company_id,
        created_at=now + timedelta(minutes=1),
        graph_synced_at=now + timedelta(minutes=2),
    )
    _seed_relationship_instance(
        db_session,
        inactive_type_id,
        person_id,
        company_id,
        created_at=now,
    )
    # Existing fixture relationship type with one active pending row.
    manages_type = (
        db_session.query(MdmRelationshipType)
        .filter(MdmRelationshipType.rel_type_name == "MANAGES_FUND")
        .one()
    )
    _seed_relationship_instance(
        db_session,
        manages_type.rel_type_id,
        adviser_id,
        fund_id,
        created_at=now - timedelta(minutes=5),
    )

    metrics = get_mdm_dashboard_metrics(session=db_session)
    relationship_counts = metrics.as_dict()["relationship_counts"]

    assert "ISSUED_BY" in relationship_counts
    assert relationship_counts["ISSUED_BY"]["active_count"] == 0
    assert relationship_counts["ISSUED_BY"]["pending_graph_sync_count"] == 0
    assert relationship_counts["ISSUED_BY"]["total_count"] == 0
    assert relationship_counts["MANAGES_FUND"]["active_count"] == 1
    assert relationship_counts["MANAGES_FUND"]["pending_graph_sync_count"] == 1
    assert relationship_counts["OWNS_COMPANY"]["active_count"] == 2
    assert relationship_counts["OWNS_COMPANY"]["pending_graph_sync_count"] == 1
    assert relationship_counts["OWNS_COMPANY"]["total_count"] == 2
    assert "INACTIVE_TYPE" not in relationship_counts


def test_pending_sync_samples_are_ordered_bounded_and_property_free(db_session):
    from edgar_warehouse.mdm.dashboard_readonly import get_mdm_dashboard_metrics

    _ensure_person_registry(db_session)
    adviser_id = _seed_domain_entity(db_session, "adviser", "Alpha Adviser")
    fund_id = _seed_domain_entity(db_session, "fund", "Alpha Fund")
    person_id = _seed_domain_entity(db_session, "person", "Jane Owner")
    company_id = _seed_domain_entity(db_session, "company", "Beta Issuer", cik=100003)
    owns_type_id = _seed_relationship_type(db_session, "OWNS_COMPANY", "person", "company")
    manages_type = (
        db_session.query(MdmRelationshipType)
        .filter(MdmRelationshipType.rel_type_name == "MANAGES_FUND")
        .one()
    )
    base = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
    _seed_relationship_instance(
        db_session,
        manages_type.rel_type_id,
        adviser_id,
        fund_id,
        created_at=base + timedelta(minutes=2),
    )
    _seed_relationship_instance(
        db_session,
        manages_type.rel_type_id,
        adviser_id,
        fund_id,
        created_at=base + timedelta(minutes=1),
    )
    _seed_relationship_instance(
        db_session,
        owns_type_id,
        person_id,
        company_id,
        created_at=base,
    )
    _seed_relationship_instance(
        db_session,
        owns_type_id,
        person_id,
        company_id,
        created_at=base + timedelta(minutes=3),
    )

    metrics = get_mdm_dashboard_metrics(
        session=db_session,
        per_type_sample_limit=1,
        global_sample_limit=2,
    )
    samples = metrics.as_dict()["pending_sync_samples"]

    assert [sample["relationship_type"] for sample in samples] == [
        "MANAGES_FUND",
        "OWNS_COMPANY",
    ]
    assert len(samples) == 2
    assert samples[0]["source_entity_name"] == "Alpha Adviser"
    assert samples[0]["target_entity_name"] == "Alpha Fund"
    assert samples[1]["source_entity_name"] == "Jane Owner"
    assert samples[1]["target_entity_name"] == "Beta Issuer"
    assert all("properties" not in sample for sample in samples)
    assert all("raw" not in repr(sample).lower() for sample in samples)


def test_active_relationship_diagnostic_inputs_are_ordered_bounded_and_keyed(db_session):
    from edgar_warehouse.mdm.dashboard_readonly import (
        get_active_relationship_diagnostic_inputs,
    )

    _ensure_person_registry(db_session)
    adviser_id = _seed_domain_entity(db_session, "adviser", "Alpha Adviser")
    fund_id = _seed_domain_entity(db_session, "fund", "Alpha Fund")
    person_id = _seed_domain_entity(db_session, "person", "Jane Owner")
    company_id = _seed_domain_entity(db_session, "company", "Beta Issuer", cik=100004)
    owns_type_id = _seed_relationship_type(db_session, "OWNS_COMPANY", "person", "company")
    manages_type = (
        db_session.query(MdmRelationshipType)
        .filter(MdmRelationshipType.rel_type_name == "MANAGES_FUND")
        .one()
    )
    base = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)
    _seed_relationship_instance(
        db_session,
        manages_type.rel_type_id,
        adviser_id,
        fund_id,
        created_at=base + timedelta(minutes=2),
    )
    _seed_relationship_instance(
        db_session,
        manages_type.rel_type_id,
        adviser_id,
        fund_id,
        created_at=base + timedelta(minutes=3),
    )
    _seed_relationship_instance(
        db_session,
        owns_type_id,
        person_id,
        company_id,
        created_at=base,
    )
    _seed_relationship_instance(
        db_session,
        owns_type_id,
        person_id,
        company_id,
        created_at=base + timedelta(minutes=1),
        active=False,
    )

    result = get_active_relationship_diagnostic_inputs(
        session=db_session,
        per_type_sample_limit=1,
        global_sample_limit=2,
    )
    payload = result.as_dict()

    assert [row["relationship_type"] for row in payload["candidate_rows"]] == [
        "MANAGES_FUND",
        "OWNS_COMPANY",
    ]
    assert len(payload["candidate_rows"]) == 2
    first_row = payload["candidate_rows"][0]
    assert set(first_row) == {
        "relationship_type",
        "source_entity_id",
        "source_entity_name",
        "target_entity_id",
        "target_entity_name",
        "created_at",
        "mdm_edge_key",
    }
    assert first_row["mdm_edge_key"] == (
        "MANAGES_FUND",
        adviser_id,
        fund_id,
    )
    assert payload["known_mdm_edge_keys"]["MANAGES_FUND"] == [
        ("MANAGES_FUND", adviser_id, fund_id)
    ]
    assert payload["known_mdm_edge_keys"]["OWNS_COMPANY"] == [
        ("OWNS_COMPANY", person_id, company_id)
    ]
    assert payload["active_relationship_counts"]["MANAGES_FUND"] == 2
    assert payload["active_relationship_counts"]["OWNS_COMPANY"] == 1
    assert payload["active_relationship_counts"]["ISSUED_BY"] == 0
    assert all("properties" not in row for row in payload["candidate_rows"])


def test_build_relationship_coverage_rows_clamps_missing_and_coverage_percent():
    from edgar_warehouse.mdm.dashboard_readonly import build_relationship_coverage_rows

    mdm_relationships = {
        "MANAGES_FUND": {"active_count": 4, "pending_graph_sync_count": 1},
        "ISSUED_BY": {"active_count": 0, "pending_graph_sync_count": 0},
        "OWNS_COMPANY": {"active_count": 2, "pending_graph_sync_count": 0},
    }
    neo4j_relationships = {
        "MANAGES_FUND": {"edge_count": 3},
        "OWNS_COMPANY": {"edge_count": 5},
    }

    rows = build_relationship_coverage_rows(mdm_relationships, neo4j_relationships)
    payload = [row.as_dict() for row in rows]

    assert payload == [
        {
            "relationship_type": "ISSUED_BY",
            "mdm_active_count": 0,
            "neo4j_edge_count": 0,
            "pending_graph_sync_count": 0,
            "missing_estimate": 0,
            "coverage_percent": None,
            "extra_graph_count": 0,
            "status": "No active MDM rows",
        },
        {
            "relationship_type": "MANAGES_FUND",
            "mdm_active_count": 4,
            "neo4j_edge_count": 3,
            "pending_graph_sync_count": 1,
            "missing_estimate": 1,
            "coverage_percent": 75.0,
            "extra_graph_count": 0,
            "status": "Missing graph data",
        },
        {
            "relationship_type": "OWNS_COMPANY",
            "mdm_active_count": 2,
            "neo4j_edge_count": 5,
            "pending_graph_sync_count": 0,
            "missing_estimate": 0,
            "coverage_percent": 100.0,
            "extra_graph_count": 3,
            "status": "Extra graph data",
        },
    ]


def test_mdm_dashboard_metrics_warning_payloads_are_actionable_and_secret_safe(monkeypatch):
    from edgar_warehouse.mdm.dashboard_readonly import get_mdm_dashboard_metrics

    secret_dsn = "postgresql://dashboard_user:super-secret@example.internal/mdm"

    def fail_engine():
        raise RuntimeError(f"could not connect to {secret_dsn}")

    monkeypatch.setenv("MDM_DATABASE_URL", secret_dsn)
    monkeypatch.setattr("edgar_warehouse.mdm.dashboard_readonly.get_engine", fail_engine)

    metrics = get_mdm_dashboard_metrics()
    payload = metrics.as_dict()
    rendered = repr(payload)

    assert payload["available"] is False
    assert payload["message"] == MDM_UNAVAILABLE_COPY
    assert payload["error_env_var"] == "MDM_DATABASE_URL"
    assert payload["warnings"]
    assert {warning["severity"] for warning in payload["warnings"]} <= {
        "error",
        "warning",
        "info",
    }
    assert all(warning["action"] for warning in payload["warnings"])
    assert "super-secret" not in rendered
    assert "dashboard_user" not in rendered
    assert "example.internal" not in rendered
    assert "could not connect" not in rendered


def test_helpers_never_commit(db_session, monkeypatch):
    from edgar_warehouse.mdm import dashboard_readonly

    def fail_commit():
        raise AssertionError("dashboard read-only helpers must not commit")

    monkeypatch.setattr(db_session, "commit", fail_commit)

    dashboard_readonly.check_mdm_status(session=db_session)
    dashboard_readonly.run_mdm_smoke_query(session=db_session, limit=5)
    dashboard_readonly.get_mdm_dashboard_metrics(session=db_session)
    dashboard_readonly.get_active_relationship_diagnostic_inputs(session=db_session)


def test_missing_mdm_configuration_uses_safe_status_copy(monkeypatch):
    from edgar_warehouse.mdm.dashboard_readonly import (
        MdmDashboardStatus,
        check_mdm_status,
    )

    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)

    status = check_mdm_status()

    assert isinstance(status, MdmDashboardStatus)
    assert status.connected is False
    assert status.message == MDM_UNAVAILABLE_COPY
    assert status.env_var == "MDM_DATABASE_URL"
    assert "MDM_DATABASE_URL" in status.as_dict()["message"]


def test_failed_mdm_connection_does_not_leak_dsn_or_raw_exception(monkeypatch):
    from edgar_warehouse.mdm.dashboard_readonly import check_mdm_status

    secret_dsn = "postgresql://dashboard_user:super-secret@example.internal/mdm"

    def fail_engine():
        raise RuntimeError(f"could not connect to {secret_dsn}")

    monkeypatch.setenv("MDM_DATABASE_URL", secret_dsn)
    monkeypatch.setattr("edgar_warehouse.mdm.dashboard_readonly.get_engine", fail_engine)

    status = check_mdm_status()
    payload = status.as_dict()
    rendered = repr(payload)

    assert payload["connected"] is False
    assert payload["message"] == MDM_UNAVAILABLE_COPY
    assert "MDM_DATABASE_URL" in rendered
    assert "super-secret" not in rendered
    assert "dashboard_user" not in rendered
    assert "example.internal" not in rendered
    assert "could not connect" not in rendered


def test_run_mdm_smoke_query_returns_safe_unavailable_result(monkeypatch):
    from edgar_warehouse.mdm.dashboard_readonly import MdmSmokeResult, run_mdm_smoke_query

    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)

    result = run_mdm_smoke_query()

    assert isinstance(result, MdmSmokeResult)
    assert result.available is False
    assert result.message == MDM_UNAVAILABLE_COPY
    assert result.rows == []
    assert result.error_env_var == "MDM_DATABASE_URL"


def test_dashboard_readonly_module_avoids_mutation_surfaces():
    module_text = Path("edgar_warehouse/mdm/dashboard_readonly.py").read_text()

    blocked_tokens = [
        "MDMPipeline",
        "migrations.runtime",
        "ResolverContext",
        "CompanyResolver",
        "AdviserResolver",
        "FundResolver",
        "PersonResolver",
        "SecurityResolver",
        "stewardship",
        "GraphSyncEngine",
        "sync_pending",
        "sync_entities",
        "_handle_run",
        "_handle_migrate",
        "_handle_sync_graph",
        "_handle_derive_relationships",
        "_handle_load_relationships",
        "commit(",
        ".commit",
    ]
    for token in blocked_tokens:
        assert token not in module_text


def test_helpers_return_plain_structures_without_stdout_parsing(db_session, capsys):
    from edgar_warehouse.mdm.dashboard_readonly import (
        check_mdm_status,
        run_mdm_smoke_query,
    )

    status = check_mdm_status(session=db_session)
    smoke = run_mdm_smoke_query(session=db_session)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert isinstance(status.as_dict(), dict)
    assert isinstance(smoke.as_dict(), dict)
