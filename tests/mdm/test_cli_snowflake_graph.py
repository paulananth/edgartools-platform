import json

import pytest

from edgar_warehouse.cli import build_parser
from edgar_warehouse.mdm.snowflake_graph import SnowflakeGraphSyncResult


NEO4J_ENV_VARS = (
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_USERNAME",
    "NEO4J_PASSWORD",
    "NEO4J_DATABASE",
    "NEO4J_SECRET_JSON",
)
SNOWFLAKE_ENV_VARS = (
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


class FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.closed = False

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True


class FakePipeline:
    instances: list["FakePipeline"] = []

    def __init__(self, *, session, silver, neo4j=None) -> None:
        self.session = session
        self.silver = silver
        self.neo4j = neo4j
        self.derive_calls = []
        self.entity_calls = []
        FakePipeline.instances.append(self)

    def run_companies(self, limit=None) -> int:
        self.entity_calls.append(("company", limit))
        return 1

    def run_advisers(self, limit=None) -> int:
        self.entity_calls.append(("adviser", limit))
        return 2

    def run_securities(self, limit=None) -> int:
        self.entity_calls.append(("security", limit))
        return 3

    def run_persons(self, limit=None) -> int:
        self.entity_calls.append(("person", limit))
        return 4

    def run_funds(self, limit=None) -> int:
        self.entity_calls.append(("fund", limit))
        return 5

    def derive_relationships(self, *, target_per_type=None, relationship_types=None):
        self.derive_calls.append(
            {
                "target_per_type": target_per_type,
                "relationship_types": relationship_types,
            }
        )
        return {
            "HOLDS": {
                "existing": 1,
                "inserted": 2,
                "skipped": 0,
                "target": target_per_type,
                "total": 3,
            }
        }


class RecordingSnowflakeExecutor:
    constructed = 0
    configs = []

    @classmethod
    def from_env(cls):
        cls.constructed += 1
        return cls()

    def sync(self, config):
        self.__class__.configs.append(config)
        return SnowflakeGraphSyncResult(
            node_count=7,
            edge_count=11,
            target_database=config.target_database or "EDGARTOOLS_DEV",
            target_schema=config.target_schema,
            node_tables=("MDM_GRAPH_NODES", "GRAPH_NODE_COMPANY"),
            edge_tables=("MDM_GRAPH_EDGES", "GRAPH_EDGE_HOLDS"),
            applied_filters={
                "entity_types": tuple(config.entity_types),
                "relationship_types": tuple(config.relationship_types),
                "limit": config.limit,
                "limit_per_type": config.limit_per_type,
            },
        )


class FakeSnowflakeCursor:
    def __init__(
        self,
        *,
        node_count: int = 0,
        edge_count: int = 0,
        result_sets: dict[str, list[dict[str, object]]] | None = None,
    ) -> None:
        self.node_count = node_count
        self.edge_count = edge_count
        self.result_sets = result_sets or {}
        self.current_sql = ""
        self.executed = []
        self.closed = False

    def execute(self, sql: str):
        self.current_sql = sql
        self.executed.append(sql)
        return self

    def fetchone(self):
        if "MDM_GRAPH_NODES" in self.current_sql:
            return (self.node_count,)
        if "MDM_GRAPH_EDGES" in self.current_sql:
            return (self.edge_count,)
        return (0,)

    def fetchall(self):
        for marker, rows in self.result_sets.items():
            if marker in self.current_sql:
                return rows
        return []

    def close(self) -> None:
        self.closed = True


class FakeSnowflakeConnection:
    def __init__(
        self,
        *,
        node_count: int = 0,
        edge_count: int = 0,
        result_sets: dict[str, list[dict[str, object]]] | None = None,
    ) -> None:
        self.cursor_instance = FakeSnowflakeCursor(
            node_count=node_count,
            edge_count=edge_count,
            result_sets=result_sets,
        )
        self.closed = False

    def cursor(self) -> FakeSnowflakeCursor:
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def reset_fakes():
    FakePipeline.instances.clear()
    RecordingSnowflakeExecutor.constructed = 0
    RecordingSnowflakeExecutor.configs.clear()


def _clear_graph_env(monkeypatch) -> None:
    for name in NEO4J_ENV_VARS + SNOWFLAKE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _patch_executor(monkeypatch) -> None:
    monkeypatch.setattr(
        "edgar_warehouse.mdm.snowflake_graph.SnowflakeGraphSyncExecutor",
        RecordingSnowflakeExecutor,
    )


def _patch_verify_settings(monkeypatch, connection: FakeSnowflakeConnection) -> None:
    class FakeSnowflakeConnectionSettings:
        database = "EDGARTOOLS_DEV"

        @classmethod
        def from_env(cls):
            return cls()

        def connect(self):
            return connection

    monkeypatch.setattr(
        "edgar_warehouse.mdm.export.SnowflakeConnectionSettings",
        FakeSnowflakeConnectionSettings,
    )


def _patch_load_relationships_dependencies(monkeypatch) -> FakeSession:
    import edgar_warehouse.mdm.cli as mdm_cli

    session = FakeSession()
    monkeypatch.setattr(mdm_cli, "_require_silver_reader", lambda required, command: (object(), 0))
    monkeypatch.setattr(mdm_cli, "_session", lambda: session)
    monkeypatch.setattr("edgar_warehouse.mdm.pipeline.MDMPipeline", FakePipeline)
    return session


def _strict_parity_results(
    *,
    node_rows: list[dict[str, object]] | None = None,
    relationship_rows: list[dict[str, object]] | None = None,
    missing_nodes: list[dict[str, object]] | None = None,
    extra_nodes: list[dict[str, object]] | None = None,
    missing_edges: list[dict[str, object]] | None = None,
    extra_edges: list[dict[str, object]] | None = None,
    endpoint_rows: list[dict[str, object]] | None = None,
    include_native_app: bool = True,
    native_app_rows: dict[str, list[dict[str, object]]] | None = None,
) -> dict[str, list[dict[str, object]]]:
    results = {
        "verify_graph:node_counts": node_rows
        or [
            {
                "ENTITY_TYPE": "company",
                "MDM_ACTIVE_COUNT": 2,
                "SNOWFLAKE_GRAPH_NODE_COUNT": 2,
                "MDM_MINUS_GRAPH": 0,
                "GRAPH_MINUS_MDM": 0,
            },
            {
                "ENTITY_TYPE": "person",
                "MDM_ACTIVE_COUNT": 1,
                "SNOWFLAKE_GRAPH_NODE_COUNT": 1,
                "MDM_MINUS_GRAPH": 0,
                "GRAPH_MINUS_MDM": 0,
            },
        ],
        "verify_graph:relationship_counts": relationship_rows
        or [
            {
                "RELATIONSHIP_TYPE": "HOLDS",
                "MDM_ACTIVE_COUNT": 2,
                "SNOWFLAKE_GRAPH_EDGE_COUNT": 2,
                "MDM_MINUS_GRAPH": 0,
                "GRAPH_MINUS_MDM": 0,
            },
            {
                "RELATIONSHIP_TYPE": "IS_INSIDER",
                "MDM_ACTIVE_COUNT": 1,
                "SNOWFLAKE_GRAPH_EDGE_COUNT": 1,
                "MDM_MINUS_GRAPH": 0,
                "GRAPH_MINUS_MDM": 0,
            },
        ],
        "verify_graph:missing_nodes": missing_nodes or [],
        "verify_graph:extra_nodes": extra_nodes or [],
        "verify_graph:missing_edges": missing_edges or [],
        "verify_graph:extra_edges": extra_edges or [],
        "verify_graph:missing_edge_endpoints": endpoint_rows or [],
    }
    if include_native_app:
        results.update(_native_app_success_results())
    if native_app_rows:
        results.update(native_app_rows)
    return results


def _native_app_success_results() -> dict[str, list[dict[str, object]]]:
    return {
        "verify_graph:native_app_installation": [
            {
                "NAME": "NEO4J_GRAPH_ANALYTICS",
                "STATE": "READY",
            }
        ],
        "verify_graph:native_app_app_user_role": [
            {
                "GRANTED_TO": "ROLE",
                "GRANTEE_NAME": "EDGARTOOLS_GRAPH_APP_USER",
            }
        ],
        "verify_graph:native_app_app_admin_role": [
            {
                "GRANTED_TO": "ROLE",
                "GRANTEE_NAME": "EDGARTOOLS_GRAPH_APP_ADMIN",
            }
        ],
        "verify_graph:native_app_application_database_role": [
            {
                "GRANTED_ON": "DATABASE ROLE",
                "NAME": "NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE",
            }
        ],
        "verify_graph:native_app_database_role_privileges": [
            {
                "PRIVILEGE": "USAGE",
                "GRANTED_ON": "DATABASE",
                "NAME": "EDGARTOOLS_DEV",
            },
            {
                "PRIVILEGE": "USAGE",
                "GRANTED_ON": "SCHEMA",
                "NAME": "EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION",
            },
            {
                "PRIVILEGE": "SELECT",
                "GRANTED_ON": "TABLE",
                "NAME": "MDM_GRAPH_NODES",
            },
            {
                "PRIVILEGE": "SELECT",
                "GRANTED_ON": "VIEW",
                "NAME": "GRAPH_NODES",
            },
            {
                "PRIVILEGE": "CREATE TABLE",
                "GRANTED_ON": "SCHEMA",
                "NAME": "EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION",
            },
        ],
        "verify_graph:native_app_compute_pools": [
            {
                "AVAILABLE_COMPUTE_POOLS": '["CPU_X64_XS"]',
            }
        ],
        "verify_graph:native_app_sample_node": [
            {
                "NODEID": "company:1",
            }
        ],
        "verify_graph:native_app_graph_info": [
            {
                "STATUS": "ok",
            }
        ],
        "verify_graph:native_app_bfs": [
            {
                "STATUS": "ok",
            }
        ],
        "verify_graph:native_app_wcc": [
            {
                "STATUS": "ok",
            }
        ],
    }


def test_sync_graph_uses_snowflake_executor_without_neo4j_credentials(monkeypatch, capsys):
    _clear_graph_env(monkeypatch)
    _patch_executor(monkeypatch)

    args = build_parser().parse_args(
        [
            "mdm",
            "sync-graph",
            "--relationship-type",
            "HOLDS",
            "--relationship-type",
            "IS_INSIDER",
            "--entity-type",
            "company",
            "--entity-type",
            "person",
            "--limit",
            "100",
            "--limit-per-type",
            "10",
            "--target-database",
            "EDGARTOOLS_DEV",
            "--target-schema",
            "NEO4J_GRAPH_MIGRATION",
            "--mdm-database",
            "EDGARTOOLS_DEV",
            "--mdm-schema",
            "MDM",
        ]
    )

    assert args.handler(args) == 0

    config = RecordingSnowflakeExecutor.configs[0]
    assert config.relationship_types == ("HOLDS", "IS_INSIDER")
    assert config.entity_types == ("company", "person")
    assert config.limit == 100
    assert config.limit_per_type == 10
    assert config.target_database == "EDGARTOOLS_DEV"
    assert config.target_schema == "NEO4J_GRAPH_MIGRATION"
    assert config.mdm_database == "EDGARTOOLS_DEV"
    assert config.mdm_schema == "MDM"

    payload = json.loads(capsys.readouterr().out)
    assert payload["graph_nodes_materialized"] == 7
    assert payload["graph_edges_materialized"] == 11
    assert payload["target"] == {
        "database": "EDGARTOOLS_DEV",
        "schema": "NEO4J_GRAPH_MIGRATION",
    }
    assert payload["applied_filters"] == {
        "entity_types": ["company", "person"],
        "relationship_types": ["HOLDS", "IS_INSIDER"],
        "limit": 100,
        "limit_per_type": 10,
    }


def test_verify_graph_reports_strict_snowflake_parity(monkeypatch, capsys):
    _clear_graph_env(monkeypatch)
    connection = FakeSnowflakeConnection(result_sets=_strict_parity_results())
    _patch_verify_settings(monkeypatch, connection)

    args = build_parser().parse_args(["mdm", "verify-graph"])

    assert args.handler(args) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["snowflake_graph_nodes"] == 3
    assert payload["snowflake_graph_edges"] == 3
    assert payload["node_parity"]["status"] == "ok"
    assert payload["relationship_parity"]["status"] == "ok"
    assert payload["native_app"]["status"] == "ok"
    assert payload["native_app"]["required"] is True
    assert payload["native_app"]["phase3_acceptance"] is True
    assert [check["name"] for check in payload["native_app"]["checks"]] == [
        "app_installation",
        "app_user_role_grant",
        "app_admin_role_grant",
        "database_role_to_application",
        "database_role_privileges",
        "compute_pool",
        "graph_schema_sample",
        "graph_info",
        "bfs",
        "wcc",
    ]
    assert payload["node_parity"]["by_entity_type"] == [
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
    ]
    assert payload["diagnostics"] == {
        "missing_graph_nodes": [],
        "extra_graph_nodes": [],
        "missing_graph_edges": [],
        "extra_graph_edges": [],
        "missing_graph_edge_endpoints": [],
    }
    assert payload["target"] == {
        "database": "EDGARTOOLS_DEV",
        "schema": "NEO4J_GRAPH_MIGRATION",
    }
    assert connection.cursor_instance.closed is True
    assert connection.closed is True


def test_verify_graph_fails_hard_when_native_app_grant_missing(monkeypatch, capsys):
    _clear_graph_env(monkeypatch)
    _patch_verify_settings(
        monkeypatch,
        FakeSnowflakeConnection(
            result_sets=_strict_parity_results(
                native_app_rows={
                    "verify_graph:native_app_application_database_role": [],
                }
            )
        ),
    )

    args = build_parser().parse_args(["mdm", "verify-graph"])

    assert args.handler(args) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["node_parity"]["status"] == "ok"
    assert payload["relationship_parity"]["status"] == "ok"
    assert payload["native_app"]["status"] == "failed"
    assert payload["native_app"]["phase3_acceptance"] is False
    grant_check = [
        check for check in payload["native_app"]["checks"]
        if check["name"] == "database_role_to_application"
    ][0]
    assert grant_check["status"] == "failed"
    assert "infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql" in grant_check["remediation"]


def test_verify_graph_skip_native_app_is_explicit_offline_only(monkeypatch, capsys):
    _clear_graph_env(monkeypatch)
    connection = FakeSnowflakeConnection(
        result_sets=_strict_parity_results(include_native_app=False)
    )
    _patch_verify_settings(monkeypatch, connection)

    args = build_parser().parse_args(["mdm", "verify-graph", "--skip-native-app"])

    assert args.handler(args) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["native_app"] == {
        "status": "skipped",
        "required": False,
        "phase3_acceptance": False,
        "remediation": "Run without --skip-native-app for live Phase 3 acceptance.",
        "checks": [],
    }
    assert "native_app_" not in "\n".join(connection.cursor_instance.executed)


def test_verify_graph_fails_with_node_mismatch_diagnostics(monkeypatch, capsys):
    _clear_graph_env(monkeypatch)
    _patch_verify_settings(
        monkeypatch,
        FakeSnowflakeConnection(
            result_sets=_strict_parity_results(
                node_rows=[
                    {
                        "ENTITY_TYPE": "company",
                        "MDM_ACTIVE_COUNT": 2,
                        "SNOWFLAKE_GRAPH_NODE_COUNT": 1,
                        "MDM_MINUS_GRAPH": 1,
                        "GRAPH_MINUS_MDM": 0,
                    }
                ],
                missing_nodes=[
                    {
                        "ENTITY_TYPE": "company",
                        "NODEID": "company:missing",
                    }
                ],
            )
        ),
    )

    args = build_parser().parse_args(["mdm", "verify-graph"])

    assert args.handler(args) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["node_parity"]["status"] == "failed"
    assert payload["node_parity"]["by_entity_type"] == [
        {
            "entity_type": "company",
            "mdm_active_count": 2,
            "snowflake_graph_node_count": 1,
            "mdm_minus_graph": 1,
            "graph_minus_mdm": 0,
        }
    ]
    assert payload["diagnostics"]["missing_graph_nodes"] == [
        {
            "entity_type": "company",
            "nodeid": "company:missing",
        }
    ]


def test_verify_graph_fails_with_relationship_and_endpoint_diagnostics(monkeypatch, capsys):
    _clear_graph_env(monkeypatch)
    _patch_verify_settings(
        monkeypatch,
        FakeSnowflakeConnection(
            result_sets=_strict_parity_results(
                relationship_rows=[
                    {
                        "RELATIONSHIP_TYPE": "HOLDS",
                        "MDM_ACTIVE_COUNT": 2,
                        "SNOWFLAKE_GRAPH_EDGE_COUNT": 1,
                        "MDM_MINUS_GRAPH": 1,
                        "GRAPH_MINUS_MDM": 0,
                    }
                ],
                missing_edges=[
                    {
                        "RELATIONSHIP_TYPE": "HOLDS",
                        "EDGEID": "edge:missing",
                    }
                ],
                extra_edges=[
                    {
                        "RELATIONSHIP_TYPE": "HOLDS",
                        "EDGEID": "edge:extra",
                    }
                ],
                endpoint_rows=[
                    {
                        "RELATIONSHIP_TYPE": "HOLDS",
                        "EDGEID": "edge:bad-endpoint",
                        "SOURCENODEID": "person:1",
                        "TARGETNODEID": "security:missing",
                        "MISSING_SOURCE_NODE": False,
                        "MISSING_TARGET_NODE": True,
                    }
                ],
            )
        ),
    )

    args = build_parser().parse_args(["mdm", "verify-graph"])

    assert args.handler(args) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["relationship_parity"]["status"] == "failed"
    assert payload["relationship_parity"]["by_relationship_type"] == [
        {
            "relationship_type": "HOLDS",
            "mdm_active_count": 2,
            "snowflake_graph_edge_count": 1,
            "mdm_minus_graph": 1,
            "graph_minus_mdm": 0,
        }
    ]
    assert payload["diagnostics"]["missing_graph_edges"] == [
        {
            "relationship_type": "HOLDS",
            "edgeid": "edge:missing",
        }
    ]
    assert payload["diagnostics"]["extra_graph_edges"] == [
        {
            "relationship_type": "HOLDS",
            "edgeid": "edge:extra",
        }
    ]
    assert payload["diagnostics"]["missing_graph_edge_endpoints"] == [
        {
            "relationship_type": "HOLDS",
            "edgeid": "edge:bad-endpoint",
            "sourcenodeid": "person:1",
            "targetnodeid": "security:missing",
            "missing_source_node": False,
            "missing_target_node": True,
        }
    ]


def test_load_relationships_default_derives_without_snowflake_credentials(monkeypatch, capsys):
    _clear_graph_env(monkeypatch)
    _patch_executor(monkeypatch)
    session = _patch_load_relationships_dependencies(monkeypatch)

    args = build_parser().parse_args(
        [
            "mdm",
            "load-relationships",
            "--skip-entity-resolution",
            "--relationship-type",
            "HOLDS",
            "--target-per-type",
            "25",
        ]
    )

    assert args.handler(args) == 0

    assert RecordingSnowflakeExecutor.constructed == 0
    assert session.committed is True
    assert session.closed is True
    assert FakePipeline.instances[0].derive_calls == [
        {"target_per_type": 25, "relationship_types": ["HOLDS"]}
    ]
    payload = json.loads(capsys.readouterr().out)
    assert payload["graph_sync"]["enabled"] is False
    assert payload["graph_edges_synced"] == 0
    assert payload["graph_nodes_synced"] == 0


def test_load_relationships_skip_graph_sync_is_no_write_path(monkeypatch, capsys):
    _clear_graph_env(monkeypatch)
    _patch_executor(monkeypatch)
    _patch_load_relationships_dependencies(monkeypatch)

    args = build_parser().parse_args(
        [
            "mdm",
            "load-relationships",
            "--skip-entity-resolution",
            "--skip-graph-sync",
        ]
    )

    assert args.handler(args) == 0

    assert RecordingSnowflakeExecutor.constructed == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["graph_sync"]["enabled"] is False


def test_load_relationships_graph_sync_opt_in_uses_snowflake_executor(monkeypatch, capsys):
    _clear_graph_env(monkeypatch)
    _patch_executor(monkeypatch)
    _patch_load_relationships_dependencies(monkeypatch)

    args = build_parser().parse_args(
        [
            "mdm",
            "load-relationships",
            "--skip-entity-resolution",
            "--graph-sync",
            "--relationship-type",
            "HOLDS",
            "--target-per-type",
            "25",
        ]
    )

    assert args.handler(args) == 0

    assert RecordingSnowflakeExecutor.constructed == 1
    config = RecordingSnowflakeExecutor.configs[0]
    assert config.relationship_types == ("HOLDS",)
    assert config.limit_per_type == 25
    assert config.limit is None
    payload = json.loads(capsys.readouterr().out)
    assert payload["graph_sync"]["enabled"] is True
    assert payload["graph_sync"]["graph_edges_materialized"] == 11
    assert payload["graph_sync"]["target"] == {
        "database": "EDGARTOOLS_DEV",
        "schema": "NEO4J_GRAPH_MIGRATION",
    }
