"""Shared fixtures for MDM tests.

Provides an in-memory SQLite session pre-loaded with the MDM schema and
the minimum seed rows required by the graph layer (entity-type definitions
and relationship types). SQLite doesn't have NOW() so we register it here.

Also provides a FastAPI TestClient that wires the in-memory session through
the app's dependency-injection system and uses real auth with MDM_API_KEYS
set in the environment (no require_api_key dependency override).

The neo4j_client fixture creates a real Neo4jGraphClient from NEO4J_*
environment variables. If these are not set the fixture raises KeyError —
tests that need Neo4j must be run with credentials exported (e.g. hydrated
from Azure Key Vault via test-mdm-e2e.sh). Silent skips are intentional
omissions; we want loud failures instead.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Generator
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import (
    Base,
    MdmEntityTypeDefinition,
    MdmRelationshipType,
)

TEST_API_KEY = "test-key-abc123"


# ---------------------------------------------------------------------------
# SQLite compatibility
# ---------------------------------------------------------------------------

@event.listens_for(Engine, "connect")
def _register_sqlite_functions(dbapi_conn, _record):
    """Register NOW() so server_default=text('NOW()') works in SQLite."""
    dbapi_conn.create_function("NOW", 0, lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Minimal seed helpers
# ---------------------------------------------------------------------------

def _seed_entity_type(session: Session, entity_type: str, label: str, table: str) -> None:
    session.add(MdmEntityTypeDefinition(
        entity_type=entity_type,
        neo4j_label=label,
        domain_table=table,
        api_path_prefix=f"/{entity_type}s",
        primary_id_field="entity_id",
        display_name=label,
        is_active=True,
    ))


def _seed_rel_type(
    session: Session,
    name: str,
    src: str,
    tgt: str,
    strategy: str = "extend_temporal",
) -> str:
    rt_id = str(uuid.uuid4())
    session.add(MdmRelationshipType(
        rel_type_id=rt_id,
        rel_type_name=name,
        source_node_type=src,
        target_node_type=tgt,
        direction="outbound",
        is_temporal=True,
        merge_strategy=strategy,
        is_active=True,
    ))
    return rt_id


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """In-memory SQLite session with MDM schema + minimal graph seed data.

    check_same_thread=False is required because FastAPI's TestClient runs
    request handlers in a worker thread while the session is created here in
    the test thread.  The StaticPool keeps a single in-memory connection so
    the schema and seed data created here are visible to request handlers.
    """
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        _seed_entity_type(session, "company",  "Company",  "mdm_company")
        _seed_entity_type(session, "adviser",  "Adviser",  "mdm_adviser")
        _seed_entity_type(session, "fund",     "Fund",     "mdm_fund")
        _seed_entity_type(session, "security", "Security", "mdm_security")
        _seed_rel_type(session, "MANAGES_FUND", "adviser",  "fund")
        _seed_rel_type(session, "ISSUED_BY",    "security", "company")
        session.commit()
        yield session


@pytest.fixture
def neo4j_client():
    """Real Neo4jGraphClient connected to the Neo4j instance specified by env vars.

    Reads NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD from the environment.
    Raises KeyError if any variable is absent — this is intentional so that
    misconfigured environments fail loudly rather than skipping silently.

    Normalises neo4j:// -> bolt:// to avoid routing-discovery failures on
    single-instance Azure Container Apps deployments.

    Tests that write nodes/edges to Neo4j must clean up within the test body:
        with neo4j_client.session() as s:
            s.run("MATCH (n) WHERE n.entity_id IN $ids DETACH DELETE n", ids=[...])
    """
    from edgar_warehouse.mdm.graph import Neo4jGraphClient

    uri  = os.environ["NEO4J_URI"]
    user = os.environ["NEO4J_USER"]
    pw   = os.environ["NEO4J_PASSWORD"]
    if uri.startswith("neo4j://"):
        uri = "bolt://" + uri[len("neo4j://"):]
    client = Neo4jGraphClient(uri=uri, user=user, password=pw)
    client.connect()
    yield client
    client.close()


@pytest.fixture
def api_client(db_session):
    """FastAPI TestClient with real auth wired to the in-memory SQLite session.

    - DB dependency is overridden to yield db_session.
    - Auth uses real _load_keys() reading MDM_API_KEYS from the environment
      (no require_api_key dependency override).
    - MDM_API_KEY_SECRET_ID is masked to prevent accidental Key Vault fetches.
    - _SECRET_CACHE is reset to None via patch.object so each test starts with
      a fresh key-load from the environment.
    - All requests include X-API-Key: TEST_API_KEY by default.
    - Neo4j dependency is NOT globally overridden; graph-endpoint tests that
      need Neo4j behaviour should add their own override.
    """
    import edgar_warehouse.mdm.api.auth as _auth
    from fastapi.testclient import TestClient
    from edgar_warehouse.mdm.api.main import create_app
    from edgar_warehouse.mdm.api.deps import get_db

    app = create_app()

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db

    env_patch = {"MDM_API_KEYS": TEST_API_KEY}
    if "MDM_API_KEY_SECRET_ID" in os.environ:
        env_patch["MDM_API_KEY_SECRET_ID"] = ""

    with patch.dict(os.environ, env_patch), patch.object(_auth, "_SECRET_CACHE", None):
        with TestClient(app, raise_server_exceptions=True,
                        headers={"X-API-Key": TEST_API_KEY}) as c:
            yield c
