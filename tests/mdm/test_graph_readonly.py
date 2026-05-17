from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch


NEO4J_NOT_CONFIGURED_COPY = (
    "Neo4j is not configured. MDM relationship tables are still available."
)
NEO4J_QUERY_FAILED_COPY = (
    "Neo4j query failed. Check `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, "
    "and network access."
)
WRITE_TOKENS = {"MERGE", "CREATE", "DELETE", "SET", "REMOVE", "CALL"}


class _FakeResult:
    def __init__(self, record: dict | None = None) -> None:
        self._record = record or {"ok": 1}

    def single(self):
        return self._record


class _FakeGraphSession:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, dict]] = []

    def run(self, query: str, **kwargs):
        self.calls.append((query, kwargs))
        if self.fail:
            raise RuntimeError("failed against neo4j://neo4j:secret@example.internal")
        return _FakeResult()


class _FakeGraphClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.graph_session = _FakeGraphSession(fail=fail)
        self.closed = False

    def session(self):
        client = self

        class _Context:
            def __enter__(self):
                return client.graph_session

            def __exit__(self, exc_type, exc, tb):
                return None

        return _Context()

    def close(self) -> None:
        self.closed = True


def test_missing_neo4j_config_returns_optional_not_configured_status():
    from edgar_warehouse.mdm.graph_readonly import (
        Neo4jReviewStatus,
        load_neo4j_review_client,
    )

    with patch.dict(os.environ, {}, clear=True):
        status, client = load_neo4j_review_client()

    assert isinstance(status, Neo4jReviewStatus)
    assert client is None
    assert status.state == "not_configured"
    assert status.connected is False
    assert status.message == NEO4J_NOT_CONFIGURED_COPY
    assert status.env_vars == ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"]


def test_load_neo4j_review_client_uses_existing_env_conventions(monkeypatch):
    from edgar_warehouse.mdm import graph_readonly

    created = {}

    class CapturingClient:
        def __init__(self, *, uri, user, password, database=None):
            created.update(
                {"uri": uri, "user": user, "password": password, "database": database}
            )

    monkeypatch.setattr(graph_readonly, "Neo4jGraphClient", CapturingClient)
    env = {
        "NEO4J_URI": "neo4j://example.internal:7687",
        "NEO4J_USERNAME": "neo4j-user",
        "NEO4J_PASSWORD": "super-secret",
        "NEO4J_DATABASE": "review",
    }
    with patch.dict(os.environ, env, clear=True):
        status, client = graph_readonly.load_neo4j_review_client()

    assert client is not None
    assert status.state == "configured"
    assert status.connected is False
    assert created == {
        "uri": "bolt://example.internal:7687",
        "user": "neo4j-user",
        "password": "super-secret",
        "database": "review",
    }
    rendered = repr(status.as_dict())
    assert "super-secret" not in rendered
    assert "neo4j-user" not in rendered
    assert "example.internal" not in rendered


def test_load_neo4j_review_client_supports_secret_json(monkeypatch):
    from edgar_warehouse.mdm import graph_readonly

    created = {}

    class CapturingClient:
        def __init__(self, *, uri, user, password, database=None):
            created.update(
                {"uri": uri, "user": user, "password": password, "database": database}
            )

    monkeypatch.setattr(graph_readonly, "Neo4jGraphClient", CapturingClient)
    env = {
        "NEO4J_SECRET_JSON": (
            '{"uri":"neo4j://secret-host:7687","username":"secret-user",'
            '"password":"secret-password","database":"neo4j"}'
        )
    }
    with patch.dict(os.environ, env, clear=True):
        status, client = graph_readonly.load_neo4j_review_client()

    assert client is not None
    assert status.state == "configured"
    assert created["uri"] == "bolt://secret-host:7687"
    assert created["user"] == "secret-user"
    assert created["password"] == "secret-password"
    rendered = repr(status.as_dict())
    assert "secret-password" not in rendered
    assert "secret-user" not in rendered
    assert "secret-host" not in rendered


def test_run_neo4j_smoke_query_uses_static_read_only_cypher():
    from edgar_warehouse.mdm.graph_readonly import run_neo4j_smoke_query

    client = _FakeGraphClient()

    status = run_neo4j_smoke_query(client=client)

    assert status.state == "connected"
    assert status.connected is True
    assert status.details["ok"] is True
    assert client.graph_session.calls == [("RETURN 1 AS ok", {})]
    query = client.graph_session.calls[0][0]
    assert query == "RETURN 1 AS ok"
    assert not (set(query.upper().split()) & WRITE_TOKENS)


def test_check_neo4j_status_closes_owned_client(monkeypatch):
    from edgar_warehouse.mdm import graph_readonly

    client = _FakeGraphClient()

    def fake_loader(environ=None):
        return graph_readonly.Neo4jReviewStatus(
            state="configured",
            connected=False,
            message="Neo4j configured.",
        ), client

    monkeypatch.setattr(graph_readonly, "load_neo4j_review_client", fake_loader)

    status = graph_readonly.check_neo4j_status()

    assert status.state == "connected"
    assert status.connected is True
    assert client.closed is True


def test_query_failure_returns_secret_safe_status():
    from edgar_warehouse.mdm.graph_readonly import run_neo4j_smoke_query

    status = run_neo4j_smoke_query(client=_FakeGraphClient(fail=True))
    payload = status.as_dict()
    rendered = repr(payload)

    assert status.state == "query_failed"
    assert status.connected is False
    assert status.message == NEO4J_QUERY_FAILED_COPY
    assert "NEO4J_URI" in rendered
    assert "NEO4J_USER" in rendered
    assert "NEO4J_PASSWORD" in rendered
    assert "secret" not in rendered
    assert "example.internal" not in rendered
    assert "failed against" not in rendered


def test_check_neo4j_status_returns_not_configured_without_raise():
    from edgar_warehouse.mdm.graph_readonly import check_neo4j_status

    with patch.dict(os.environ, {}, clear=True):
        status = check_neo4j_status()

    assert status.state == "not_configured"
    assert status.connected is False
    assert status.message == NEO4J_NOT_CONFIGURED_COPY


def test_graph_readonly_module_avoids_sync_and_write_surfaces():
    module_text = Path("edgar_warehouse/mdm/graph_readonly.py").read_text()

    blocked_tokens = [
        "GraphSyncEngine",
        "relationship_merge_cypher",
        "node_merge_cypher",
        "sync_entities",
        "sync_pending",
        "backfill_relationship_instances",
        "MERGE ",
        "CREATE ",
        "DELETE ",
        "SET ",
        "REMOVE ",
        "CALL ",
    ]
    for token in blocked_tokens:
        assert token not in module_text
