from edgar_warehouse.mdm.snowflake_graph import (
    SnowflakeGraphMigrationConfig,
    generate_snowflake_graph_migration,
    run_hosted_neo4j_e2e,
    run_snowflake_graph_sql,
)


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
