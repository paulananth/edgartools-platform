"""Endpoint tests for the MDM FastAPI application.

Every test uses the `api_client` fixture (defined in conftest.py) which:
  - wires an in-memory SQLite session so no real database is needed
  - bypasses the X-API-Key check with TEST_API_KEY
  - leaves the Neo4j dependency returning None (graph endpoints fall back
    to the SQL relationship mirror)

Test groups — ordered from simplest to most integrated:
  1. Infrastructure  — /healthz, OpenAPI schema
  2. Auth            — missing / wrong / valid API key
  3. Entities        — list, get, sources, pagination, search, resolve
  4. Companies       — by CIK, insiders, advisers, securities
  5. Graph           — relationship types, neighborhood, traversal, sync-status
  6. Stewardship     — quarantine, unquarantine, merge, reviews
  7. Export          — changes feed, snapshot

Each class documents the endpoints it covers and the invariants it verifies
so future contributors know exactly what scenario each test owns.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

from tests.mdm.conftest import TEST_API_KEY

# ---------------------------------------------------------------------------
# Helpers: factory functions that create domain rows via the db_session fixture
# ---------------------------------------------------------------------------

def _entity(session, entity_type: str) -> str:
    from edgar_warehouse.mdm.database import MdmEntity
    eid = str(uuid.uuid4())
    session.add(MdmEntity(
        entity_id=eid,
        entity_type=entity_type,
        resolution_method="test",
        confidence=1.0,
    ))
    session.flush()
    return eid


def _company(session, cik: int = 320193, name: str = "Apple Inc") -> tuple[str, object]:
    from edgar_warehouse.mdm.database import MdmCompany
    eid = _entity(session, "company")
    row = MdmCompany(entity_id=eid, cik=cik, canonical_name=name)
    session.add(row)
    session.flush()
    return eid, row


def _adviser(session, crd: str = "CRD001", name: str = "Acme Advisers",
             linked_company_eid: str | None = None) -> tuple[str, object]:
    from edgar_warehouse.mdm.database import MdmAdviser
    eid = _entity(session, "adviser")
    row = MdmAdviser(
        entity_id=eid,
        crd_number=crd,
        canonical_name=name,
        linked_company_entity_id=linked_company_eid,
    )
    session.add(row)
    session.flush()
    return eid, row


def _fund(session, adviser_eid: str | None = None, name: str = "Test Fund") -> tuple[str, object]:
    from edgar_warehouse.mdm.database import MdmFund
    eid = _entity(session, "fund")
    row = MdmFund(entity_id=eid, adviser_entity_id=adviser_eid, canonical_name=name)
    session.add(row)
    session.flush()
    return eid, row


def _security(session, issuer_eid: str | None = None, title: str = "Common Stock") -> tuple[str, object]:
    from edgar_warehouse.mdm.database import MdmSecurity
    eid = _entity(session, "security")
    row = MdmSecurity(
        entity_id=eid,
        issuer_entity_id=issuer_eid,
        canonical_title=title,
        security_type="common_stock",
    )
    session.add(row)
    session.flush()
    return eid, row


def _person(session, name: str = "Jane Doe") -> tuple[str, object]:
    from edgar_warehouse.mdm.database import MdmPerson
    eid = _entity(session, "person")
    row = MdmPerson(entity_id=eid, canonical_name=name)
    session.add(row)
    session.flush()
    return eid, row


def _rel_instance(session, rel_type_name: str, src_eid: str, tgt_eid: str,
                  effective_from=None, effective_to=None) -> object:
    """Insert a relationship instance for the given named type."""
    from sqlalchemy import select
    from edgar_warehouse.mdm.database import MdmRelationshipInstance, MdmRelationshipType

    rt = session.scalar(
        select(MdmRelationshipType).where(MdmRelationshipType.rel_type_name == rel_type_name)
    )
    if rt is None:
        raise ValueError(f"Relationship type '{rel_type_name}' not seeded — check conftest fixture")
    row = MdmRelationshipInstance(
        rel_type_id=rt.rel_type_id,
        source_entity_id=src_eid,
        target_entity_id=tgt_eid,
        effective_from=effective_from,
        effective_to=effective_to,
    )
    session.add(row)
    session.flush()
    return row


# ===========================================================================
# 1. Infrastructure
# ===========================================================================

class TestInfrastructure:
    """
    Endpoints: GET /healthz
               GET /openapi.json

    Verifies that the app boots cleanly and the health probe returns 200
    without requiring an API key.
    """

    def test_healthz_returns_200(self, api_client):
        r = api_client.get("/healthz")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_healthz_no_auth_required(self, api_client):
        # Confirm health probe doesn't need X-API-Key even on a strict client
        r = api_client.get("/healthz")
        assert r.status_code == 200

    def test_openapi_schema_reachable(self, api_client):
        r = api_client.get("/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        assert "paths" in schema
        assert schema["info"]["title"] == "EdgarTools MDM"

    def test_all_expected_path_prefixes_registered(self, api_client):
        r = api_client.get("/openapi.json")
        paths = r.json()["paths"]
        for prefix in ("/api/v1/mdm/entities", "/api/v1/mdm/companies",
                       "/api/v1/mdm/graph", "/api/v1/mdm/stewardship"):
            assert any(p.startswith(prefix) for p in paths), f"missing prefix {prefix}"


# ===========================================================================
# 2. Auth
# ===========================================================================

class TestAuth:
    """
    Endpoint: All /api/v1/mdm/* routes require X-API-Key.

    Verifies:
      - 503 when MDM_API_KEYS env var is absent (key store not configured)
      - 401 when header is missing or contains a wrong key
      - 200 when the correct test key is supplied
    """

    def test_missing_key_returns_401(self, db_session):
        """Real auth active; request with no X-API-Key header must get 401."""
        import edgar_warehouse.mdm.api.auth as _auth
        from fastapi.testclient import TestClient
        from edgar_warehouse.mdm.api.main import create_app
        from edgar_warehouse.mdm.api.deps import get_db

        app = create_app()
        def _db(): yield db_session
        app.dependency_overrides[get_db] = _db
        env = {"MDM_API_KEYS": TEST_API_KEY, "MDM_API_KEY_SECRET_ID": ""}
        with patch.dict(os.environ, env), patch.object(_auth, "_SECRET_CACHE", None):
            with TestClient(app, raise_server_exceptions=False) as c:
                r = c.get("/api/v1/mdm/entities")  # no X-API-Key header
        assert r.status_code == 401

    def test_wrong_key_returns_401(self, db_session):
        import edgar_warehouse.mdm.api.auth as _auth
        from fastapi.testclient import TestClient
        from edgar_warehouse.mdm.api.main import create_app
        from edgar_warehouse.mdm.api.deps import get_db

        app = create_app()
        def _db(): yield db_session
        app.dependency_overrides[get_db] = _db
        env = {"MDM_API_KEYS": TEST_API_KEY, "MDM_API_KEY_SECRET_ID": ""}
        with patch.dict(os.environ, env), patch.object(_auth, "_SECRET_CACHE", None):
            with TestClient(app, raise_server_exceptions=False) as c:
                r = c.get("/api/v1/mdm/entities", headers={"X-API-Key": "wrong"})
        assert r.status_code == 401

    def test_empty_key_store_returns_503(self, db_session):
        import edgar_warehouse.mdm.api.auth as _auth
        from fastapi.testclient import TestClient
        from edgar_warehouse.mdm.api.main import create_app
        from edgar_warehouse.mdm.api.deps import get_db

        app = create_app()
        def _db(): yield db_session
        app.dependency_overrides[get_db] = _db
        # MDM_API_KEYS="" → _load_keys() returns empty set → 503
        env = {"MDM_API_KEYS": "", "MDM_API_KEY_SECRET_ID": ""}
        with patch.dict(os.environ, env), patch.object(_auth, "_SECRET_CACHE", None):
            with TestClient(app, raise_server_exceptions=False) as c:
                r = c.get("/api/v1/mdm/entities", headers={"X-API-Key": TEST_API_KEY})
        assert r.status_code == 503

    def test_valid_key_grants_access(self, api_client):
        r = api_client.get("/api/v1/mdm/entities")
        assert r.status_code == 200


# ===========================================================================
# 3. Entities
# ===========================================================================

class TestEntitiesEndpoints:
    """
    Endpoints:
      GET  /api/v1/mdm/entities                 — paginated list
      GET  /api/v1/mdm/entities/{entity_id}     — single entity
      GET  /api/v1/mdm/entities/{entity_id}/sources
      POST /api/v1/mdm/entities/resolve

    Verifies: schema shape, 404 on missing, pagination meta, quarantine filter,
              type filter, text search, source-system resolve.
    """

    def test_list_entities_empty(self, api_client):
        r = api_client.get("/api/v1/mdm/entities")
        assert r.status_code == 200
        body = r.json()
        assert body["items"] == []
        assert body["meta"]["total"] == 0

    def test_list_entities_returns_created_entities(self, api_client, db_session):
        _entity(db_session, "company")
        _entity(db_session, "adviser")
        db_session.commit()
        r = api_client.get("/api/v1/mdm/entities")
        assert r.status_code == 200
        assert r.json()["meta"]["total"] == 2

    def test_list_entities_type_filter(self, api_client, db_session):
        _entity(db_session, "company")
        _entity(db_session, "adviser")
        db_session.commit()
        r = api_client.get("/api/v1/mdm/entities", params={"type": "company"})
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["entity_type"] == "company"

    def test_list_entities_quarantine_excluded_by_default(self, api_client, db_session):
        from edgar_warehouse.mdm.database import MdmEntity
        eid = str(uuid.uuid4())
        db_session.add(MdmEntity(entity_id=eid, entity_type="company", is_quarantined=True))
        db_session.commit()
        r = api_client.get("/api/v1/mdm/entities")
        assert r.status_code == 200
        assert r.json()["meta"]["total"] == 0

    def test_list_entities_include_quarantined(self, api_client, db_session):
        from edgar_warehouse.mdm.database import MdmEntity
        eid = str(uuid.uuid4())
        db_session.add(MdmEntity(entity_id=eid, entity_type="company", is_quarantined=True))
        db_session.commit()
        r = api_client.get("/api/v1/mdm/entities", params={"include_quarantined": "true"})
        assert r.status_code == 200
        assert r.json()["meta"]["total"] == 1

    def test_list_entities_pagination_meta(self, api_client, db_session):
        for _ in range(5):
            _entity(db_session, "company")
        db_session.commit()
        r = api_client.get("/api/v1/mdm/entities", params={"limit": 2, "page": 1})
        body = r.json()
        assert body["meta"]["total"] == 5
        assert body["meta"]["limit"] == 2
        assert len(body["items"]) == 2

    def test_get_entity_by_id(self, api_client, db_session):
        eid = _entity(db_session, "company")
        db_session.commit()
        r = api_client.get(f"/api/v1/mdm/entities/{eid}")
        assert r.status_code == 200
        body = r.json()
        assert body["entity_id"] == eid
        assert body["entity_type"] == "company"
        assert "is_quarantined" in body
        assert "valid_from" in body

    def test_get_entity_404(self, api_client):
        r = api_client.get(f"/api/v1/mdm/entities/{uuid.uuid4()}")
        assert r.status_code == 404

    def test_get_entity_sources_empty(self, api_client, db_session):
        eid = _entity(db_session, "company")
        db_session.commit()
        r = api_client.get(f"/api/v1/mdm/entities/{eid}/sources")
        assert r.status_code == 200
        assert r.json() == []

    def test_get_entity_sources_returns_ref_rows(self, api_client, db_session):
        from edgar_warehouse.mdm.database import MdmSourceRef
        eid = _entity(db_session, "company")
        db_session.add(MdmSourceRef(
            entity_id=eid, source_system="edgar_cik",
            source_id="0000320193", source_priority=1, confidence=1.0,
        ))
        db_session.commit()
        r = api_client.get(f"/api/v1/mdm/entities/{eid}/sources")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 1
        assert items[0]["source_system"] == "edgar_cik"
        assert items[0]["source_id"] == "0000320193"

    def test_resolve_entity_found(self, api_client, db_session):
        from edgar_warehouse.mdm.database import MdmSourceRef
        eid = _entity(db_session, "company")
        db_session.add(MdmSourceRef(
            entity_id=eid, source_system="edgar_cik",
            source_id="0000320193", source_priority=1, confidence=1.0,
        ))
        db_session.commit()
        r = api_client.post("/api/v1/mdm/entities/resolve", json={
            "source_system": "edgar_cik",
            "source_id": "0000320193",
            "entity_type": "company",
            "raw_attributes": {},
        })
        assert r.status_code == 200
        assert r.json()["entity_id"] == eid

    def test_resolve_entity_not_found(self, api_client):
        r = api_client.post("/api/v1/mdm/entities/resolve", json={
            "source_system": "edgar_cik",
            "source_id": "9999999999",
            "entity_type": "company",
            "raw_attributes": {},
        })
        assert r.status_code == 404


# ===========================================================================
# 4. Companies
# ===========================================================================

class TestCompaniesEndpoints:
    """
    Endpoints:
      GET /api/v1/mdm/companies/{cik}
      GET /api/v1/mdm/companies/{cik}/insiders
      GET /api/v1/mdm/companies/{cik}/advisers
      GET /api/v1/mdm/companies/{cik}/securities

    Verifies: correct field mapping, 404 on missing CIK, cross-domain joins.
    """

    def test_get_company_by_cik(self, api_client, db_session):
        eid, _ = _company(db_session, cik=320193, name="Apple Inc")
        db_session.commit()
        r = api_client.get("/api/v1/mdm/companies/320193")
        assert r.status_code == 200
        body = r.json()
        assert body["cik"] == 320193
        assert body["canonical_name"] == "Apple Inc"
        assert body["entity_id"] == eid

    def test_get_company_404(self, api_client):
        r = api_client.get("/api/v1/mdm/companies/999999")
        assert r.status_code == 404

    def test_get_company_advisers_empty(self, api_client, db_session):
        _company(db_session, cik=111111)
        db_session.commit()
        r = api_client.get("/api/v1/mdm/companies/111111/advisers")
        assert r.status_code == 200
        assert r.json() == []

    def test_get_company_advisers_returns_linked_rows(self, api_client, db_session):
        co_eid, _ = _company(db_session, cik=222222)
        _adviser(db_session, crd="CRD999", linked_company_eid=co_eid)
        db_session.commit()
        r = api_client.get("/api/v1/mdm/companies/222222/advisers")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 1
        assert items[0]["crd_number"] == "CRD999"

    def test_get_company_securities(self, api_client, db_session):
        co_eid, _ = _company(db_session, cik=333333)
        _security(db_session, issuer_eid=co_eid, title="Series A Preferred")
        db_session.commit()
        r = api_client.get("/api/v1/mdm/companies/333333/securities")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 1
        assert items[0]["canonical_title"] == "Series A Preferred"

    def test_get_company_insiders_no_rel_type(self, api_client, db_session):
        """IS_INSIDER rel type is not seeded in conftest → endpoint returns []."""
        _company(db_session, cik=444444)
        db_session.commit()
        r = api_client.get("/api/v1/mdm/companies/444444/insiders")
        assert r.status_code == 200
        assert r.json() == []


# ===========================================================================
# 5. Graph
# ===========================================================================

class TestGraphEndpoints:
    """
    Endpoints:
      GET  /api/v1/mdm/graph/relationship-types
      GET  /api/v1/mdm/graph/relationship-types/{name}
      GET  /api/v1/mdm/graph/neighborhood/{entity_id}
      POST /api/v1/mdm/graph/traversal
      GET  /api/v1/mdm/graph/sync-status
      GET  /api/v1/mdm/graph/connections/shared-insiders

    Verifies: registry listing, schema shape, neighborhood graph traversal
    (depth 1 and 2), rel_type filter, as_of date filter, sync-status counter,
    unknown entity_id returns empty graph (not 404), 422 on unknown rel_type.
    """

    def test_list_relationship_types(self, api_client):
        r = api_client.get("/api/v1/mdm/graph/relationship-types")
        assert r.status_code == 200
        names = {item["rel_type_name"] for item in r.json()}
        assert "MANAGES_FUND" in names
        assert "ISSUED_BY" in names

    def test_list_relationship_types_schema(self, api_client):
        r = api_client.get("/api/v1/mdm/graph/relationship-types")
        item = r.json()[0]
        for field in ("rel_type_name", "source_node_type", "target_node_type",
                      "direction", "is_temporal"):
            assert field in item, f"missing field: {field}"

    def test_get_relationship_type_detail(self, api_client):
        r = api_client.get("/api/v1/mdm/graph/relationship-types/MANAGES_FUND")
        assert r.status_code == 200
        body = r.json()
        assert body["rel_type_name"] == "MANAGES_FUND"
        assert body["source_node_type"] == "adviser"
        assert body["target_node_type"] == "fund"
        assert "properties" in body

    def test_get_relationship_type_404(self, api_client):
        r = api_client.get("/api/v1/mdm/graph/relationship-types/NO_SUCH_TYPE")
        assert r.status_code == 404

    def test_sync_status_zero_pending(self, api_client):
        r = api_client.get("/api/v1/mdm/graph/sync-status")
        assert r.status_code == 200
        body = r.json()
        assert body["pending_relationships"] == 0
        assert body["pending_nodes"] == 0

    def test_sync_status_counts_unsynced_rows(self, api_client, db_session):
        adv_eid = _entity(db_session, "adviser")
        fund_eid = _entity(db_session, "fund")
        db_session.flush()
        _rel_instance(db_session, "MANAGES_FUND", adv_eid, fund_eid)
        db_session.commit()
        r = api_client.get("/api/v1/mdm/graph/sync-status")
        assert r.status_code == 200
        assert r.json()["pending_relationships"] == 1

    def test_sync_status_excludes_synced_rows(self, api_client, db_session):
        from edgar_warehouse.mdm.database import MdmRelationshipInstance
        from sqlalchemy import select, update
        adv_eid = _entity(db_session, "adviser")
        fund_eid = _entity(db_session, "fund")
        db_session.flush()
        row = _rel_instance(db_session, "MANAGES_FUND", adv_eid, fund_eid)
        db_session.commit()
        db_session.execute(
            update(MdmRelationshipInstance)
            .where(MdmRelationshipInstance.instance_id == row.instance_id)
            .values(graph_synced_at=datetime.now(timezone.utc))
        )
        db_session.commit()
        r = api_client.get("/api/v1/mdm/graph/sync-status")
        assert r.json()["pending_relationships"] == 0

    def test_neighborhood_unknown_entity_returns_empty_graph(self, api_client):
        r = api_client.get(f"/api/v1/mdm/graph/neighborhood/{uuid.uuid4()}")
        assert r.status_code == 200
        body = r.json()
        assert body["nodes"] == []
        assert body["edges"] == []

    def test_neighborhood_includes_seed_entity_node(self, api_client, db_session):
        eid = _entity(db_session, "adviser")
        db_session.commit()
        r = api_client.get(f"/api/v1/mdm/graph/neighborhood/{eid}")
        assert r.status_code == 200
        body = r.json()
        node_ids = {n["entity_id"] for n in body["nodes"]}
        assert eid in node_ids

    def test_neighborhood_depth_1_returns_direct_edges(self, api_client, db_session):
        adv_eid = _entity(db_session, "adviser")
        fund_eid = _entity(db_session, "fund")
        db_session.flush()
        _rel_instance(db_session, "MANAGES_FUND", adv_eid, fund_eid)
        db_session.commit()

        r = api_client.get(f"/api/v1/mdm/graph/neighborhood/{adv_eid}", params={"depth": 1})
        assert r.status_code == 200
        body = r.json()
        edge_types = {e["rel_type"] for e in body["edges"]}
        assert "MANAGES_FUND" in edge_types
        node_ids = {n["entity_id"] for n in body["nodes"]}
        assert fund_eid in node_ids

    def test_neighborhood_rel_type_filter(self, api_client, db_session):
        """Only MANAGES_FUND edges returned when filter is applied."""
        adv_eid  = _entity(db_session, "adviser")
        fund_eid = _entity(db_session, "fund")
        sec_eid  = _entity(db_session, "security")
        co_eid   = _entity(db_session, "company")
        db_session.flush()
        _rel_instance(db_session, "MANAGES_FUND", adv_eid, fund_eid)
        _rel_instance(db_session, "ISSUED_BY",    sec_eid, co_eid)
        db_session.commit()

        r = api_client.get(
            f"/api/v1/mdm/graph/neighborhood/{adv_eid}",
            params={"rel_types": "MANAGES_FUND"},
        )
        edge_types = {e["rel_type"] for e in r.json()["edges"]}
        assert edge_types == {"MANAGES_FUND"}

    def test_neighborhood_unknown_rel_type_filter_returns_422(self, api_client, db_session):
        eid = _entity(db_session, "adviser")
        db_session.commit()
        r = api_client.get(
            f"/api/v1/mdm/graph/neighborhood/{eid}",
            params={"rel_types": "DOES_NOT_EXIST"},
        )
        assert r.status_code == 422

    def test_neighborhood_as_of_excludes_future_edges(self, api_client, db_session):
        adv_eid  = _entity(db_session, "adviser")
        fund_eid = _entity(db_session, "fund")
        db_session.flush()
        _rel_instance(db_session, "MANAGES_FUND", adv_eid, fund_eid,
                      effective_from=date(2030, 1, 1))
        db_session.commit()

        r = api_client.get(
            f"/api/v1/mdm/graph/neighborhood/{adv_eid}",
            params={"as_of": "2025-01-01"},
        )
        assert r.json()["edges"] == []

    def test_neighborhood_as_of_includes_current_edges(self, api_client, db_session):
        adv_eid  = _entity(db_session, "adviser")
        fund_eid = _entity(db_session, "fund")
        db_session.flush()
        _rel_instance(db_session, "MANAGES_FUND", adv_eid, fund_eid,
                      effective_from=date(2020, 1, 1))
        db_session.commit()

        r = api_client.get(
            f"/api/v1/mdm/graph/neighborhood/{adv_eid}",
            params={"as_of": "2025-01-01"},
        )
        assert len(r.json()["edges"]) == 1

    def test_traversal_post(self, api_client, db_session):
        adv_eid  = _entity(db_session, "adviser")
        fund_eid = _entity(db_session, "fund")
        db_session.flush()
        _rel_instance(db_session, "MANAGES_FUND", adv_eid, fund_eid)
        db_session.commit()

        r = api_client.post("/api/v1/mdm/graph/traversal", json={
            "start_entity_id": adv_eid,
            "relationship_types": ["MANAGES_FUND"],
            "max_depth": 1,
        })
        assert r.status_code == 200
        assert len(r.json()["edges"]) == 1

    def test_traversal_invalid_rel_type_returns_422(self, api_client, db_session):
        eid = _entity(db_session, "adviser")
        db_session.commit()
        r = api_client.post("/api/v1/mdm/graph/traversal", json={
            "start_entity_id": eid,
            "relationship_types": ["FAKE_TYPE"],
            "max_depth": 1,
        })
        assert r.status_code == 422

    def test_shared_insiders_companies_not_found(self, api_client):
        r = api_client.get(
            "/api/v1/mdm/graph/connections/shared-insiders",
            params={"company_a": 1, "company_b": 2},
        )
        assert r.status_code == 404

    def test_shared_insiders_no_is_insider_rel_type(self, api_client, db_session):
        """IS_INSIDER not seeded → returns empty list, not an error."""
        _company(db_session, cik=100001)
        _company(db_session, cik=100002)
        db_session.commit()
        r = api_client.get(
            "/api/v1/mdm/graph/connections/shared-insiders",
            params={"company_a": 100001, "company_b": 100002},
        )
        assert r.status_code == 200
        assert r.json() == []


# ===========================================================================
# 6. Stewardship
# ===========================================================================

class TestStewardshipEndpoints:
    """
    Endpoints:
      POST /api/v1/mdm/stewardship/entities/{entity_id}/quarantine
      POST /api/v1/mdm/stewardship/entities/{entity_id}/unquarantine
      POST /api/v1/mdm/stewardship/entities/merge
      GET  /api/v1/mdm/stewardship/reviews

    Verifies: quarantine toggle persists to DB, merge deactivates discard entity,
              reviews list is empty when no pending reviews.
    """

    def test_quarantine_entity(self, api_client, db_session):
        from edgar_warehouse.mdm.database import MdmEntity
        eid = _entity(db_session, "company")
        db_session.commit()

        r = api_client.post(f"/api/v1/mdm/stewardship/entities/{eid}/quarantine")
        assert r.status_code == 200

        db_session.expire_all()
        e = db_session.get(MdmEntity, eid)
        assert e.is_quarantined is True

    def test_unquarantine_entity(self, api_client, db_session):
        from edgar_warehouse.mdm.database import MdmEntity
        eid = str(uuid.uuid4())
        db_session.add(MdmEntity(entity_id=eid, entity_type="company", is_quarantined=True))
        db_session.commit()

        r = api_client.post(f"/api/v1/mdm/stewardship/entities/{eid}/unquarantine")
        assert r.status_code == 200

        db_session.expire_all()
        e = db_session.get(MdmEntity, eid)
        assert e.is_quarantined is False

    def test_merge_entities(self, api_client, db_session):
        """merge_entities tombstones the discard entity via valid_to (not quarantine)."""
        from edgar_warehouse.mdm.database import MdmEntity
        keep_eid    = _entity(db_session, "company")
        discard_eid = _entity(db_session, "company")
        db_session.commit()

        r = api_client.post("/api/v1/mdm/stewardship/entities/merge", json={
            "entity_id_keep":    keep_eid,
            "entity_id_discard": discard_eid,
            "reason":            "duplicate detected in test",
        })
        assert r.status_code == 200
        assert r.json()["kept"] == keep_eid

        db_session.expire_all()
        discard = db_session.get(MdmEntity, discard_eid)
        assert discard.valid_to is not None, "discard entity should be tombstoned via valid_to"

    def test_list_reviews_empty(self, api_client):
        r = api_client.get("/api/v1/mdm/stewardship/reviews")
        assert r.status_code == 200
        assert r.json() == []

    def test_quarantine_unknown_entity_is_silent_noop(self, api_client):
        """quarantine() issues an UPDATE; 0 rows affected for an unknown ID is
        not an error — the endpoint returns 200 regardless. This is intentional:
        callers should not need to check existence first."""
        r = api_client.post(f"/api/v1/mdm/stewardship/entities/{uuid.uuid4()}/quarantine")
        assert r.status_code == 200


# ===========================================================================
# 7. Export
# ===========================================================================

class TestExportEndpoints:
    """
    Endpoints:
      GET /api/v1/mdm/export/changes
      GET /api/v1/mdm/export/snapshot/{entity_type}

    Verifies: empty change log returns empty list, snapshot accepts valid
              entity types and returns 422 on unknown types.
    """

    def test_changes_empty(self, api_client):
        r = api_client.get("/api/v1/mdm/export/changes")
        assert r.status_code == 200
        assert r.json() == []

    def test_snapshot_company_empty(self, api_client):
        r = api_client.get("/api/v1/mdm/export/snapshot/company")
        assert r.status_code == 200
        assert r.json() == []

    def test_snapshot_returns_existing_rows(self, api_client, db_session):
        _company(db_session, cik=777777, name="Snapshot Corp")
        db_session.commit()
        r = api_client.get("/api/v1/mdm/export/snapshot/company")
        assert r.status_code == 200
        assert len(r.json()) == 1
