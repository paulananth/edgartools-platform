from __future__ import annotations

from typing import Any

import pytest

from edgar_warehouse.mdm.snowflake_graph import (
    DEFAULT_MDM_SCHEMA,
    DEFAULT_NATIVE_APP_COMPUTE_POOL,
    DEFAULT_NATIVE_APP_DATABASE_ROLE,
    DEFAULT_NATIVE_APP_NAME,
    DEFAULT_TARGET_SCHEMA,
    SnowflakeGraphVerificationResult,
)


class FakeVerifier:
    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        *,
        passed: bool = True,
        exc: Exception | None = None,
    ) -> None:
        self.payload = payload or _healthy_payload()
        self.passed = passed
        self.exc = exc
        self.configs = []

    def verify(self, config):
        self.configs.append(config)
        if self.exc is not None:
            raise self.exc
        return SnowflakeGraphVerificationResult(
            passed=self.passed,
            payload=self.payload,
        )


def _healthy_payload() -> dict[str, Any]:
    return {
        "status": "ok",
        "snowflake_graph_nodes": 3,
        "snowflake_graph_edges": 2,
        "target": {
            "database": "EDGARTOOLS_DEV",
            "schema": "NEO4J_GRAPH_MIGRATION",
        },
        "node_parity": {
            "status": "ok",
            "total_mdm_active": 3,
            "total_snowflake_graph": 3,
            "by_entity_type": [
                {
                    "entity_type": "company",
                    "mdm_active_count": 2,
                    "snowflake_graph_node_count": 2,
                    "mdm_minus_graph": 0,
                    "graph_minus_mdm": 0,
                },
                {
                    "entity_type": "person",
                    "mdm_active_count": 1,
                    "snowflake_graph_node_count": 1,
                    "mdm_minus_graph": 0,
                    "graph_minus_mdm": 0,
                },
            ],
        },
        "relationship_parity": {
            "status": "ok",
            "total_mdm_active": 2,
            "total_snowflake_graph": 2,
            "by_relationship_type": [
                {
                    "relationship_type": "HOLDS",
                    "mdm_active_count": 2,
                    "snowflake_graph_edge_count": 2,
                    "mdm_minus_graph": 0,
                    "graph_minus_mdm": 0,
                }
            ],
        },
        "diagnostics": {
            "missing_graph_nodes": [],
            "extra_graph_nodes": [],
            "missing_graph_edges": [],
            "extra_graph_edges": [],
            "missing_graph_edge_endpoints": [],
        },
        "native_app": {
            "status": "ok",
            "required": True,
            "phase3_acceptance": True,
            "checks": [
                {"name": "compute_pool", "status": "ok", "row_count": 1},
                {"name": "graph_info", "status": "ok", "row_count": 1},
                {"name": "bfs", "status": "ok", "row_count": 1},
                {"name": "wcc", "status": "ok", "row_count": 1},
            ],
        },
    }


def _failed_payload() -> dict[str, Any]:
    payload = _healthy_payload()
    payload.update(
        {
            "status": "failed",
            "snowflake_graph_nodes": 1,
            "snowflake_graph_edges": 1,
        }
    )
    payload["node_parity"] = {
        "status": "failed",
        "total_mdm_active": 2,
        "total_snowflake_graph": 1,
        "by_entity_type": [
            {
                "entity_type": "company",
                "mdm_active_count": 2,
                "snowflake_graph_node_count": 1,
                "mdm_minus_graph": 1,
                "graph_minus_mdm": 0,
            }
        ],
    }
    payload["relationship_parity"] = {
        "status": "failed",
        "total_mdm_active": 2,
        "total_snowflake_graph": 1,
        "by_relationship_type": [
            {
                "relationship_type": "HOLDS",
                "mdm_active_count": 2,
                "snowflake_graph_edge_count": 1,
                "mdm_minus_graph": 1,
                "graph_minus_mdm": 0,
            }
        ],
    }
    payload["diagnostics"] = {
        "missing_graph_nodes": [
            {"entity_type": "company", "nodeid": "company:missing"},
            {"entity_type": "person", "nodeid": "person:missing"},
        ],
        "extra_graph_nodes": [
            {"entity_type": "company", "nodeid": "company:extra"},
        ],
        "missing_graph_edges": [
            {"relationship_type": "HOLDS", "edgeid": "edge:missing"},
        ],
        "extra_graph_edges": [
            {"relationship_type": "HOLDS", "edgeid": "edge:extra"},
        ],
        "missing_graph_edge_endpoints": [
            {
                "relationship_type": "HOLDS",
                "edgeid": "edge:bad-endpoint",
                "sourcenodeid": "person:1",
                "targetnodeid": "security:missing",
                "missing_source_node": False,
                "missing_target_node": True,
            }
        ],
    }
    payload["native_app"] = {
        "status": "failed",
        "required": True,
        "phase3_acceptance": False,
        "checks": [
            {"name": "compute_pool", "status": "failed", "row_count": 0, "remediation": "Activate compute pool selector CPU_X64_XS."},
            {"name": "graph_info", "status": "failed", "error": "password=secret host example.internal", "remediation": "Confirm GRAPH_INFO can read the graph schema."},
            {"name": "bfs", "status": "ok", "row_count": 1},
            {"name": "wcc", "status": "ok", "row_count": 1},
        ],
    }
    return payload


def test_snowflake_graph_metrics_map_verify_payload_to_dashboard_rows():
    from edgar_warehouse.mdm import graph_readonly

    verifier = FakeVerifier()

    metrics = graph_readonly.get_snowflake_graph_metrics(
        verifier=verifier,
        target_database="EDGARTOOLS_DEV",
        sample_limit=25,
    )
    payload = metrics.as_dict()

    assert payload["available"] is True
    assert payload["state"] == "ok"
    assert payload["message"] == "Snowflake graph metrics loaded."
    assert payload["last_refreshed"]
    assert payload["target"] == {
        "database": "EDGARTOOLS_DEV",
        "schema": "NEO4J_GRAPH_MIGRATION",
    }
    assert payload["snowflake_graph_nodes"] == 3
    assert payload["snowflake_graph_edges"] == 2
    assert payload["entity_comparison"] == [
        {
            "entity_type": "company",
            "mdm_active_count": 2,
            "snowflake_graph_node_count": 2,
            "mdm_minus_graph": 0,
            "graph_minus_mdm": 0,
            "status": "OK",
        },
        {
            "entity_type": "person",
            "mdm_active_count": 1,
            "snowflake_graph_node_count": 1,
            "mdm_minus_graph": 0,
            "graph_minus_mdm": 0,
            "status": "OK",
        },
    ]
    assert payload["relationship_comparison"] == [
        {
            "relationship_type": "HOLDS",
            "mdm_active_count": 2,
            "snowflake_graph_edge_count": 2,
            "mdm_minus_graph": 0,
            "graph_minus_mdm": 0,
            "status": "OK",
        }
    ]
    assert payload["diagnostics"]["missing_graph_nodes"] == []
    assert payload["native_app"]["status"] == "ok"
    assert payload["native_app"]["failing_checks"] == []

    config = verifier.configs[0]
    assert config.target_database == "EDGARTOOLS_DEV"
    assert config.target_schema == DEFAULT_TARGET_SCHEMA
    assert config.mdm_database == "EDGARTOOLS_DEV"
    assert config.mdm_schema == DEFAULT_MDM_SCHEMA
    assert config.sample_limit == 25
    assert config.verify_native_app is True
    assert config.native_app_name == DEFAULT_NATIVE_APP_NAME
    assert config.native_app_database_role == DEFAULT_NATIVE_APP_DATABASE_ROLE
    assert config.native_app_compute_pool == DEFAULT_NATIVE_APP_COMPUTE_POOL


def test_snowflake_graph_metrics_expose_bounded_mismatch_and_native_app_failures():
    from edgar_warehouse.mdm import graph_readonly

    metrics = graph_readonly.get_snowflake_graph_metrics(
        verifier=FakeVerifier(_failed_payload(), passed=False),
        target_database="EDGARTOOLS_DEV",
        sample_limit=1,
    )
    payload = metrics.as_dict()
    rendered = repr(payload)

    assert payload["available"] is True
    assert payload["state"] == "failed"
    assert payload["message"] == "Snowflake graph diagnostics loaded with mismatches."
    assert payload["entity_comparison"][0]["status"] == "Mismatch"
    assert payload["relationship_comparison"][0]["status"] == "Mismatch"
    assert payload["diagnostics"]["missing_graph_nodes"] == [
        {"entity_type": "company", "node_id": "company:missing"}
    ]
    assert payload["diagnostics"]["extra_graph_nodes"] == [
        {"entity_type": "company", "node_id": "company:extra"}
    ]
    assert payload["diagnostics"]["missing_graph_edges"] == [
        {"relationship_type": "HOLDS", "edge_id": "edge:missing"}
    ]
    assert payload["diagnostics"]["extra_graph_edges"] == [
        {"relationship_type": "HOLDS", "edge_id": "edge:extra"}
    ]
    assert payload["diagnostics"]["missing_graph_edge_endpoints"] == [
        {
            "relationship_type": "HOLDS",
            "edge_id": "edge:bad-endpoint",
            "source_node_id": "person:1",
            "target_node_id": "security:missing",
            "missing_source_node": False,
            "missing_target_node": True,
            "direction": "source -> target",
        }
    ]
    assert payload["native_app"]["failing_checks"] == [
        {
            "check": "compute_pool",
            "status": "failed",
            "detail": "0 row(s) returned.",
            "remediation": "Activate compute pool selector CPU_X64_XS.",
        },
        {
            "check": "graph_info",
            "status": "failed",
            "detail": "Check failed before returning rows.",
            "remediation": "Confirm GRAPH_INFO can read the graph schema.",
        },
    ]
    assert "password=secret" not in rendered
    assert "example.internal" not in rendered


def test_snowflake_graph_metrics_missing_configuration_is_secret_safe(monkeypatch):
    from edgar_warehouse.mdm import graph_readonly

    def fail_from_env():
        raise RuntimeError(
            "Missing Snowflake export setting(s): "
            "MDM_SNOWFLAKE_ACCOUNT or DBT_SNOWFLAKE_ACCOUNT"
        )

    monkeypatch.setattr(
        "edgar_warehouse.mdm.graph_readonly.SnowflakeConnectionSettings.from_env",
        fail_from_env,
    )

    payload = graph_readonly.get_snowflake_graph_metrics().as_dict()

    assert payload["available"] is False
    assert payload["state"] == "missing_config"
    assert payload["message"] == graph_readonly.SNOWFLAKE_GRAPH_UNAVAILABLE_MESSAGE
    assert "MDM_SNOWFLAKE_ACCOUNT" in payload["error_setting_names"]
    assert "DBT_SNOWFLAKE_DATABASE" in payload["error_setting_names"]
    assert "Missing Snowflake export setting" not in repr(payload)


def test_snowflake_graph_permission_failure_uses_fixed_safe_copy():
    from edgar_warehouse.mdm import graph_readonly

    metrics = graph_readonly.get_snowflake_graph_metrics(
        verifier=FakeVerifier(
            exc=RuntimeError(
                "Insufficient privileges for user password=secret at example.internal"
            )
        ),
        target_database="EDGARTOOLS_DEV",
    )
    payload = metrics.as_dict()
    rendered = repr(payload)

    assert payload["available"] is False
    assert payload["state"] == "permission_denied"
    assert payload["message"] == graph_readonly.SNOWFLAKE_GRAPH_PERMISSION_DENIED_MESSAGE
    assert "password=secret" not in rendered
    assert "example.internal" not in rendered
    assert "Insufficient privileges" not in rendered


def test_snowflake_graph_helper_does_not_write_or_emit_stdout(capsys):
    from edgar_warehouse.mdm import graph_readonly

    metrics = graph_readonly.get_snowflake_graph_metrics(
        verifier=FakeVerifier(),
        target_database="EDGARTOOLS_DEV",
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert isinstance(metrics.as_dict(), dict)

