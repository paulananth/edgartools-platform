from pathlib import Path

from edgar_warehouse.mdm.snowflake_graph import (
    NODE_TABLES,
    EDGE_TABLES,
    SnowflakeGraphSyncConfig,
    SnowflakeGraphSyncExecutor,
    SnowflakeGraphValidationError,
    SnowflakeGraphMigrationConfig,
    SnowflakeGraphVerificationConfig,
    SnowflakeGraphVerifier,
    _fq,
    _graph_context,
    _split_sql_statements,
    generate_snowflake_graph_migration,
    render_graph_tables,
    run_hosted_neo4j_e2e,
    run_snowflake_graph_sql,
    _render_native_app_bfs,
    _render_native_app_graph_info,
    _render_native_app_list_graphs,
    _render_native_app_sample_node,
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
            generation_id="11111111-1111-1111-1111-111111111111",
        )
    )

    cursor = connection.fake_cursor
    combined_sql = "\n".join(cursor.executed)
    assert cursor.closed is True
    assert cursor.executed[0].startswith("-- Build graph-ready node and edge tables")
    assert len(cursor.executed) > 3
    # 07-05: additive publish -- no blanket CREATE OR REPLACE TABLE for staged rows.
    assert "CREATE OR REPLACE TABLE" not in combined_sql
    assert "CREATE TABLE IF NOT EXISTS EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES" in combined_sql
    assert "CREATE TABLE IF NOT EXISTS EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.MDM_GRAPH_EDGES" in combined_sql
    assert "INSERT INTO EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES" in combined_sql
    assert "INSERT INTO EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.MDM_GRAPH_EDGES" in combined_sql
    assert "'11111111-1111-1111-1111-111111111111'" in combined_sql
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
        "generation_id": "11111111-1111-1111-1111-111111111111",
    }


def test_graph_sync_executor_requires_generation_id():
    connection = FakeGraphConnection()
    executor = SnowflakeGraphSyncExecutor(connection)

    try:
        executor.sync(SnowflakeGraphSyncConfig(target_database="EDGARTOOLS_DEV"))
    except SnowflakeGraphValidationError as exc:
        assert "generation_id" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected missing generation_id to raise")
    assert connection.fake_cursor.executed == []


def test_graph_sync_is_idempotent_full_rebuild():
    """GVER-03 (sync side, D-04/D-05), updated for 07-05's additive architecture:
    a repeated sync-graph run against the SAME generation_id and unchanged MDM
    state must be a stable no-op, not merely a one-time manual observation.
    Publication is now additive (MERGE the generation row, scoped DELETE+INSERT
    of that generation's staged rows) rather than CREATE OR REPLACE TABLE, so
    idempotency is proven by showing two runs against the same generation_id
    emit byte-identical SQL and stable node/edge counts, and that every
    DELETE/INSERT statement is scoped to that one generation_id (so a re-run
    can never touch another generation's immutable staged rows).
    """
    config = SnowflakeGraphSyncConfig(
        target_database="EDGARTOOLS_DEV",
        target_schema="NEO4J_GRAPH_MIGRATION",
        mdm_schema="MDM_TEST",
        entity_types=("company", "person"),
        relationship_types=("IS_INSIDER", "HOLDS"),
        limit=100,
        limit_per_type=10,
        generation_id="22222222-2222-2222-2222-222222222222",
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

    generation_literal = "'22222222-2222-2222-2222-222222222222'"
    for statement in first_executed + second_executed:
        stripped = statement.strip()
        upper = " ".join(stripped.upper().split())
        is_staged_delete_or_insert = upper.startswith("DELETE FROM") or (
            upper.startswith("INSERT INTO") and ("MDM_GRAPH_NODES" in upper or "MDM_GRAPH_EDGES" in upper)
        )
        if is_staged_delete_or_insert:
            assert generation_literal in stripped, (
                f"DELETE/INSERT into staged rows must be scoped to this sync's generation_id: {stripped[:120]!r}"
            )
        assert "CREATE OR REPLACE TABLE" not in upper, (
            f"07-05: staged tables are additive (CREATE TABLE IF NOT EXISTS), never CREATE OR REPLACE: {stripped[:80]!r}"
        )


def test_graph_sync_different_generations_do_not_collide():
    """A second sync with a DIFFERENT generation_id must not remove or alter
    the first generation's staged rows -- each generation's DELETE/INSERT is
    scoped to its own generation_id literal, never a blanket rebuild."""
    base_kwargs = dict(
        target_database="EDGARTOOLS_DEV",
        target_schema="NEO4J_GRAPH_MIGRATION",
        mdm_schema="MDM_TEST",
    )
    gen_a = SnowflakeGraphSyncConfig(**base_kwargs, generation_id="aaaaaaaa-0000-0000-0000-000000000000")
    gen_b = SnowflakeGraphSyncConfig(**base_kwargs, generation_id="bbbbbbbb-0000-0000-0000-000000000000")

    connection_a = FakeGraphConnection()
    SnowflakeGraphSyncExecutor(connection_a).sync(gen_a)
    sql_a = "\n".join(connection_a.fake_cursor.executed)

    connection_b = FakeGraphConnection()
    SnowflakeGraphSyncExecutor(connection_b).sync(gen_b)
    sql_b = "\n".join(connection_b.fake_cursor.executed)

    assert "'aaaaaaaa-0000-0000-0000-000000000000'" in sql_a
    assert "'bbbbbbbb-0000-0000-0000-000000000000'" not in sql_a
    assert "'bbbbbbbb-0000-0000-0000-000000000000'" in sql_b
    assert "'aaaaaaaa-0000-0000-0000-000000000000'" not in sql_b


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


def test_native_app_bfs_sample_is_scoped_to_active_graph_view():
    context = {
        "target_database": "EDGARTOOLS_PROD",
        "target_schema": "NEO4J_GRAPH_MIGRATION",
    }

    sql = _render_native_app_sample_node(context)

    assert "GRAPH_APP_NODES" in sql
    assert "MDM_GRAPH_NODES" not in sql


def test_split_sql_statements_preserves_semicolon_inside_string_literal():
    statements = _split_sql_statements("SELECT 'a;b' AS value; SELECT 'c'';d' AS value;")

    assert statements == ["SELECT 'a;b' AS value;", "SELECT 'c'';d' AS value;"]


def test_split_sql_statements_ignores_semicolon_inside_line_comment():
    sql = (
        "-- never CREATE OR REPLACE);\n"
        "-- platform-owned discovery/lifecycle registry;\n"
        "CREATE TABLE foo (id STRING);\n"
        "SELECT 1;\n"
    )

    statements = _split_sql_statements(sql)

    assert len(statements) == 2
    assert statements[0].endswith("CREATE TABLE foo (id STRING);")
    assert statements[1] == "SELECT 1;"


def test_render_graph_tables_header_comment_does_not_produce_empty_statements():
    context = _graph_context(
        target_database="EDGARTOOLS_DEV",
        target_schema="NEO4J_GRAPH_MIGRATION",
        mdm_database="EDGARTOOLS_DEV_MDM",
        mdm_schema="PUBLIC",
    )

    statements = _split_sql_statements(render_graph_tables(context))

    for statement in statements:
        code_lines = [
            line
            for line in statement.splitlines()
            if line.strip() and not line.strip().startswith("--")
        ]
        assert code_lines, f"statement has no executable SQL content: {statement!r}"


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


# -- 07-05 Task 1: additive generation registry + active pointer -------------


def _context(**overrides):
    kwargs = dict(
        target_database="EDGARTOOLS_DEV",
        target_schema="NEO4J_GRAPH_MIGRATION",
        mdm_database="EDGARTOOLS_DEV",
        mdm_schema="MDM",
        generation_id="cccccccc-0000-0000-0000-000000000000",
    )
    kwargs.update(overrides)
    return _graph_context(**kwargs)


def test_generation_registry_and_active_pointer_tables_are_additive():
    graph_sql = render_graph_tables(_context())

    assert "CREATE TABLE IF NOT EXISTS EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_GENERATION" in graph_sql
    assert "CREATE TABLE IF NOT EXISTS EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER" in graph_sql
    assert "MERGE INTO EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_GENERATION" in graph_sql
    assert "'cccccccc-0000-0000-0000-000000000000'" in graph_sql
    assert "CREATE OR REPLACE TABLE" not in graph_sql


def test_every_stable_view_resolves_through_the_single_active_pointer():
    graph_sql = render_graph_tables(_context())
    active_pointer_subquery = (
        "(SELECT ACTIVE_GENERATION_ID FROM EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER "
        "WHERE POINTER_ID = 'active')"
    )
    assert active_pointer_subquery in graph_sql

    stable_view_names = [
        name for name in NODE_TABLES + EDGE_TABLES
        if name not in ("MDM_GRAPH_NODES", "MDM_GRAPH_EDGES")
    ]
    assert stable_view_names, "expected at least one stable view name to check"
    for view_name in stable_view_names:
        marker = f"CREATE OR REPLACE VIEW EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.{view_name} AS"
        assert marker in graph_sql, f"{view_name} view definition not found"
        start = graph_sql.index(marker)
        end = graph_sql.index(";", start)
        view_body = graph_sql[start:end]
        assert active_pointer_subquery in view_body, (
            f"{view_name} does not resolve through the single active-generation pointer"
        )


def test_node_and_edge_rows_are_generation_tagged_not_mixed():
    graph_sql = render_graph_tables(_context())

    nodes_insert_start = graph_sql.index("INSERT INTO EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES")
    nodes_insert_end = graph_sql.index(";", nodes_insert_start)
    assert "GENERATION_ID" in graph_sql[nodes_insert_start:nodes_insert_end]
    assert "'cccccccc-0000-0000-0000-000000000000' AS GENERATION_ID" in graph_sql[nodes_insert_start:nodes_insert_end]

    edges_insert_start = graph_sql.index("INSERT INTO EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.MDM_GRAPH_EDGES")
    edges_insert_end = graph_sql.index(";", edges_insert_start)
    assert "'cccccccc-0000-0000-0000-000000000000' AS GENERATION_ID" in graph_sql[edges_insert_start:edges_insert_end]

    # Each publish is scoped by a DELETE ... WHERE GENERATION_ID = <this generation> --
    # never a blanket delete that could cross-contaminate another generation.
    assert (
        "DELETE FROM EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES "
        "WHERE GENERATION_ID = 'cccccccc-0000-0000-0000-000000000000'"
    ) in graph_sql
    assert (
        "DELETE FROM EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.MDM_GRAPH_EDGES "
        "WHERE GENERATION_ID = 'cccccccc-0000-0000-0000-000000000000'"
    ) in graph_sql


def test_staged_edges_carry_new_temporal_and_lineage_columns():
    graph_sql = render_graph_tables(_context())

    for column in (
        "RELATIONSHIP_ID",
        "VALID_FROM_DATE",
        "VALID_TO_DATE",
        "DATE_PROVENANCE",
        "RELATIONSHIP_KIND",
        "SOURCENODEID_ORIGINAL",
        "TARGETNODEID_ORIGINAL",
    ):
        assert column in graph_sql

    assert "GRAPH_ENTITY_MERGE_LINEAGE" in graph_sql
    assert "CHANGED_FIELDS:merged_from" in graph_sql


def test_existing_view_names_remain_available_to_native_app_consumers():
    graph_sql = render_graph_tables(_context())
    for table_name in NODE_TABLES + EDGE_TABLES:
        assert table_name in graph_sql


def test_verify_functions_accept_an_explicit_generation_id_for_pre_activation_checks():
    context = _context()
    node_sql = _render_verify_node_counts(context, "dddddddd-0000-0000-0000-000000000000")
    assert "'dddddddd-0000-0000-0000-000000000000'" in node_sql
    # backward-compatible default: no generation_id -> verify the active generation
    default_sql = _render_verify_node_counts(context)
    assert "GRAPH_ACTIVE_POINTER" in default_sql


# -- 07-05 Task 2: exact identity/property parity (not count-only) -----------


class _FakeVerifyCursor:
    """Routes canned rows by matching the leading `-- verify_graph:<name>`
    comment each renderer emits, so a single fake can drive verify()'s full
    sequence of distinct queries without caring about exact SQL text."""

    def __init__(self, responses: dict[str, list[tuple]]) -> None:
        self.responses = responses
        self.executed: list[str] = []
        self.closed = False
        self._pending: list[tuple] = []

    def execute(self, sql: str):
        self.executed.append(sql)
        marker = next((key for key in self.responses if key in sql), None)
        self._pending = list(self.responses.get(marker, [])) if marker else []
        return self

    def fetchall(self):
        return self._pending

    def fetchone(self):
        return self._pending[0] if self._pending else (0,)

    def close(self) -> None:
        self.closed = True


class _FakeVerifyConnection:
    def __init__(self, responses: dict[str, list[tuple]]) -> None:
        self.fake_cursor = _FakeVerifyCursor(responses)

    def cursor(self) -> _FakeVerifyCursor:
        return self.fake_cursor


def _base_verify_responses(*, matching_hash: bool) -> dict[str, list[tuple]]:
    hash_a, hash_b = "HASH_A", "HASH_A" if matching_hash else "HASH_B"
    node_rows = [
        (entity_type, 1, 1, 0, 0)
        for entity_type in ("adviser", "audit_firm", "company", "fund", "person", "security")
    ]
    relationship_rows = [
        (rel_type, 1, 1, 0, 0)
        for rel_type in ("COMPANY_HOLDS", "HOLDS", "ISSUED_BY", "IS_INSIDER")
    ]
    return {
        "verify_graph:node_counts": node_rows,
        "verify_graph:relationship_counts": relationship_rows,
        "verify_graph:missing_nodes": [],
        "verify_graph:extra_nodes": [],
        "verify_graph:missing_edges": [],
        "verify_graph:extra_edges": [],
        "verify_graph:missing_edge_endpoints": [],
        "verify_graph:exact_node_parity": [(hash_a, hash_b, 5, 5, matching_hash)],
        "verify_graph:exact_relationship_parity": [(hash_a, hash_b, 3, 3, matching_hash)],
        "verify_graph:canonical_remap_leaks": [],
    }


def test_verify_passes_exact_parity_when_counts_and_content_hashes_both_match():
    connection = _FakeVerifyConnection(_base_verify_responses(matching_hash=True))
    verifier = SnowflakeGraphVerifier(connection)

    result = verifier.verify(
        SnowflakeGraphVerificationConfig(target_database="EDGARTOOLS_DEV", verify_native_app=False)
    )

    assert result.passed is True
    assert result.payload["exact_parity"]["status"] == "ok"


def test_verify_fails_exact_parity_when_counts_match_but_content_hash_differs():
    """RSYNC-02 acceptance criterion: a matching count with a different edge
    identity or property must fail verification -- count-only checks alone
    (node_parity/relationship_parity, both 'ok' here since counts match)
    cannot catch this; only the HASH_AGG-based exact_parity check can."""
    connection = _FakeVerifyConnection(_base_verify_responses(matching_hash=False))
    verifier = SnowflakeGraphVerifier(connection)

    result = verifier.verify(
        SnowflakeGraphVerificationConfig(target_database="EDGARTOOLS_DEV", verify_native_app=False)
    )

    assert result.payload["node_parity"]["status"] == "ok"
    assert result.payload["relationship_parity"]["status"] == "ok"
    assert result.payload["exact_parity"]["status"] == "failed"
    assert result.passed is False


def test_verify_fails_exact_parity_when_a_discarded_entity_still_appears_as_a_canonical_endpoint():
    responses = _base_verify_responses(matching_hash=True)
    responses["verify_graph:canonical_remap_leaks"] = [
        ("edge-1", "IS_INSIDER", "discarded-entity-id", "company-1"),
    ]
    connection = _FakeVerifyConnection(responses)
    verifier = SnowflakeGraphVerifier(connection)

    result = verifier.verify(
        SnowflakeGraphVerificationConfig(target_database="EDGARTOOLS_DEV", verify_native_app=False)
    )

    assert result.passed is False
    assert result.payload["exact_parity"]["status"] == "failed"
    assert result.payload["exact_parity"]["canonical_remap_leaks"]


# -- 07-05 Task 2: guarded activation / rollback / retention -----------------

from edgar_warehouse.mdm.snowflake_graph import (  # noqa: E402
    SnowflakeGraphActivationError,
    activate_graph_generation,
    cleanup_retired_generations,
    render_cleanup_candidates,
    rollback_graph_generation,
)


class _FakeActivationCursor:
    def __init__(self, *, generation_status: dict[str, str], active_generation_id: str | None,
                 cleanup_candidates: list[tuple] | None = None) -> None:
        self.generation_status = generation_status
        self.active_generation_id = active_generation_id
        self.cleanup_candidates = cleanup_candidates or []
        self.executed: list[str] = []
        self.closed = False
        self._pending: list[tuple] = []

    def execute(self, sql: str):
        self.executed.append(sql)
        upper = " ".join(sql.upper().split())
        if upper.startswith("SELECT STATUS FROM"):
            for generation_id, status in self.generation_status.items():
                if f"'{generation_id}'".upper() in upper:
                    self._pending = [(status,)]
                    break
            else:
                self._pending = []
        elif "GRAPH_ACTIVE_POINTER WHERE POINTER_ID = 'ACTIVE'" in upper:
            self._pending = [(self.active_generation_id,)] if self.active_generation_id else []
        elif "VERIFY_GRAPH:CLEANUP_CANDIDATES" in sql.upper() or "RECENCY_RANK" in upper:
            self._pending = list(self.cleanup_candidates)
        else:
            self._pending = []
        return self

    def fetchall(self):
        return self._pending

    def close(self) -> None:
        self.closed = True


class _FakeActivationConnection:
    def __init__(self, **kwargs) -> None:
        self.fake_cursor = _FakeActivationCursor(**kwargs)

    def cursor(self) -> _FakeActivationCursor:
        return self.fake_cursor


def test_activation_flips_pointer_only_when_generation_is_verified():
    connection = _FakeActivationConnection(
        generation_status={"gen-new": "verified"},
        active_generation_id="gen-old",
    )

    result = activate_graph_generation(
        connection, target_database="EDGARTOOLS_DEV", generation_id="gen-new"
    )

    assert result.generation_id == "gen-new"
    assert result.previous_generation_id == "gen-old"
    combined = "\n".join(connection.fake_cursor.executed)
    assert "MERGE INTO EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER" in combined
    assert "'gen-new'" in combined


def test_activation_refuses_unverified_generation_and_leaves_pointer_untouched():
    connection = _FakeActivationConnection(
        generation_status={"gen-building": "building"},
        active_generation_id="gen-old",
    )

    try:
        activate_graph_generation(
            connection, target_database="EDGARTOOLS_DEV", generation_id="gen-building"
        )
    except SnowflakeGraphActivationError as exc:
        assert "gen-building" in str(exc)
        assert "building" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected activation of an unverified generation to raise")

    # Only the guard SELECT ran -- no MERGE/UPDATE ever touched the pointer.
    combined = "\n".join(connection.fake_cursor.executed)
    assert "MERGE" not in combined.upper()
    assert "UPDATE" not in combined.upper()


def test_activation_refuses_unknown_generation_id():
    connection = _FakeActivationConnection(generation_status={}, active_generation_id="gen-old")

    try:
        activate_graph_generation(
            connection, target_database="EDGARTOOLS_DEV", generation_id="does-not-exist"
        )
    except SnowflakeGraphActivationError as exc:
        assert "does-not-exist" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected activation of an unknown generation to raise")
    assert "MERGE" not in "\n".join(connection.fake_cursor.executed).upper()


def test_rollback_accepts_a_retired_generation_but_refuses_a_failed_one():
    connection = _FakeActivationConnection(
        generation_status={"gen-retired": "retired"},
        active_generation_id="gen-current",
    )
    result = rollback_graph_generation(
        connection, target_database="EDGARTOOLS_DEV", generation_id="gen-retired"
    )
    assert result.previous_generation_id == "gen-current"

    failed_connection = _FakeActivationConnection(
        generation_status={"gen-failed": "failed"},
        active_generation_id="gen-current",
    )
    try:
        rollback_graph_generation(
            failed_connection, target_database="EDGARTOOLS_DEV", generation_id="gen-failed"
        )
    except SnowflakeGraphActivationError as exc:
        assert "failed" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected rollback to a 'failed' generation to raise")


def test_cleanup_deletes_only_generations_outside_the_retention_window():
    connection = _FakeActivationConnection(
        generation_status={},
        active_generation_id="gen-current",
        cleanup_candidates=[("gen-ancient-1",), ("gen-ancient-2",)],
    )

    deleted = cleanup_retired_generations(connection, target_database="EDGARTOOLS_DEV")

    assert deleted == ["gen-ancient-1", "gen-ancient-2"]
    combined = "\n".join(connection.fake_cursor.executed)
    assert "DELETE FROM EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES WHERE GENERATION_ID IN ('gen-ancient-1', 'gen-ancient-2')" in combined
    assert "DELETE FROM EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.MDM_GRAPH_EDGES WHERE GENERATION_ID IN ('gen-ancient-1', 'gen-ancient-2')" in combined
    assert "DELETE FROM EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_GENERATION WHERE GENERATION_ID IN ('gen-ancient-1', 'gen-ancient-2')" in combined


def test_retention_cleanup_candidates_query_keeps_newest_n_and_recent_generations():
    context = {"target_database": "EDGARTOOLS_DEV", "target_schema": "NEO4J_GRAPH_MIGRATION"}
    sql = render_cleanup_candidates(context, min_generations=3, retention_days=30)

    assert "WHERE STATUS = 'retired'" in sql
    assert "RECENCY_RANK > 3" in sql
    assert "DATEADD('day', -30, CURRENT_TIMESTAMP())" in sql


def test_retention_cleanup_with_no_candidates_issues_no_delete():
    connection = _FakeActivationConnection(
        generation_status={}, active_generation_id="gen-current", cleanup_candidates=[]
    )
    deleted = cleanup_retired_generations(connection, target_database="EDGARTOOLS_DEV")
    assert deleted == []
    assert "DELETE" not in "\n".join(connection.fake_cursor.executed).upper()


# -- 07-05: verify() closes the building -> verified/failed loop -------------
#
# activate_graph_generation only accepts status='verified' -- something has
# to actually set that status. Verifying an EXPLICIT candidate generation_id
# (not the default "verify the active one") is that something.


def test_verify_promotes_an_explicit_candidate_generation_to_verified_on_pass():
    connection = _FakeVerifyConnection(_base_verify_responses(matching_hash=True))
    verifier = SnowflakeGraphVerifier(connection)

    result = verifier.verify(
        SnowflakeGraphVerificationConfig(
            target_database="EDGARTOOLS_DEV", verify_native_app=False, generation_id="gen-candidate"
        )
    )

    assert result.passed is True
    combined = "\n".join(connection.fake_cursor.executed)
    assert "SET STATUS = 'verified'" in combined
    assert "'gen-candidate'" in combined
    assert "AND STATUS = 'building'" in combined


def test_verify_marks_an_explicit_candidate_generation_failed_on_parity_mismatch():
    connection = _FakeVerifyConnection(_base_verify_responses(matching_hash=False))
    verifier = SnowflakeGraphVerifier(connection)

    result = verifier.verify(
        SnowflakeGraphVerificationConfig(
            target_database="EDGARTOOLS_DEV", verify_native_app=False, generation_id="gen-candidate"
        )
    )

    assert result.passed is False
    combined = "\n".join(connection.fake_cursor.executed)
    assert "SET STATUS = 'failed'" in combined
    assert "'gen-candidate'" in combined


def test_verify_of_the_default_active_generation_never_touches_generation_status():
    """Without an explicit generation_id, verify() checks the currently-active
    generation -- it must never flip that generation's status (it's already
    'activated', not a 'building' candidate awaiting promotion)."""
    connection = _FakeVerifyConnection(_base_verify_responses(matching_hash=True))
    verifier = SnowflakeGraphVerifier(connection)

    verifier.verify(SnowflakeGraphVerificationConfig(target_database="EDGARTOOLS_DEV", verify_native_app=False))

    combined = "\n".join(connection.fake_cursor.executed).upper()
    assert "SET STATUS" not in combined
