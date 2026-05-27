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
    "DBT_SNOWFLAKE_ACCOUNT",
    "DBT_SNOWFLAKE_USER",
    "DBT_SNOWFLAKE_PASSWORD",
    "DBT_SNOWFLAKE_DATABASE",
    "DBT_SNOWFLAKE_SCHEMA",
    "DBT_SNOWFLAKE_WAREHOUSE",
    "DBT_SNOWFLAKE_ROLE",
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


def _patch_load_relationships_dependencies(monkeypatch) -> FakeSession:
    import edgar_warehouse.mdm.cli as mdm_cli

    session = FakeSession()
    monkeypatch.setattr(mdm_cli, "_require_silver_reader", lambda required, command: (object(), 0))
    monkeypatch.setattr(mdm_cli, "_session", lambda: session)
    monkeypatch.setattr("edgar_warehouse.mdm.pipeline.MDMPipeline", FakePipeline)
    return session


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
