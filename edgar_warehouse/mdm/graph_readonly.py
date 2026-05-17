"""Review-only Neo4j helpers for the local MDM dashboard."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
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


def _close_client(client: Any) -> None:
    close = getattr(client, "close", None)
    if close is not None:
        close()
