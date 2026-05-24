"""Review-only Neo4j helpers for the local MDM dashboard."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from edgar_warehouse.mdm.graph import Neo4jGraphClient


NEO4J_ENV_VARS = ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"]
NEO4J_NOT_CONFIGURED_MESSAGE = (
    "Neo4j is not configured. MDM relationship tables are still available."
)
NEO4J_QUERY_FAILED_MESSAGE = (
    "Neo4j query failed. Check `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, "
    "and network access."
)
NEO4J_SMOKE_QUERY = "RETURN 1 AS ok"
_CYPHER_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Neo4jReviewStatus:
    state: str
    connected: bool
    message: str
    env_vars: list[str] = field(default_factory=lambda: list(NEO4J_ENV_VARS))
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "connected": self.connected,
            "message": self.message,
            "env_vars": list(self.env_vars),
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class Neo4jNodeMetric:
    label: str
    node_count: int
    status: str = "OK"

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "node_count": self.node_count,
            "status": self.status,
        }


@dataclass(frozen=True)
class Neo4jDiagnosticSample:
    relationship_type: str
    source_entity_id: str
    source_entity_name: str | None
    target_entity_id: str
    target_entity_name: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "relationship_type": self.relationship_type,
            "source_entity_id": self.source_entity_id,
            "source_entity_name": self.source_entity_name,
            "target_entity_id": self.target_entity_id,
            "target_entity_name": self.target_entity_name,
        }


@dataclass(frozen=True)
class Neo4jRelationshipMetric:
    relationship_type: str
    edge_count: int
    status: str = "OK"
    missing_edge_samples: list[Neo4jDiagnosticSample] = field(default_factory=list)
    extra_graph_samples: list[Neo4jDiagnosticSample] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "relationship_type": self.relationship_type,
            "edge_count": self.edge_count,
            "status": self.status,
            "missing_edge_samples": [
                sample.as_dict() for sample in self.missing_edge_samples
            ],
            "extra_graph_samples": [
                sample.as_dict() for sample in self.extra_graph_samples
            ],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class Neo4jGraphMetrics:
    state: str
    available: bool
    connected: bool
    message: str
    node_counts: dict[str, Neo4jNodeMetric] = field(default_factory=dict)
    relationship_counts: dict[str, Neo4jRelationshipMetric] = field(default_factory=dict)
    missing_edge_samples: dict[str, list[Neo4jDiagnosticSample]] = field(
        default_factory=dict
    )
    extra_graph_samples: dict[str, list[Neo4jDiagnosticSample]] = field(
        default_factory=dict
    )
    warnings: list[str] = field(default_factory=list)
    env_vars: list[str] = field(default_factory=lambda: list(NEO4J_ENV_VARS))
    last_refreshed: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "available": self.available,
            "connected": self.connected,
            "message": self.message,
            "node_counts": {
                label: metric.as_dict() for label, metric in self.node_counts.items()
            },
            "relationship_counts": {
                rel_type: metric.as_dict()
                for rel_type, metric in self.relationship_counts.items()
            },
            "missing_edge_samples": {
                rel_type: [sample.as_dict() for sample in samples]
                for rel_type, samples in self.missing_edge_samples.items()
            },
            "extra_graph_samples": {
                rel_type: [sample.as_dict() for sample in samples]
                for rel_type, samples in self.extra_graph_samples.items()
            },
            "warnings": list(self.warnings),
            "env_vars": list(self.env_vars),
            "last_refreshed": self.last_refreshed,
        }


def load_neo4j_review_client(
    environ: Mapping[str, str] | None = None,
) -> tuple[Neo4jReviewStatus, Neo4jGraphClient | None]:
    env = environ if environ is not None else os.environ
    uri = env.get("NEO4J_URI")
    user = env.get("NEO4J_USER") or env.get("NEO4J_USERNAME")
    password = env.get("NEO4J_PASSWORD")
    database = env.get("NEO4J_DATABASE")

    if not (uri and user and password):
        secret_payload = _load_secret_payload(env.get("NEO4J_SECRET_JSON"))
        uri = uri or _string_or_none(secret_payload.get("uri"))
        user = user or _string_or_none(
            secret_payload.get("user") or secret_payload.get("username")
        )
        password = password or _string_or_none(secret_payload.get("password"))
        database = database or _string_or_none(secret_payload.get("database"))

    if not (uri and user and password):
        return _not_configured_status(), None

    client = Neo4jGraphClient(
        uri=_normalize_uri(uri),
        user=user,
        password=password,
        database=database,
    )
    return (
        Neo4jReviewStatus(
            state="configured",
            connected=False,
            message="Neo4j configured.",
            details={"database_configured": bool(database)},
        ),
        client,
    )


def check_neo4j_status(
    *,
    client: Any | None = None,
    environ: Mapping[str, str] | None = None,
) -> Neo4jReviewStatus:
    owned_client = False
    active_client = client
    if active_client is None:
        status, active_client = load_neo4j_review_client(environ=environ)
        if active_client is None:
            return status
        owned_client = True

    try:
        return run_neo4j_smoke_query(client=active_client)
    finally:
        if owned_client:
            _close_client(active_client)


def run_neo4j_smoke_query(*, client: Any | None) -> Neo4jReviewStatus:
    if client is None:
        return _not_configured_status()

    try:
        with client.session() as session:
            record = session.run(NEO4J_SMOKE_QUERY).single()
        ok = bool(record and record["ok"] == 1)
    except Exception:
        return _query_failed_status()

    if not ok:
        return _query_failed_status()
    return Neo4jReviewStatus(
        state="connected",
        connected=True,
        message="Neo4j connected.",
        details={"ok": True},
    )


def get_neo4j_graph_metrics(
    *,
    entity_labels: list[str],
    relationship_types: list[str],
    mdm_diagnostic_inputs: Mapping[str, Any] | None = None,
    client: Any | None = None,
    environ: Mapping[str, str] | None = None,
    per_type_sample_limit: int = 5,
    global_sample_limit: int = 50,
) -> Neo4jGraphMetrics:
    sample_limit = _bounded_limit(per_type_sample_limit, default=5, maximum=50)
    total_limit = _bounded_limit(global_sample_limit, default=50, maximum=500)
    owned_client = False
    active_client = client

    try:
        labels = [_validate_cypher_identifier(label) for label in entity_labels]
        rel_types = [
            _validate_cypher_identifier(rel_type) for rel_type in relationship_types
        ]
    except ValueError:
        return _invalid_identifier_metrics()

    if active_client is None:
        status, active_client = load_neo4j_review_client(environ=environ)
        if active_client is None:
            return _graph_metrics_from_status(status)
        owned_client = True

    try:
        node_counts: dict[str, Neo4jNodeMetric] = {}
        relationship_counts: dict[str, Neo4jRelationshipMetric] = {}
        missing_samples: dict[str, list[Neo4jDiagnosticSample]] = {}
        extra_samples: dict[str, list[Neo4jDiagnosticSample]] = {}
        warnings: list[str] = []
        remaining_sample_slots = total_limit
        diagnostic_inputs = mdm_diagnostic_inputs or {}

        with active_client.session() as session:
            for label in labels:
                query = f"MATCH (n:{label}) RETURN count(n) AS n"
                record = session.run(query).single()
                node_counts[label] = Neo4jNodeMetric(
                    label=label,
                    node_count=_record_int(record, "n"),
                )

            for rel_type in rel_types:
                query = f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS n"
                record = session.run(query).single()
                edge_count = _record_int(record, "n")
                candidate_rows = _diagnostic_candidate_rows(
                    diagnostic_inputs,
                    rel_type,
                )
                known_edge_keys = _diagnostic_edge_keys(diagnostic_inputs, rel_type)
                mdm_active_count = _diagnostic_active_count(
                    diagnostic_inputs,
                    rel_type,
                )
                type_limit = min(sample_limit, remaining_sample_slots)
                missing_for_type: list[Neo4jDiagnosticSample] = []
                extra_for_type: list[Neo4jDiagnosticSample] = []

                if type_limit > 0 and candidate_rows:
                    missing_for_type = _find_missing_edge_samples_with_session(
                        session=session,
                        relationship_type=rel_type,
                        candidate_rows=candidate_rows,
                        limit=type_limit,
                    )
                    remaining_sample_slots -= len(missing_for_type)

                if type_limit > 0 and _needs_extra_samples(
                    edge_count,
                    mdm_active_count,
                ):
                    extra_limit = min(sample_limit, remaining_sample_slots)
                    if extra_limit > 0:
                        extra_for_type = _find_extra_graph_samples_with_session(
                            session=session,
                            relationship_type=rel_type,
                            known_mdm_edge_keys=known_edge_keys,
                            limit=extra_limit,
                        )
                        remaining_sample_slots -= len(extra_for_type)
                    if not extra_for_type:
                        warnings.append(
                            f"{rel_type}: extra graph rows were indicated, "
                            "but no bounded sample rows were returned."
                        )

                missing_samples[rel_type] = missing_for_type
                extra_samples[rel_type] = extra_for_type
                relationship_counts[rel_type] = Neo4jRelationshipMetric(
                    relationship_type=rel_type,
                    edge_count=edge_count,
                    status="OK",
                    missing_edge_samples=missing_for_type,
                    extra_graph_samples=extra_for_type,
                    warnings=[
                        warning
                        for warning in warnings
                        if warning.startswith(f"{rel_type}:")
                    ],
                )
    except ValueError:
        return _invalid_identifier_metrics()
    except Exception:
        return _query_failed_metrics()
    finally:
        if owned_client:
            _close_client(active_client)

    return Neo4jGraphMetrics(
        state="connected",
        available=True,
        connected=True,
        message="Neo4j graph metrics loaded.",
        node_counts=node_counts,
        relationship_counts=relationship_counts,
        missing_edge_samples=missing_samples,
        extra_graph_samples=extra_samples,
        warnings=warnings,
        last_refreshed=_utc_now_iso(),
    )


def find_missing_edge_samples(
    *,
    client: Any,
    relationship_type: str,
    candidate_rows: list[Any],
    limit: int = 5,
) -> list[Neo4jDiagnosticSample]:
    try:
        rel_type = _validate_cypher_identifier(relationship_type)
        row_limit = _bounded_limit(limit, default=5, maximum=50)
        with client.session() as session:
            return _find_missing_edge_samples_with_session(
                session=session,
                relationship_type=rel_type,
                candidate_rows=candidate_rows,
                limit=row_limit,
            )
    except (Exception, ValueError):
        return []


def find_extra_graph_samples(
    *,
    client: Any,
    relationship_type: str,
    known_mdm_edge_keys: list[tuple[str, str, str]],
    limit: int = 5,
) -> list[Neo4jDiagnosticSample]:
    try:
        rel_type = _validate_cypher_identifier(relationship_type)
        row_limit = _bounded_limit(limit, default=5, maximum=50)
        with client.session() as session:
            return _find_extra_graph_samples_with_session(
                session=session,
                relationship_type=rel_type,
                known_mdm_edge_keys=known_mdm_edge_keys,
                limit=row_limit,
            )
    except (Exception, ValueError):
        return []


def _find_missing_edge_samples_with_session(
    *,
    session: Any,
    relationship_type: str,
    candidate_rows: list[Any],
    limit: int,
) -> list[Neo4jDiagnosticSample]:
    rel_type = _validate_cypher_identifier(relationship_type)
    row_limit = _bounded_limit(limit, default=5, maximum=50)
    samples: list[Neo4jDiagnosticSample] = []
    if row_limit <= 0:
        return samples
    query = (
        f"MATCH (s)-[r:{rel_type}]->(t) "
        "WHERE s.entity_id = $source_entity_id "
        "AND t.entity_id = $target_entity_id "
        "RETURN count(r) AS n"
    )
    checked = 0
    for row in candidate_rows:
        if checked >= row_limit:
            break
        if _row_value(row, "relationship_type") != rel_type:
            continue
        source_entity_id = _string_or_empty(_row_value(row, "source_entity_id"))
        target_entity_id = _string_or_empty(_row_value(row, "target_entity_id"))
        if not source_entity_id or not target_entity_id:
            continue
        checked += 1
        record = session.run(
            query,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
        ).single()
        if _record_int(record, "n") == 0:
            samples.append(
                Neo4jDiagnosticSample(
                    relationship_type=rel_type,
                    source_entity_id=source_entity_id,
                    source_entity_name=_optional_string(
                        _row_value(row, "source_entity_name")
                    ),
                    target_entity_id=target_entity_id,
                    target_entity_name=_optional_string(
                        _row_value(row, "target_entity_name")
                    ),
                )
            )
    return samples[:row_limit]


def _find_extra_graph_samples_with_session(
    *,
    session: Any,
    relationship_type: str,
    known_mdm_edge_keys: list[tuple[str, str, str]],
    limit: int,
) -> list[Neo4jDiagnosticSample]:
    rel_type = _validate_cypher_identifier(relationship_type)
    row_limit = _bounded_limit(limit, default=5, maximum=50)
    if row_limit <= 0:
        return []
    known_keys = {
        (str(item[0]), str(item[1]), str(item[2]))
        for item in known_mdm_edge_keys
        if len(item) == 3
    }
    query = (
        f"MATCH (s)-[r:{rel_type}]->(t) "
        "RETURN s.entity_id AS source_entity_id, "
        "coalesce(s.canonical_name, s.name, s.entity_id) AS source_entity_name, "
        "t.entity_id AS target_entity_id, "
        "coalesce(t.canonical_name, t.name, t.entity_id) AS target_entity_name "
        "LIMIT $limit"
    )
    samples: list[Neo4jDiagnosticSample] = []
    for record in session.run(query, limit=row_limit * 2):
        source_entity_id = _string_or_empty(_record_value(record, "source_entity_id"))
        target_entity_id = _string_or_empty(_record_value(record, "target_entity_id"))
        key = (rel_type, source_entity_id, target_entity_id)
        if not source_entity_id or not target_entity_id or key in known_keys:
            continue
        samples.append(
            Neo4jDiagnosticSample(
                relationship_type=rel_type,
                source_entity_id=source_entity_id,
                source_entity_name=_optional_string(
                    _record_value(record, "source_entity_name")
                ),
                target_entity_id=target_entity_id,
                target_entity_name=_optional_string(
                    _record_value(record, "target_entity_name")
                ),
            )
        )
        if len(samples) >= row_limit:
            break
    return samples


def _load_secret_payload(raw_secret: str | None) -> dict[str, Any]:
    if not raw_secret:
        return {}
    try:
        payload = json.loads(raw_secret)
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _normalize_uri(uri: str) -> str:
    if uri.startswith("neo4j://"):
        return "bolt://" + uri[len("neo4j://") :]
    return uri


def _not_configured_status() -> Neo4jReviewStatus:
    return Neo4jReviewStatus(
        state="not_configured",
        connected=False,
        message=NEO4J_NOT_CONFIGURED_MESSAGE,
    )


def _query_failed_status() -> Neo4jReviewStatus:
    return Neo4jReviewStatus(
        state="query_failed",
        connected=False,
        message=NEO4J_QUERY_FAILED_MESSAGE,
    )


def _graph_metrics_from_status(status: Neo4jReviewStatus) -> Neo4jGraphMetrics:
    return Neo4jGraphMetrics(
        state=status.state,
        available=False,
        connected=status.connected,
        message=status.message,
        env_vars=list(status.env_vars),
    )


def _query_failed_metrics() -> Neo4jGraphMetrics:
    return Neo4jGraphMetrics(
        state="query_failed",
        available=False,
        connected=False,
        message=NEO4J_QUERY_FAILED_MESSAGE,
    )


def _invalid_identifier_metrics() -> Neo4jGraphMetrics:
    return Neo4jGraphMetrics(
        state="invalid_identifier",
        available=False,
        connected=False,
        message="Neo4j graph metric labels and relationship types must be registry identifiers.",
    )


def _validate_cypher_identifier(value: str) -> str:
    if not isinstance(value, str) or not _CYPHER_IDENTIFIER_RE.fullmatch(value):
        raise ValueError("Unsafe Cypher identifier.")
    return value


def _bounded_limit(limit: int, *, default: int, maximum: int) -> int:
    try:
        requested = int(limit)
    except (TypeError, ValueError):
        requested = default
    return max(0, min(requested, maximum))


def _record_int(record: Any, key: str) -> int:
    try:
        return int(_record_value(record, key) or 0)
    except (TypeError, ValueError):
        return 0


def _record_value(record: Any, key: str) -> Any:
    if record is None:
        return None
    get = getattr(record, "get", None)
    if get is not None:
        return get(key)
    try:
        return record[key]
    except (KeyError, TypeError):
        return None


def _row_value(row: Any, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key, None)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _string_or_empty(value: Any) -> str:
    text = _optional_string(value)
    return text or ""


def _diagnostic_candidate_rows(
    diagnostic_inputs: Mapping[str, Any],
    relationship_type: str,
) -> list[Any]:
    rows = diagnostic_inputs.get("candidate_rows", [])
    if isinstance(rows, list):
        return [
            row
            for row in rows
            if _row_value(row, "relationship_type") == relationship_type
        ]
    return []


def _diagnostic_edge_keys(
    diagnostic_inputs: Mapping[str, Any],
    relationship_type: str,
) -> list[tuple[str, str, str]]:
    edge_keys = diagnostic_inputs.get("known_mdm_edge_keys", {})
    if not isinstance(edge_keys, Mapping):
        return []
    raw_keys = edge_keys.get(relationship_type, [])
    normalized: list[tuple[str, str, str]] = []
    for raw_key in raw_keys:
        if isinstance(raw_key, (list, tuple)) and len(raw_key) == 3:
            normalized.append((str(raw_key[0]), str(raw_key[1]), str(raw_key[2])))
    return normalized


def _diagnostic_active_count(
    diagnostic_inputs: Mapping[str, Any],
    relationship_type: str,
) -> int | None:
    active_counts = diagnostic_inputs.get("active_relationship_counts", {})
    if not isinstance(active_counts, Mapping) or relationship_type not in active_counts:
        return None
    try:
        return int(active_counts[relationship_type] or 0)
    except (TypeError, ValueError):
        return None


def _needs_extra_samples(edge_count: int, mdm_active_count: int | None) -> bool:
    return mdm_active_count is not None and edge_count > mdm_active_count


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _close_client(client: Any) -> None:
    close = getattr(client, "close", None)
    if close is not None:
        close()
