from edgar_warehouse.mdm.snowflake_graph import (
    SnowflakeGraphSyncConfig,
    SnowflakeGraphSyncExecutor,
    SnowflakeGraphValidationError,
    SnowflakeGraphMigrationConfig,
    generate_snowflake_graph_migration,
    run_hosted_neo4j_e2e,
    run_snowflake_graph_sql,
)


class FakeGraphCursor:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.results: list[tuple[int]] = [(7,), (11,)]
        self.closed = False

    def execute(self, sql: str):
        self.executed.append(sql)
        return self

    def fetchone(self):
        if self.results:
            return self.results.pop(0)
        return (0,)

    def close(self) -> None:
        self.closed = True


class FakeGraphConnection:
    def __init__(self) -> None:
        self.fake_cursor = FakeGraphCursor()

    def cursor(self) -> FakeGraphCursor:
        return self.fake_cursor


def test_generates_snowflake_graph_migration_sql(tmp_path):
    output_dir = tmp_path / "sql"

    files = generate_snowflake_graph_migration(
        SnowflakeGraphMigrationConfig(
            env="dev",
            output_dir=output_dir,
            target_schema="GRAPH_TEST",
            mdm_schema="MDM_TEST",
        )
    )

    assert sorted(files) == [
        "00_graph_tables.sql",
        "01_validation.sql",
        "02_hosted_neo4j_e2e.sql",
        "README.md",
    ]
    graph_sql = (output_dir / "00_graph_tables.sql").read_text(encoding="utf-8")
    validation_sql = (output_dir / "01_validation.sql").read_text(encoding="utf-8")
    hosted_sql = (output_dir / "02_hosted_neo4j_e2e.sql").read_text(encoding="utf-8")
    assert "Neo4j is not external" in graph_sql
    assert "MDM_COMPANY" in graph_sql
    assert "GRAPH_NODES" in graph_sql
    assert "GRAPH_EDGES" in graph_sql
    assert "MDM_RELATIONSHIP_INSTANCE" in validation_sql
    assert "GRAPH_NODE_COMPANY_PAGERANK" in hosted_sql
    assert "Snowflake-Hosted" in (output_dir / "README.md").read_text(encoding="utf-8")


def test_generated_sql_exposes_phase_2_graph_projection_contract(tmp_path):
    output_dir = tmp_path / "sql"

    generate_snowflake_graph_migration(
        SnowflakeGraphMigrationConfig(env="dev", output_dir=output_dir)
    )

    graph_sql = (output_dir / "00_graph_tables.sql").read_text(encoding="utf-8")
    validation_sql = (output_dir / "01_validation.sql").read_text(encoding="utf-8")
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    combined = "\n".join([graph_sql, validation_sql, readme])

    assert "EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION" in graph_sql

    for table_name in [
        "MDM_GRAPH_NODES",
        "MDM_GRAPH_EDGES",
        "GRAPH_NODE_COMPANY",
        "GRAPH_NODE_PERSON",
        "GRAPH_NODE_SECURITY",
        "GRAPH_NODE_ADVISER",
        "GRAPH_NODE_FUND",
        "GRAPH_EDGE_IS_INSIDER",
        "GRAPH_EDGE_HOLDS",
        "GRAPH_EDGE_COMPANY_HOLDS",
        "GRAPH_EDGE_ISSUED_BY",
        "GRAPH_EDGE_IS_ENTITY_OF",
        "GRAPH_EDGE_HAS_PARENT_COMPANY",
        "GRAPH_EDGE_MANAGES_FUND",
        "GRAPH_EDGE_IS_PERSON_OF",
    ]:
        assert table_name in graph_sql

    for column_name in [
        "NODEID",
        "SOURCENODEID",
        "TARGETNODEID",
        "SOURCE_SYSTEM",
        "SOURCE_ACCESSION",
        "SOURCE_UPDATED_AT",
        "CREATED_AT",
        "UPDATED_AT",
        "GRAPH_SYNC_STATUS",
        "GRAPH_SYNCED_AT",
    ]:
        assert column_name in graph_sql

    assert "MDM_ENTITY_TYPE_DEFINITION" in graph_sql
    assert "NEO4J_LABEL" in graph_sql
    assert "IS_QUARANTINED = FALSE" in graph_sql
    assert "RI.IS_ACTIVE = TRUE" in graph_sql
    assert "RT.IS_ACTIVE = TRUE" in graph_sql
    assert "OBJECT_CONSTRUCT_KEEP_NULL" in graph_sql

    assert "active_mdm_relationship_parity" in validation_sql
    assert "missing_graph_edge_endpoints" in validation_sql
    assert "MDM_GRAPH_NODES" in validation_sql
    assert "MDM_GRAPH_EDGES" in validation_sql

    assert "NEO4J_GRAPH_ANALYTICS.GRAPH." in readme
    assert "operator cleanup" in readme.lower()

    for forbidden in [
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
        "NEO4J_DATABASE",
        "NEO4J_SECRET_JSON",
    ]:
        assert forbidden not in combined


def test_run_snowflake_graph_sql_uses_snow_connection(tmp_path, monkeypatch):
    first = tmp_path / "00_graph_tables.sql"
    second = tmp_path / "01_validation.sql"
    readme = tmp_path / "README.md"
    first.write_text("SELECT 1;", encoding="utf-8")
    second.write_text("SELECT 2;", encoding="utf-8")
    readme.write_text("docs", encoding="utf-8")
    calls = []

    def fake_run(cmd, check):
        calls.append((cmd, check))

    monkeypatch.setattr("edgar_warehouse.mdm.snowflake_graph.subprocess.run", fake_run)

    executed = run_snowflake_graph_sql(
        {"README.md": readme, "01_validation.sql": second, "00_graph_tables.sql": first},
        snow_connection="edgartools-dev",
    )

    assert executed == ["00_graph_tables.sql", "01_validation.sql"]
    assert calls == [
        (["snow", "sql", "-c", "edgartools-dev", "-f", str(first)], True),
        (["snow", "sql", "-c", "edgartools-dev", "-f", str(second)], True),
    ]


def test_run_hosted_neo4j_e2e_uses_hosted_validation_only(tmp_path, monkeypatch):
    hosted = tmp_path / "02_hosted_neo4j_e2e.sql"
    hosted.write_text("SELECT 1;", encoding="utf-8")
    calls = []

    def fake_run(cmd, check):
        calls.append((cmd, check))

    monkeypatch.setattr("edgar_warehouse.mdm.snowflake_graph.subprocess.run", fake_run)

    executed = run_hosted_neo4j_e2e(
        {"02_hosted_neo4j_e2e.sql": hosted},
        snow_connection="edgartools-dev",
    )

    assert executed == ["02_hosted_neo4j_e2e.sql"]
    assert calls == [(["snow", "sql", "-c", "edgartools-dev", "-f", str(hosted)], True)]


def test_graph_sync_executor_materializes_filtered_graph_contract_without_credentials():
    connection = FakeGraphConnection()
    executor = SnowflakeGraphSyncExecutor(connection)

    result = executor.sync(
        SnowflakeGraphSyncConfig(
            target_database="EDGARTOOLS_DEV",
            target_schema="NEO4J_GRAPH_MIGRATION",
            mdm_schema="MDM_TEST",
            entity_types=("company", "person"),
            relationship_types=("IS_INSIDER", "HOLDS"),
            limit=100,
            limit_per_type=10,
        )
    )

    cursor = connection.fake_cursor
    combined_sql = "\n".join(cursor.executed)
    assert cursor.closed is True
    assert cursor.executed[0].startswith("-- Build graph-ready node and edge tables")
    assert "CREATE OR REPLACE TABLE EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES" in combined_sql
    assert "CREATE OR REPLACE TABLE EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.MDM_GRAPH_EDGES" in combined_sql
    assert "EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION" in combined_sql
    assert "GRAPH_NODE_COMPANY" in combined_sql
    assert "GRAPH_EDGE_IS_INSIDER" in combined_sql
    assert "NODEID" in combined_sql
    assert "SOURCENODEID" in combined_sql
    assert "TARGETNODEID" in combined_sql
    assert "E.ENTITY_TYPE IN ('company', 'person')" in combined_sql
    assert "RT.REL_TYPE_NAME IN ('HOLDS', 'IS_INSIDER')" in combined_sql
    assert "ROW_NUMBER() OVER (PARTITION BY E.ENTITY_TYPE ORDER BY E.ENTITY_ID) <= 10" in combined_sql
    assert "ROW_NUMBER() OVER (PARTITION BY RT.REL_TYPE_NAME ORDER BY RI.INSTANCE_ID) <= 10" in combined_sql
    assert "LIMIT 100" in combined_sql
    assert result.node_count == 7
    assert result.edge_count == 11
    assert result.target_database == "EDGARTOOLS_DEV"
    assert result.target_schema == "NEO4J_GRAPH_MIGRATION"
    assert result.node_tables == (
        "MDM_GRAPH_NODES",
        "GRAPH_NODE_ADVISER",
        "GRAPH_NODE_AUDITFIRM",
        "GRAPH_NODE_COMPANY",
        "GRAPH_NODE_FUND",
        "GRAPH_NODE_PERSON",
        "GRAPH_NODE_SECURITY",
    )
    assert "GRAPH_EDGE_HOLDS" in result.edge_tables
    assert result.applied_filters == {
        "entity_types": ("company", "person"),
        "relationship_types": ("HOLDS", "IS_INSIDER"),
        "limit": 100,
        "limit_per_type": 10,
    }


def test_graph_sync_executor_rejects_unknown_relationship_before_execute():
    connection = FakeGraphConnection()
    executor = SnowflakeGraphSyncExecutor(connection)

    try:
        executor.sync(
            SnowflakeGraphSyncConfig(
                target_database="EDGARTOOLS_DEV",
                relationship_types=("HODLS",),
            )
        )
    except SnowflakeGraphValidationError as exc:
        message = str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected invalid relationship filter to raise")

    assert "HODLS" in message
    assert "IS_INSIDER" in message
    assert "MANAGES_FUND" in message
    assert connection.fake_cursor.executed == []


def test_graph_sync_executor_rejects_unknown_entity_before_execute():
    connection = FakeGraphConnection()
    executor = SnowflakeGraphSyncExecutor(connection)

    try:
        executor.sync(
            SnowflakeGraphSyncConfig(
                target_database="EDGARTOOLS_DEV",
                entity_types=("companies",),
            )
        )
    except SnowflakeGraphValidationError as exc:
        message = str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected invalid entity filter to raise")

    assert "companies" in message
    assert "company" in message
    assert "security" in message
    assert connection.fake_cursor.executed == []
