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
    def __init__(
        self,
        record: dict | None = None,
        records: list[dict] | None = None,
    ) -> None:
        self._record = record or {"ok": 1}
        self._records = records if records is not None else [self._record]

    def single(self):
        return self._record

    def __iter__(self):
        return iter(self._records)


class _FakeGraphSession:
    def __init__(
        self,
        *,
        fail: bool = False,
        counts: dict[str, int] | None = None,
        edge_presence: dict[tuple[str, str, str], bool] | None = None,
        extra_edges: dict[str, list[dict]] | None = None,
    ) -> None:
        self.fail = fail
        self.counts = counts or {}
        self.edge_presence = edge_presence or {}
        self.extra_edges = extra_edges or {}
        self.calls: list[tuple[str, dict]] = []

    def run(self, query: str, **kwargs):
        self.calls.append((query, kwargs))
        if self.fail:
            raise RuntimeError("failed against neo4j://neo4j:secret@example.internal")
        if "count(n) AS n" in query:
            label = query.split("MATCH (n:", 1)[1].split(")", 1)[0]
            return _FakeResult({"n": self.counts.get(f"label:{label}", 0)})
        if "count(r) AS n" in query:
            rel_type = query.split("[r:", 1)[1].split("]", 1)[0]
            if "source_entity_id" in kwargs:
                key = (
                    rel_type,
                    kwargs["source_entity_id"],
                    kwargs["target_entity_id"],
                )
                return _FakeResult({"n": 1 if self.edge_presence.get(key) else 0})
            return _FakeResult({"n": self.counts.get(f"relationship:{rel_type}", 0)})
        if "source_entity_id" in query and "target_entity_id" in query:
            rel_type = query.split("[r:", 1)[1].split("]", 1)[0]
            return _FakeResult(records=self.extra_edges.get(rel_type, []))
        return _FakeResult()


class _FakeGraphClient:
    def __init__(
        self,
        *,
        fail: bool = False,
        counts: dict[str, int] | None = None,
        edge_presence: dict[tuple[str, str, str], bool] | None = None,
        extra_edges: dict[str, list[dict]] | None = None,
    ) -> None:
        self.graph_session = _FakeGraphSession(
            fail=fail,
            counts=counts,
            edge_presence=edge_presence,
            extra_edges=extra_edges,
        )
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


def test_get_neo4j_graph_metrics_counts_nodes_and_edges_by_registry_names():
    from edgar_warehouse.mdm.graph_readonly import get_neo4j_graph_metrics

    client = _FakeGraphClient(
        counts={
            "label:Company": 7,
            "label:Fund": 3,
            "relationship:MANAGES_FUND": 2,
            "relationship:OWNS_COMPANY": 5,
        }
    )

    result = get_neo4j_graph_metrics(
        entity_labels=["Company", "Fund"],
        relationship_types=["MANAGES_FUND", "OWNS_COMPANY"],
        client=client,
    )
    payload = result.as_dict()

    assert payload["available"] is True
    assert payload["node_counts"]["Company"]["node_count"] == 7
    assert payload["node_counts"]["Fund"]["node_count"] == 3
    assert payload["relationship_counts"]["MANAGES_FUND"]["edge_count"] == 2
    assert payload["relationship_counts"]["OWNS_COMPANY"]["edge_count"] == 5
    assert payload["missing_edge_samples"] == {
        "MANAGES_FUND": [],
        "OWNS_COMPANY": [],
    }
    assert payload["extra_graph_samples"] == {
        "MANAGES_FUND": [],
        "OWNS_COMPANY": [],
    }
    assert all(
        ("MATCH" in query or "RETURN" in query)
        and not (set(query.upper().split()) & WRITE_TOKENS)
        for query, _kwargs in client.graph_session.calls
    )


def test_graph_metrics_rejects_unsafe_dynamic_identifiers_before_cypher_runs():
    from edgar_warehouse.mdm.graph_readonly import (
        find_missing_edge_samples,
        get_neo4j_graph_metrics,
    )

    client = _FakeGraphClient()

    result = get_neo4j_graph_metrics(
        entity_labels=["Company) MATCH (x"],
        relationship_types=["MANAGES_FUND"],
        client=client,
    )

    assert result.available is False
    assert result.state == "invalid_identifier"
    assert client.graph_session.calls == []

    samples = find_missing_edge_samples(
        client=client,
        relationship_type="MANAGES_FUND DELETE",
        candidate_rows=[
            {
                "relationship_type": "MANAGES_FUND",
                "source_entity_id": "source-1",
                "target_entity_id": "target-1",
            }
        ],
    )

    assert samples == []
    assert client.graph_session.calls == []


def test_graph_metrics_query_failures_return_secret_safe_unavailable_payload():
    from edgar_warehouse.mdm.graph_readonly import get_neo4j_graph_metrics

    result = get_neo4j_graph_metrics(
        entity_labels=["Company"],
        relationship_types=["MANAGES_FUND"],
        client=_FakeGraphClient(fail=True),
    )
    payload = result.as_dict()
    rendered = repr(payload)

    assert payload["available"] is False
    assert payload["connected"] is False
    assert payload["state"] == "query_failed"
    assert payload["message"] == NEO4J_QUERY_FAILED_COPY
    assert "NEO4J_URI" in rendered
    assert "NEO4J_USER" in rendered
    assert "NEO4J_PASSWORD" in rendered
    assert "secret" not in rendered
    assert "example.internal" not in rendered
    assert "failed against" not in rendered


def test_graph_metrics_missing_config_returns_secret_safe_unavailable_payload():
    from edgar_warehouse.mdm.graph_readonly import get_neo4j_graph_metrics

    with patch.dict(os.environ, {}, clear=True):
        result = get_neo4j_graph_metrics(
            entity_labels=["Company"],
            relationship_types=["MANAGES_FUND"],
        )

    payload = result.as_dict()
    assert payload["available"] is False
    assert payload["connected"] is False
    assert payload["state"] == "not_configured"
    assert payload["message"] == NEO4J_NOT_CONFIGURED_COPY
    assert payload["env_vars"] == ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"]


def test_find_missing_edge_samples_checks_bounded_candidates_and_readable_fields():
    from edgar_warehouse.mdm.graph_readonly import find_missing_edge_samples

    client = _FakeGraphClient(
        edge_presence={
            ("MANAGES_FUND", "adviser-1", "fund-1"): True,
            ("MANAGES_FUND", "adviser-2", "fund-2"): False,
            ("MANAGES_FUND", "adviser-3", "fund-3"): False,
        }
    )
    candidate_rows = [
        {
            "relationship_type": "MANAGES_FUND",
            "source_entity_id": "adviser-1",
            "source_entity_name": "Alpha Adviser",
            "target_entity_id": "fund-1",
            "target_entity_name": "Alpha Fund",
            "properties": {"raw": "hidden"},
        },
        {
            "relationship_type": "MANAGES_FUND",
            "source_entity_id": "adviser-2",
            "source_entity_name": "Beta Adviser",
            "target_entity_id": "fund-2",
            "target_entity_name": "Beta Fund",
        },
        {
            "relationship_type": "MANAGES_FUND",
            "source_entity_id": "adviser-3",
            "source_entity_name": "Gamma Adviser",
            "target_entity_id": "fund-3",
            "target_entity_name": "Gamma Fund",
        },
    ]

    samples = find_missing_edge_samples(
        client=client,
        relationship_type="MANAGES_FUND",
        candidate_rows=candidate_rows,
        limit=2,
    )
    payload = [sample.as_dict() for sample in samples]

    assert [row["source_entity_id"] for row in payload] == ["adviser-2"]
    assert set(payload[0]) == {
        "relationship_type",
        "source_entity_id",
        "source_entity_name",
        "target_entity_id",
        "target_entity_name",
    }
    assert len(client.graph_session.calls) == 2
    assert all(
        ("MATCH" in query or "RETURN" in query)
        and not (set(query.upper().split()) & WRITE_TOKENS)
        for query, _kwargs in client.graph_session.calls
    )


def test_find_extra_graph_samples_filters_known_mdm_keys_and_hides_properties():
    from edgar_warehouse.mdm.graph_readonly import find_extra_graph_samples

    client = _FakeGraphClient(
        extra_edges={
            "MANAGES_FUND": [
                {
                    "source_entity_id": "adviser-1",
                    "source_entity_name": "Alpha Adviser",
                    "target_entity_id": "fund-1",
                    "target_entity_name": "Alpha Fund",
                    "properties": {"raw": "hidden"},
                },
                {
                    "source_entity_id": "adviser-9",
                    "source_entity_name": "Extra Adviser",
                    "target_entity_id": "fund-9",
                    "target_entity_name": "Extra Fund",
                    "properties": {"raw": "hidden"},
                },
                {
                    "source_entity_id": "adviser-8",
                    "source_entity_name": "Second Extra Adviser",
                    "target_entity_id": "fund-8",
                    "target_entity_name": "Second Extra Fund",
                },
            ]
        }
    )

    samples = find_extra_graph_samples(
        client=client,
        relationship_type="MANAGES_FUND",
        known_mdm_edge_keys=[("MANAGES_FUND", "adviser-1", "fund-1")],
        limit=1,
    )
    payload = [sample.as_dict() for sample in samples]

    assert payload == [
        {
            "relationship_type": "MANAGES_FUND",
            "source_entity_id": "adviser-9",
            "source_entity_name": "Extra Adviser",
            "target_entity_id": "fund-9",
            "target_entity_name": "Extra Fund",
        }
    ]
    assert len(client.graph_session.calls) == 1
    assert all("properties" not in row for row in payload)
    assert all(
        ("MATCH" in query or "RETURN" in query)
        and not (set(query.upper().split()) & WRITE_TOKENS)
        for query, _kwargs in client.graph_session.calls
    )
