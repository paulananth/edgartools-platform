"""Read-only hosted graph helpers for the local MDM dashboard."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from edgar_warehouse.mdm.export import SnowflakeConnectionSettings
from edgar_warehouse.mdm.snowflake_graph import (
    DEFAULT_MDM_SCHEMA,
    DEFAULT_NATIVE_APP_COMPUTE_POOL,
    DEFAULT_NATIVE_APP_DATABASE_ROLE,
    DEFAULT_NATIVE_APP_NAME,
    DEFAULT_TARGET_SCHEMA,
    SnowflakeGraphVerificationConfig,
    SnowflakeGraphVerifier,
)


SNOWFLAKE_GRAPH_UNAVAILABLE_MESSAGE = (
    "Snowflake graph metrics unavailable. MDM overview remains available."
)
SNOWFLAKE_GRAPH_PERMISSION_DENIED_MESSAGE = (
    "Snowflake graph permission denied. Confirm the configured Snowflake role "
    "can run read-only graph diagnostics."
)
SNOWFLAKE_GRAPH_LOADED_MESSAGE = "Snowflake graph metrics loaded."
SNOWFLAKE_GRAPH_MISMATCH_MESSAGE = (
    "Snowflake graph diagnostics loaded with mismatches."
)
SNOWFLAKE_GRAPH_SETTING_NAMES = (
    "SNOWFLAKE_CONNECTION",
    "MDM_SNOWFLAKE_ACCOUNT",
    "MDM_SNOWFLAKE_USER",
    "MDM_SNOWFLAKE_PASSWORD",
    "MDM_SNOWFLAKE_DATABASE",
    "MDM_SNOWFLAKE_SCHEMA",
    "MDM_SNOWFLAKE_WAREHOUSE",
    "MDM_SNOWFLAKE_ROLE",
    "MDM_SNOWFLAKE_SECRET_JSON",
    "DBT_SNOWFLAKE_ACCOUNT",
    "DBT_SNOWFLAKE_USER",
    "DBT_SNOWFLAKE_PASSWORD",
    "DBT_SNOWFLAKE_DATABASE",
    "DBT_SNOWFLAKE_SCHEMA",
    "DBT_SNOWFLAKE_WAREHOUSE",
    "DBT_SNOWFLAKE_ROLE",
    "DBT_SNOWFLAKE_SECRET_JSON",
)


def _empty_diagnostics() -> dict[str, list[dict[str, Any]]]:
    return {
        "missing_graph_nodes": [],
        "extra_graph_nodes": [],
        "missing_graph_edges": [],
        "extra_graph_edges": [],
        "missing_graph_edge_endpoints": [],
    }


def _empty_native_app() -> dict[str, Any]:
    return {
        "status": "unavailable",
        "required": True,
        "phase3_acceptance": False,
        "failing_checks": [],
    }


@dataclass(frozen=True)
class SnowflakeGraphDashboardMetrics:
    available: bool
    state: str
    message: str
    target: dict[str, Any] = field(default_factory=dict)
    snowflake_graph_nodes: int = 0
    snowflake_graph_edges: int = 0
    entity_comparison: list[dict[str, Any]] = field(default_factory=list)
    relationship_comparison: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, list[dict[str, Any]]] = field(default_factory=_empty_diagnostics)
    native_app: dict[str, Any] = field(default_factory=_empty_native_app)
    last_refreshed: str | None = None
    error_setting_names: tuple[str, ...] = ()
    warnings: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "state": self.state,
            "message": self.message,
            "target": dict(self.target),
            "snowflake_graph_nodes": self.snowflake_graph_nodes,
            "snowflake_graph_edges": self.snowflake_graph_edges,
            "entity_comparison": list(self.entity_comparison),
            "relationship_comparison": list(self.relationship_comparison),
            "diagnostics": {
                key: list(rows) for key, rows in self.diagnostics.items()
            },
            "native_app": dict(self.native_app),
            "last_refreshed": self.last_refreshed,
            "error_setting_names": list(self.error_setting_names),
            "warnings": list(self.warnings),
        }


def get_snowflake_graph_metrics(
    *,
    verifier: Any | None = None,
    connection: Any | None = None,
    target_database: str | None = None,
    target_schema: str = DEFAULT_TARGET_SCHEMA,
    mdm_database: str | None = None,
    mdm_schema: str = DEFAULT_MDM_SCHEMA,
    sample_limit: int = 20,
    verify_native_app: bool = True,
    native_app_name: str = DEFAULT_NATIVE_APP_NAME,
    native_app_database_role: str = DEFAULT_NATIVE_APP_DATABASE_ROLE,
    native_app_compute_pool: str = DEFAULT_NATIVE_APP_COMPUTE_POOL,
) -> SnowflakeGraphDashboardMetrics:
    """Load hosted graph dashboard metrics through the strict verifier boundary."""

    owned_connection: Any | None = None
    try:
        active_verifier = verifier
        default_database = target_database
        if active_verifier is None:
            if connection is None:
                settings = SnowflakeConnectionSettings.from_env()
                owned_connection = settings.connect()
                connection = owned_connection
                default_database = settings.database
            active_verifier = SnowflakeGraphVerifier(
                connection,
                default_database=default_database,
            )

        resolved_target_database = target_database or default_database
        result = active_verifier.verify(
            SnowflakeGraphVerificationConfig(
                target_database=resolved_target_database,
                target_schema=target_schema,
                mdm_database=mdm_database or resolved_target_database,
                mdm_schema=mdm_schema,
                sample_limit=_bounded_sample_limit(sample_limit),
                verify_native_app=verify_native_app,
                native_app_name=native_app_name,
                native_app_database_role=native_app_database_role,
                native_app_compute_pool=native_app_compute_pool,
            )
        )
        return _metrics_from_payload(
            result.payload,
            sample_limit=_bounded_sample_limit(sample_limit),
        )
    except Exception as exc:
        return _unavailable_metrics(exc)
    finally:
        if owned_connection is not None:
            try:
                owned_connection.close()
            except Exception:
                pass


def _metrics_from_payload(
    payload: dict[str, Any],
    *,
    sample_limit: int,
) -> SnowflakeGraphDashboardMetrics:
    status = str(payload.get("status") or "").lower()
    state = "ok" if status == "ok" else "failed"
    return SnowflakeGraphDashboardMetrics(
        available=True,
        state=state,
        message=(
            SNOWFLAKE_GRAPH_LOADED_MESSAGE
            if state == "ok"
            else SNOWFLAKE_GRAPH_MISMATCH_MESSAGE
        ),
        target=dict(payload.get("target") or {}),
        snowflake_graph_nodes=_int_value(payload.get("snowflake_graph_nodes")),
        snowflake_graph_edges=_int_value(payload.get("snowflake_graph_edges")),
        entity_comparison=_entity_comparison_rows(payload),
        relationship_comparison=_relationship_comparison_rows(payload),
        diagnostics=_diagnostics_payload(payload, sample_limit=sample_limit),
        native_app=_native_app_payload(payload.get("native_app")),
        last_refreshed=_utc_now_iso(),
    )


def _entity_comparison_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    node_parity = payload.get("node_parity") or {}
    rows = node_parity.get("by_entity_type") or []
    return [
        {
            "entity_type": str(row.get("entity_type") or ""),
            "mdm_active_count": _int_value(row.get("mdm_active_count")),
            "snowflake_graph_node_count": _int_value(
                row.get("snowflake_graph_node_count")
            ),
            "mdm_minus_graph": _int_value(row.get("mdm_minus_graph")),
            "graph_minus_mdm": _int_value(row.get("graph_minus_mdm")),
            "status": _parity_status(row),
        }
        for row in rows
        if isinstance(row, dict)
    ]


def _relationship_comparison_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    relationship_parity = payload.get("relationship_parity") or {}
    rows = relationship_parity.get("by_relationship_type") or []
    return [
        {
            "relationship_type": str(row.get("relationship_type") or ""),
            "mdm_active_count": _int_value(row.get("mdm_active_count")),
            "snowflake_graph_edge_count": _int_value(
                row.get("snowflake_graph_edge_count")
            ),
            "mdm_minus_graph": _int_value(row.get("mdm_minus_graph")),
            "graph_minus_mdm": _int_value(row.get("graph_minus_mdm")),
            "status": _parity_status(row),
        }
        for row in rows
        if isinstance(row, dict)
    ]


def _diagnostics_payload(
    payload: dict[str, Any],
    *,
    sample_limit: int,
) -> dict[str, list[dict[str, Any]]]:
    diagnostics = payload.get("diagnostics") or {}
    return {
        "missing_graph_nodes": [
            {
                "entity_type": str(_field(row, "entity_type") or ""),
                "node_id": str(_field(row, "nodeid", "node_id") or ""),
            }
            for row in _bounded_rows(diagnostics.get("missing_graph_nodes"), sample_limit)
        ],
        "extra_graph_nodes": [
            {
                "entity_type": str(_field(row, "entity_type") or ""),
                "node_id": str(_field(row, "nodeid", "node_id") or ""),
            }
            for row in _bounded_rows(diagnostics.get("extra_graph_nodes"), sample_limit)
        ],
        "missing_graph_edges": [
            {
                "relationship_type": str(_field(row, "relationship_type") or ""),
                "edge_id": str(_field(row, "edgeid", "edge_id") or ""),
            }
            for row in _bounded_rows(diagnostics.get("missing_graph_edges"), sample_limit)
        ],
        "extra_graph_edges": [
            {
                "relationship_type": str(_field(row, "relationship_type") or ""),
                "edge_id": str(_field(row, "edgeid", "edge_id") or ""),
            }
            for row in _bounded_rows(diagnostics.get("extra_graph_edges"), sample_limit)
        ],
        "missing_graph_edge_endpoints": [
            _endpoint_row(row)
            for row in _bounded_rows(
                diagnostics.get("missing_graph_edge_endpoints"),
                sample_limit,
            )
        ],
    }


def _endpoint_row(row: dict[str, Any]) -> dict[str, Any]:
    source_node_id = str(_field(row, "sourcenodeid", "source_node_id") or "")
    target_node_id = str(_field(row, "targetnodeid", "target_node_id") or "")
    return {
        "relationship_type": str(_field(row, "relationship_type") or ""),
        "edge_id": str(_field(row, "edgeid", "edge_id") or ""),
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "missing_source_node": bool(_field(row, "missing_source_node")),
        "missing_target_node": bool(_field(row, "missing_target_node")),
        "direction": "source -> target" if source_node_id and target_node_id else "",
    }


def _native_app_payload(value: Any) -> dict[str, Any]:
    native_app = value if isinstance(value, dict) else {}
    checks = [
        check for check in native_app.get("checks", [])
        if isinstance(check, dict)
    ]
    failing_checks = [
        _native_failure_row(check)
        for check in checks
        if str(check.get("status") or "").lower() != "ok"
    ]
    payload = {
        "status": native_app.get("status", "unavailable"),
        "required": bool(native_app.get("required", True)),
        "phase3_acceptance": bool(native_app.get("phase3_acceptance", False)),
        "failing_checks": failing_checks,
    }
    for key in ("app_name", "database_role", "compute_pool"):
        if key in native_app:
            payload[key] = native_app[key]
    return payload


def _native_failure_row(check: dict[str, Any]) -> dict[str, Any]:
    remediation = check.get("remediation") or "Review hosted graph prerequisites."
    return {
        "check": str(check.get("name") or "native_app"),
        "status": str(check.get("status") or "failed"),
        "detail": _native_failure_detail(check),
        "remediation": str(remediation),
    }


def _native_failure_detail(check: dict[str, Any]) -> str:
    if "row_count" in check:
        return f"{_int_value(check.get('row_count'))} row(s) returned."
    return "Check failed before returning rows."


def _unavailable_metrics(exc: Exception) -> SnowflakeGraphDashboardMetrics:
    state, message = _classify_unavailable(exc)
    return SnowflakeGraphDashboardMetrics(
        available=False,
        state=state,
        message=message,
        error_setting_names=SNOWFLAKE_GRAPH_SETTING_NAMES,
        warnings=[
            {
                "severity": "warning",
                "message": message,
                "action": "Confirm Snowflake connection context and Native App grants.",
                "group": "snowflake_graph",
            }
        ],
    )


def _classify_unavailable(exc: Exception) -> tuple[str, str]:
    text = str(exc).lower()
    if any(
        token in text
        for token in (
            "permission",
            "privilege",
            "not authorized",
            "unauthorized",
            "access denied",
            "insufficient",
        )
    ):
        return "permission_denied", SNOWFLAKE_GRAPH_PERMISSION_DENIED_MESSAGE
    if (
        "missing snowflake export setting" in text
        or "target_database is required" in text
        or "snowflake-connector-python is not installed" in text
    ):
        return "missing_config", SNOWFLAKE_GRAPH_UNAVAILABLE_MESSAGE
    return "unavailable", SNOWFLAKE_GRAPH_UNAVAILABLE_MESSAGE


def _field(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        for candidate in (key, key.lower(), key.upper()):
            if candidate in row:
                return row[candidate]
    return None


def _bounded_rows(value: Any, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows = [row for row in value if isinstance(row, dict)]
    return rows[:limit]


def _bounded_sample_limit(value: int) -> int:
    try:
        requested = int(value)
    except (TypeError, ValueError):
        requested = 20
    return max(0, min(requested, 250))


def _parity_status(row: dict[str, Any]) -> str:
    if _int_value(row.get("mdm_minus_graph")) or _int_value(row.get("graph_minus_mdm")):
        return "Mismatch"
    return "OK"


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "SNOWFLAKE_GRAPH_PERMISSION_DENIED_MESSAGE",
    "SNOWFLAKE_GRAPH_UNAVAILABLE_MESSAGE",
    "SnowflakeGraphDashboardMetrics",
    "get_snowflake_graph_metrics",
]

