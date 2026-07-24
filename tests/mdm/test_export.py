from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.mdm import database as db
from edgar_warehouse.mdm.database import Base
from edgar_warehouse.mdm.export import MDMExporter, SnowflakeConnectorWriter
from edgar_warehouse.mdm.export import SnowflakeConnectionSettings


class FakeWriter:
    """Records upsert calls without touching real Snowflake."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict], str]] = []

    def upsert(self, table: str, rows: list[dict], key: str = "entity_id") -> int:
        self.calls.append((table, rows, key))
        return len(rows)


class FakeCursor:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.batches: list[tuple[str, list[tuple[str, ...]]]] = []
        self.closed = False

    def execute(self, sql: str) -> None:
        self.executed.append(sql)

    def executemany(self, sql: str, values: list[tuple[str, ...]]) -> None:
        self.batches.append((sql, values))

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self) -> None:
        self.fake_cursor = FakeCursor()

    def cursor(self) -> FakeCursor:
        return self.fake_cursor


def test_snowflake_connector_writer_upserts_rows_with_merge_sql():
    connection = FakeConnection()
    writer = SnowflakeConnectorWriter(connection, database="EDGARTOOLS_DEV", schema="MDM")

    count = writer.upsert(
        "MDM_COMPANY",
        [{"entity_id": "company-1", "canonical_name": "Issuer Corp"}],
    )

    cursor = connection.fake_cursor
    assert count == 1
    assert cursor.closed is True
    assert any("CREATE TEMPORARY TABLE" in sql for sql in cursor.executed)
    assert cursor.batches
    merge_sql = cursor.executed[-1]
    assert 'MERGE INTO "EDGARTOOLS_DEV"."MDM"."MDM_COMPANY"' in merge_sql
    assert 'ON target."ENTITY_ID" = source."ENTITY_ID"' in merge_sql


def test_snowflake_connector_writer_multi_row_upsert_keeps_parse_json_out_of_values():
    """PARSE_JSON must live in the SELECT list, not the VALUES clause.

    snowflake-connector-python's executemany rewrites INSERT ... VALUES (...)
    into a multi-row VALUES list, and Snowflake rejects any non-constant
    expression there ("002014 (22000): Invalid expression [PARSE_JSON(...)]
    in VALUES clause"). Hit live by bronze_seed_silver_gold's MdmExport at
    real batch sizes (single-row batches masked it in dev). The supported
    pattern is INSERT ... SELECT PARSE_JSON(columnN) ... FROM VALUES (...).
    """
    connection = FakeConnection()
    writer = SnowflakeConnectorWriter(connection, database="EDGARTOOLS_PROD", schema="MDM")

    count = writer.upsert(
        "MDM_COMPANY",
        [
            {"entity_id": "company-1", "canonical_name": "Issuer Corp"},
            {"entity_id": "company-2", "canonical_name": "Bank 2020 Bnk25"},
        ],
    )

    assert count == 2
    cursor = connection.fake_cursor
    assert len(cursor.batches) == 1
    insert_sql, values = cursor.batches[0]
    values_clause = insert_sql[insert_sql.index("VALUES") :]
    assert "PARSE_JSON" not in values_clause
    assert "SELECT PARSE_JSON(column1), PARSE_JSON(column2)" in insert_sql
    assert "FROM VALUES (%s, %s)" in insert_sql
    assert len(values) == 2
    assert all(len(row) == 2 for row in values)


def test_snowflake_connector_writer_serializes_decimal_values_as_json_numbers():
    connection = FakeConnection()
    writer = SnowflakeConnectorWriter(connection, database="EDGARTOOLS_PROD", schema="MDM")

    count = writer.upsert(
        "MDM_FUND",
        [{"entity_id": "fund-1", "aum_amount": Decimal("1234.50")}],
    )

    assert count == 1
    _, values = connection.fake_cursor.batches[0]
    encoded_values = values[0]
    assert json.loads(encoded_values[0]) == 1234.5
    assert json.loads(encoded_values[1]) == "fund-1"


def test_snowflake_connection_settings_read_mdm_env(monkeypatch):
    for name in list(os.environ):
        if name.startswith("MDM_SNOWFLAKE_") or name.startswith("DBT_SNOWFLAKE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MDM_SNOWFLAKE_ACCOUNT", "acct")
    monkeypatch.setenv("MDM_SNOWFLAKE_USER", "user")
    monkeypatch.setenv("MDM_SNOWFLAKE_PASSWORD", "secret")
    monkeypatch.setenv("MDM_SNOWFLAKE_DATABASE", "EDGARTOOLS_DEV")
    monkeypatch.setenv("MDM_SNOWFLAKE_SCHEMA", "MDM")
    monkeypatch.setenv("MDM_SNOWFLAKE_WAREHOUSE", "LOAD_WH")
    monkeypatch.setenv("MDM_SNOWFLAKE_ROLE", "MDM_LOADER")

    settings = SnowflakeConnectionSettings.from_env()

    assert settings.connection_kwargs() == {
        "account": "acct",
        "user": "user",
        "password": "secret",
        "database": "EDGARTOOLS_DEV",
        "schema": "MDM",
        "warehouse": "LOAD_WH",
        "role": "MDM_LOADER",
    }


def test_snowflake_connection_settings_preserve_dbt_fallbacks(monkeypatch):
    for name in list(os.environ):
        if name.startswith("MDM_SNOWFLAKE_") or name.startswith("DBT_SNOWFLAKE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DBT_SNOWFLAKE_ACCOUNT", "acct")
    monkeypatch.setenv("DBT_SNOWFLAKE_USER", "user")
    monkeypatch.setenv("DBT_SNOWFLAKE_PASSWORD", "secret")
    monkeypatch.setenv("DBT_SNOWFLAKE_DATABASE", "EDGARTOOLS_DEV")
    monkeypatch.setenv("DBT_SNOWFLAKE_WAREHOUSE", "LOAD_WH")

    settings = SnowflakeConnectionSettings.from_env()

    assert settings.database == "EDGARTOOLS_DEV"
    assert settings.schema == "EDGARTOOLS_GOLD"
    assert settings.connection_kwargs()["warehouse"] == "LOAD_WH"


def test_snowflake_connection_settings_read_json_secret(monkeypatch):
    for name in list(os.environ):
        if name.startswith("MDM_SNOWFLAKE_") or name.startswith("DBT_SNOWFLAKE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(
        "MDM_SNOWFLAKE_SECRET_JSON",
        json.dumps(
            {
                "account": "acct",
                "user": "user",
                "password": "secret",
                "database": "EDGARTOOLS_DEV",
                "schema": "MDM",
                "warehouse": "LOAD_WH",
                "role": "MDM_LOADER",
            }
        ),
    )

    settings = SnowflakeConnectionSettings.from_env()

    assert settings.connection_kwargs() == {
        "account": "acct",
        "user": "user",
        "password": "secret",
        "database": "EDGARTOOLS_DEV",
        "schema": "MDM",
        "warehouse": "LOAD_WH",
        "role": "MDM_LOADER",
    }


def test_snowflake_connection_settings_env_overrides_json_secret(monkeypatch):
    for name in list(os.environ):
        if name.startswith("MDM_SNOWFLAKE_") or name.startswith("DBT_SNOWFLAKE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(
        "MDM_SNOWFLAKE_SECRET_JSON",
        json.dumps(
            {
                "account": "secret-acct",
                "user": "user",
                "password": "secret",
                "database": "EDGARTOOLS_DEV",
                "warehouse": "LOAD_WH",
            }
        ),
    )
    monkeypatch.setenv("MDM_SNOWFLAKE_ACCOUNT", "env-acct")

    settings = SnowflakeConnectionSettings.from_env()

    assert settings.account == "env-acct"


def test_snowflake_connection_settings_missing_values_preserve_error_names(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith("MDM_SNOWFLAKE_") or name.startswith("DBT_SNOWFLAKE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    try:
        SnowflakeConnectionSettings.from_env()
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected missing settings to raise")

    assert "MDM_SNOWFLAKE_ACCOUNT or DBT_SNOWFLAKE_ACCOUNT" in message
    assert "MDM_SNOWFLAKE_USER or DBT_SNOWFLAKE_USER" in message
    assert "MDM_SNOWFLAKE_PASSWORD or DBT_SNOWFLAKE_PASSWORD" in message
    assert "MDM_SNOWFLAKE_DATABASE or DBT_SNOWFLAKE_DATABASE" in message
    assert "MDM_SNOWFLAKE_WAREHOUSE or DBT_SNOWFLAKE_WAREHOUSE" in message
    assert "NEO4J_" not in message


# ---------------------------------------------------------------------------
# MDMExporter mirror tests: keeping the sync-graph-source MDM schema mirror
# current. Before this, nothing refreshed EDGARTOOLS_PROD.MDM after its
# one-time bootstrap load, so sync-graph silently read a frozen snapshot.
# ---------------------------------------------------------------------------

@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sess = Session(engine)
    yield sess
    sess.close()


def test_export_pending_mirrors_entity_and_change_log_when_mirror_writer_provided(session):
    entity_id = str(uuid.uuid4())
    session.add(db.MdmEntity(entity_id=entity_id, entity_type="company"))
    session.add(db.MdmCompany(entity_id=entity_id, cik=1, canonical_name="Issuer Corp"))
    session.commit()
    session.add(db.MdmChangeLog(entity_id=entity_id, entity_type="company", changed_fields={"cik": 1}))
    session.commit()

    domain_writer = FakeWriter()
    mirror_writer = FakeWriter()
    exporter = MDMExporter(session=session, writer=domain_writer, mirror_writer=mirror_writer)

    total = exporter.export_pending()

    assert total == 1
    domain_tables = {call[0] for call in domain_writer.calls}
    assert domain_tables == {"MDM_COMPANY"}
    mirror_tables = {call[0] for call in mirror_writer.calls}
    assert mirror_tables == {"MDM_ENTITY", "MDM_CHANGE_LOG"}
    entity_call = next(call for call in mirror_writer.calls if call[0] == "MDM_ENTITY")
    assert entity_call[2] == "entity_id"
    assert entity_call[1][0]["entity_id"] == entity_id
    change_log_call = next(call for call in mirror_writer.calls if call[0] == "MDM_CHANGE_LOG")
    assert change_log_call[2] == "change_id"


def test_export_pending_skips_mirror_when_mirror_writer_is_none(session):
    entity_id = str(uuid.uuid4())
    session.add(db.MdmEntity(entity_id=entity_id, entity_type="company"))
    session.add(db.MdmCompany(entity_id=entity_id, cik=1, canonical_name="Issuer Corp"))
    session.commit()
    session.add(db.MdmChangeLog(entity_id=entity_id, entity_type="company", changed_fields={"cik": 1}))
    session.commit()

    domain_writer = FakeWriter()
    exporter = MDMExporter(session=session, writer=domain_writer)

    total = exporter.export_pending()

    assert total == 1
    assert {call[0] for call in domain_writer.calls} == {"MDM_COMPANY"}


def test_export_all_pending_drains_every_entity_batch(session):
    for index in range(5):
        entity_id = str(uuid.uuid4())
        session.add(db.MdmEntity(entity_id=entity_id, entity_type="company"))
        session.add(db.MdmCompany(
            entity_id=entity_id,
            cik=1000 + index,
            canonical_name=f"Issuer {index}",
        ))
        session.add(db.MdmChangeLog(
            entity_id=entity_id,
            entity_type="company",
            changed_fields={"cik": 1000 + index},
        ))
    session.commit()

    writer = FakeWriter()
    exporter = MDMExporter(session=session, writer=writer)

    total = exporter.export_all_pending(batch_size=2)

    assert total == 5
    assert [len(rows) for table, rows, _key in writer.calls if table == "MDM_COMPANY"] == [2, 2, 1]
    assert session.query(db.MdmChangeLog).filter(
        db.MdmChangeLog.exported_at.is_(None)
    ).count() == 0


def test_export_pending_relationships_mirrors_and_stamps_graph_synced_at(session):
    rel_type_id = str(uuid.uuid4())
    session.add(db.MdmRelationshipType(
        rel_type_id=rel_type_id, rel_type_name="MANAGES_FUND",
        source_node_type="adviser", target_node_type="fund",
        direction="outbound", is_temporal=True, merge_strategy="extend_temporal", is_active=True,
    ))
    adviser_id = str(uuid.uuid4())
    fund_id = str(uuid.uuid4())
    session.add(db.MdmEntity(entity_id=adviser_id, entity_type="adviser"))
    session.add(db.MdmEntity(entity_id=fund_id, entity_type="fund"))
    session.commit()
    instance_id = str(uuid.uuid4())
    session.add(db.MdmRelationshipInstance(
        instance_id=instance_id, rel_type_id=rel_type_id,
        source_entity_id=adviser_id, target_entity_id=fund_id,
        source_system="test", is_active=True,
    ))
    session.commit()

    mirror_writer = FakeWriter()
    exporter = MDMExporter(session=session, writer=FakeWriter(), mirror_writer=mirror_writer)

    total = exporter.export_pending_relationships()

    assert total == 1
    assert mirror_writer.calls[0][0] == "MDM_RELATIONSHIP_INSTANCE"
    assert mirror_writer.calls[0][2] == "instance_id"
    refreshed = session.get(db.MdmRelationshipInstance, instance_id)
    assert refreshed.graph_synced_at is not None

    # A second call should find nothing pending -- graph_synced_at excludes it now.
    mirror_writer_2 = FakeWriter()
    exporter_2 = MDMExporter(session=session, writer=FakeWriter(), mirror_writer=mirror_writer_2)
    assert exporter_2.export_pending_relationships() == 0
    assert mirror_writer_2.calls == []


def test_export_pending_relationships_returns_zero_without_mirror_writer(session):
    exporter = MDMExporter(session=session, writer=FakeWriter())
    assert exporter.export_pending_relationships() == 0


def test_export_all_pending_relationships_drains_every_batch(session):
    rel_type_id = str(uuid.uuid4())
    session.add(db.MdmRelationshipType(
        rel_type_id=rel_type_id,
        rel_type_name="MANAGES_FUND",
        source_node_type="adviser",
        target_node_type="fund",
        direction="outbound",
        is_temporal=True,
        merge_strategy="extend_temporal",
        is_active=True,
    ))
    for _index in range(5):
        adviser_id = str(uuid.uuid4())
        fund_id = str(uuid.uuid4())
        session.add(db.MdmEntity(entity_id=adviser_id, entity_type="adviser"))
        session.add(db.MdmEntity(entity_id=fund_id, entity_type="fund"))
        session.add(db.MdmRelationshipInstance(
            instance_id=str(uuid.uuid4()),
            rel_type_id=rel_type_id,
            source_entity_id=adviser_id,
            target_entity_id=fund_id,
            source_system="test",
            is_active=True,
        ))
    session.commit()

    writer = FakeWriter()
    exporter = MDMExporter(
        session=session,
        writer=FakeWriter(),
        mirror_writer=writer,
    )

    total = exporter.export_all_pending_relationships(batch_size=2)

    assert total == 5
    assert [
        len(rows)
        for table, rows, _key in writer.calls
        if table == "MDM_RELATIONSHIP_INSTANCE"
    ] == [2, 2, 1]
    assert session.query(db.MdmRelationshipInstance).filter(
        db.MdmRelationshipInstance.graph_synced_at.is_(None)
    ).count() == 0


def test_sync_reference_tables_upserts_entity_type_definitions_and_relationship_types(session):
    session.add(db.MdmEntityTypeDefinition(
        entity_type="company", neo4j_label="Company", domain_table="mdm_company",
        api_path_prefix="/companies", primary_id_field="entity_id",
        display_name="Company", is_active=True,
    ))
    session.add(db.MdmRelationshipType(
        rel_type_id=str(uuid.uuid4()), rel_type_name="MANAGES_FUND",
        source_node_type="adviser", target_node_type="fund",
        direction="outbound", is_temporal=True, merge_strategy="extend_temporal", is_active=True,
    ))
    session.commit()

    mirror_writer = FakeWriter()
    exporter = MDMExporter(session=session, writer=FakeWriter(), mirror_writer=mirror_writer)

    total = exporter.sync_reference_tables()

    assert total == 2
    tables_and_keys = {(call[0], call[2]) for call in mirror_writer.calls}
    assert tables_and_keys == {
        ("MDM_ENTITY_TYPE_DEFINITION", "entity_type"),
        ("MDM_RELATIONSHIP_TYPE", "rel_type_id"),
    }


def test_sync_reference_tables_returns_zero_without_mirror_writer(session):
    exporter = MDMExporter(session=session, writer=FakeWriter())
    assert exporter.sync_reference_tables() == 0
