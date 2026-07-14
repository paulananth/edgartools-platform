from pathlib import Path

from edgar_warehouse.mdm.snowflake_graph import (
    SnowflakeGraphSyncConfig,
    SnowflakeGraphSyncExecutor,
    SnowflakeGraphValidationError,
    SnowflakeGraphMigrationConfig,
    _split_sql_statements,
    generate_snowflake_graph_migration,
    run_hosted_neo4j_e2e,
    run_snowflake_graph_sql,
    _render_native_app_bfs,
    _render_native_app_graph_info,
    _render_native_app_list_graphs,
    _render_verify_node_counts,
)


def _repo_root():
    return Path(__file__).resolve().parents[2]


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


def test_node_parity_preserves_active_zero_count_entity_types():
    validation_sql = _render_verify_node_counts(
        {
            "target_database": "EDGARTOOLS_DEV",
            "target_schema": "NEO4J_GRAPH_MIGRATION",
            "mdm_database": "EDGARTOOLS_DEV",
            "mdm_schema": "MDM",
        }
    )

    assert "SELECT ETD.ENTITY_TYPE, COUNT(E.ENTITY_ID) AS MDM_ACTIVE_COUNT" in validation_sql
    assert "FROM EDGARTOOLS_DEV.MDM.MDM_ENTITY_TYPE_DEFINITION ETD" in validation_sql
    assert "LEFT JOIN EDGARTOOLS_DEV.MDM.MDM_ENTITY E" in validation_sql


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
        "GRAPH_NODE_AUDITFIRM",
        "GRAPH_EDGE_IS_INSIDER",
        "GRAPH_EDGE_HOLDS",
        "GRAPH_EDGE_COMPANY_HOLDS",
        "GRAPH_EDGE_ISSUED_BY",
        "GRAPH_EDGE_IS_ENTITY_OF",
        "GRAPH_EDGE_HAS_PARENT_COMPANY",
        "GRAPH_EDGE_MANAGES_FUND",
        "GRAPH_EDGE_IS_PERSON_OF",
        "GRAPH_EDGE_EMPLOYED_BY",
        "GRAPH_EDGE_AUDITED_BY",
        "GRAPH_EDGE_INSTITUTIONAL_HOLDS",
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

    assert "GRAPH_NODE_AUDITFIRM AS" in graph_sql
    auditfirm_view_start = graph_sql.index("GRAPH_NODE_AUDITFIRM")
    auditfirm_view_sql = graph_sql[auditfirm_view_start : auditfirm_view_start + 400]
    assert "WHERE ENTITY_TYPE = 'audit_firm'" in auditfirm_view_sql

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


def test_neo4j_graph_analytics_app_grants_are_least_privilege():
    sql_path = _repo_root() / "infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql"
    sql = sql_path.read_text(encoding="utf-8")
    normalized = " ".join(sql.upper().split())

    assert "CREATE DATABASE ROLE IF NOT EXISTS NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE" in normalized
    assert "GRANT CREATE COMPUTE POOL ON ACCOUNT TO APPLICATION NEO4J_GRAPH_ANALYTICS" in normalized
    assert "GRANT CREATE WAREHOUSE ON ACCOUNT TO APPLICATION NEO4J_GRAPH_ANALYTICS" in normalized
    assert "USE DATABASE {{ DATABASE }}" in normalized
    assert "GRANT USAGE ON DATABASE {{ DATABASE }} TO DATABASE ROLE NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE" in normalized
    assert (
        "GRANT USAGE ON SCHEMA {{ DATABASE }}.NEO4J_GRAPH_MIGRATION "
        "TO DATABASE ROLE NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE"
    ) in normalized
    assert (
        "GRANT SELECT ON ALL TABLES IN SCHEMA {{ DATABASE }}.NEO4J_GRAPH_MIGRATION "
        "TO DATABASE ROLE NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE"
    ) in normalized
    assert (
        "GRANT SELECT ON ALL VIEWS IN SCHEMA {{ DATABASE }}.NEO4J_GRAPH_MIGRATION "
        "TO DATABASE ROLE NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE"
    ) in normalized
    assert (
        "GRANT SELECT ON FUTURE TABLES IN SCHEMA {{ DATABASE }}.NEO4J_GRAPH_MIGRATION "
        "TO DATABASE ROLE NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE"
    ) in normalized
    assert (
        "GRANT SELECT ON FUTURE VIEWS IN SCHEMA {{ DATABASE }}.NEO4J_GRAPH_MIGRATION "
        "TO DATABASE ROLE NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE"
    ) in normalized
    assert (
        "GRANT CREATE TABLE ON SCHEMA {{ DATABASE }}.NEO4J_GRAPH_MIGRATION "
        "TO DATABASE ROLE NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE"
    ) in normalized
    assert (
        "GRANT DATABASE ROLE NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE "
        "TO APPLICATION NEO4J_GRAPH_ANALYTICS"
    ) in normalized
    assert "GRANT APPLICATION ROLE NEO4J_GRAPH_ANALYTICS.APP_USER TO ROLE EDGARTOOLS_GRAPH_APP_USER" in normalized
    assert "GRANT APPLICATION ROLE NEO4J_GRAPH_ANALYTICS.APP_ADMIN TO ROLE EDGARTOOLS_GRAPH_APP_ADMIN" in normalized

    for forbidden in [
        "ALL PRIVILEGES",
        "GRANT OWNERSHIP",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
        "NEO4J_SECRET_JSON",
    ]:
        assert forbidden not in normalized


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
    assert len(cursor.executed) > 3
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
        "GRAPH_APP_NODES",
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


def test_graph_sync_is_idempotent_full_rebuild():
    """GVER-03 (sync side, D-04/D-05): repeated sync-graph against unchanged MDM
    state must be a stable no-op, not merely a one-time manual observation. The
    graph-sync side rebuilds tables via CREATE OR REPLACE TABLE ... AS SELECT, so
    idempotency is proven by showing two runs emit byte-identical SQL sequences,
    stable node/edge counts, and never issue row-level accumulation verbs
    (INSERT/MERGE/UPDATE/DELETE).
    """
    config = SnowflakeGraphSyncConfig(
        target_database="EDGARTOOLS_DEV",
        target_schema="NEO4J_GRAPH_MIGRATION",
        mdm_schema="MDM_TEST",
        entity_types=("company", "person"),
        relationship_types=("IS_INSIDER", "HOLDS"),
        limit=100,
        limit_per_type=10,
    )

    first_connection = FakeGraphConnection()
    first_executor = SnowflakeGraphSyncExecutor(first_connection)
    first_result = first_executor.sync(config)
    first_executed = list(first_connection.fake_cursor.executed)

    second_connection = FakeGraphConnection()
    second_executor = SnowflakeGraphSyncExecutor(second_connection)
    second_result = second_executor.sync(config)
    second_executed = list(second_connection.fake_cursor.executed)

    assert first_executed == second_executed
    assert first_result.node_count == second_result.node_count
    assert first_result.edge_count == second_result.edge_count

    allowed_leading_verbs = ("CREATE", "SELECT", "--")
    forbidden_verbs = ("INSERT", "MERGE", "UPDATE", "DELETE")
    for statement in first_executed + second_executed:
        stripped = statement.strip()
        upper = stripped.upper()
        assert upper.startswith(allowed_leading_verbs), (
            f"unexpected leading verb in graph-sync statement: {stripped[:80]!r}"
        )
        assert not any(upper.startswith(verb) for verb in forbidden_verbs), (
            f"row-level accumulation verb found in graph-sync statement: {stripped[:80]!r}"
        )


def test_native_app_current_graph_info_bfs_and_list_graphs_sql():
    context = {
        "target_database": "EDGARTOOLS_DEV",
        "target_schema": "NEO4J_GRAPH_MIGRATION",
    }
    graph_info = _render_native_app_graph_info(
        context, "NEO4J_GRAPH_ANALYTICS", "CPU_X64_XS"
    )
    bfs = _render_native_app_bfs(
        context, "NEO4J_GRAPH_ANALYTICS", "CPU_X64_XS", "company:1"
    )
    list_graphs = _render_native_app_list_graphs("NEO4J_GRAPH_ANALYTICS")

    for sql in (graph_info, bfs):
        assert "'CPU_X64_XS'" in sql
        assert "'project':" in sql
        assert "'nodeTables':" in sql
        assert "'relationshipTables':" in sql
        assert "GRAPH_APP_NODES" in sql
        assert "GRAPH_APP_EDGES" in sql
        assert "project_name" not in sql
        assert "compute_pool" not in sql
        assert "node_tables" not in sql
        assert "relationship_tables" not in sql

    assert "'sourceNodeTable':" in bfs
    assert "'sourceNode': 'company:1'" in bfs
    assert "'targetNodesTable':" in bfs
    assert "'targetNodes': []" in bfs
    assert "'maxDepth': 2" in bfs
    assert "'outputTable':" in bfs
    assert "EXPERIMENTAL.LIST_GRAPHS()" in list_graphs


def test_split_sql_statements_preserves_semicolon_inside_string_literal():
    statements = _split_sql_statements("SELECT 'a;b' AS value; SELECT 'c'';d' AS value;")

    assert statements == ["SELECT 'a;b' AS value;", "SELECT 'c'';d' AS value;"]


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
