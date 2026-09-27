from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.mdm import database as db
from edgar_warehouse.mdm.database import Base
from edgar_warehouse.mdm.export import MDMExporter


class FakeWriter:
    """Records upsert calls without touching real Snowflake."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict], str]] = []

    def upsert(self, table: str, rows: list[dict], key: str = "entity_id") -> int:
        self.calls.append((table, rows, key))
        return len(rows)


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
    session.add(db.MdmChangeLog(
        entity_id=entity_id,
        entity_type="company",
        changed_fields={"cik": 1},
        run_id="entity-export-run",
    ))
    session.commit()

    domain_writer = FakeWriter()
    mirror_writer = FakeWriter()
    exporter = MDMExporter(session=session, writer=domain_writer, mirror_writer=mirror_writer)

    total = exporter.export_pending()

    assert total == 1
    domain_tables = {call[0] for call in domain_writer.calls}
    assert domain_tables == {"MDM_COMPANY_ENTITY"}
    mirror_tables = {call[0] for call in mirror_writer.calls}
    assert mirror_tables == {"MDM_ENTITY", "MDM_CHANGE_LOG"}
    entity_call = next(call for call in mirror_writer.calls if call[0] == "MDM_ENTITY")
    assert entity_call[2] == "entity_id"
    assert entity_call[1][0]["entity_id"] == entity_id
    change_log_call = next(call for call in mirror_writer.calls if call[0] == "MDM_CHANGE_LOG")
    assert change_log_call[2] == "change_id"
    assert change_log_call[1][0]["run_id"] == "entity-export-run"


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
    assert {call[0] for call in domain_writer.calls} == {"MDM_COMPANY_ENTITY"}


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
    assert [len(rows) for table, rows, _key in writer.calls if table == "MDM_COMPANY_ENTITY"] == [2, 2, 1]
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
        source_system="test", is_active=True, run_id="relationship-export-run",
    ))
    session.commit()

    mirror_writer = FakeWriter()
    exporter = MDMExporter(session=session, writer=FakeWriter(), mirror_writer=mirror_writer)

    total = exporter.export_pending_relationships()

    # 2 endpoint entities + 1 relationship instance
    assert total == 3
    tables = [call[0] for call in mirror_writer.calls]
    assert "MDM_ENTITY" in tables
    assert "MDM_RELATIONSHIP_INSTANCE" in tables
    rel_call = next(call for call in mirror_writer.calls if call[0] == "MDM_RELATIONSHIP_INSTANCE")
    assert rel_call[2] == "instance_id"
    assert rel_call[1][0]["run_id"] == "relationship-export-run"
    entity_call = next(call for call in mirror_writer.calls if call[0] == "MDM_ENTITY")
    mirrored_ids = {row["entity_id"] for row in entity_call[1]}
    assert mirrored_ids == {adviser_id, fund_id}
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

    # 5 relationships + 10 distinct endpoint entities (2 per relationship)
    assert total == 15
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


def test_export_active_relationship_endpoints_seals_persons_without_change_log(session):
    """Ticket 20: EMPLOYED_BY edges can export while person stubs never do.

    Proxy person stubs historically skipped mdm_change_log, so identity/property
    hashes still matched (mirror had the edge; MDM entity count excluded the
    person) while missing_graph_edge_endpoints failed. Endpoint seal must push
    person MDM_ENTITY + MDM_PERSON even with graph_synced_at already set and
    no pending change-log row.
    """
    rel_type_id = str(uuid.uuid4())
    session.add(db.MdmRelationshipType(
        rel_type_id=rel_type_id,
        rel_type_name="EMPLOYED_BY",
        source_node_type="person",
        target_node_type="company",
        direction="outbound",
        is_temporal=True,
        merge_strategy="extend_temporal",
        is_active=True,
    ))
    person_id = str(uuid.uuid4())
    company_id = str(uuid.uuid4())
    session.add(db.MdmEntity(entity_id=person_id, entity_type="person"))
    session.add(db.MdmPerson(entity_id=person_id, canonical_name="Jane Executive"))
    session.add(db.MdmEntity(entity_id=company_id, entity_type="company"))
    session.add(db.MdmCompany(entity_id=company_id, cik=320193, canonical_name="Issuer Corp"))
    session.add(db.MdmRelationshipInstance(
        instance_id=str(uuid.uuid4()),
        rel_type_id=rel_type_id,
        source_entity_id=person_id,
        target_entity_id=company_id,
        source_system="proxy_filing",
        is_active=True,
        graph_synced_at=datetime.now(timezone.utc),
    ))
    session.commit()

    domain_writer = FakeWriter()
    mirror_writer = FakeWriter()
    exporter = MDMExporter(session=session, writer=domain_writer, mirror_writer=mirror_writer)

    total = exporter.export_active_relationship_endpoints()

    assert total > 0
    mirror_tables = {call[0] for call in mirror_writer.calls}
    assert "MDM_ENTITY" in mirror_tables
    assert "MDM_PERSON" in mirror_tables
    assert "MDM_COMPANY" in mirror_tables
    entity_call = next(call for call in mirror_writer.calls if call[0] == "MDM_ENTITY")
    assert {row["entity_id"] for row in entity_call[1]} == {person_id, company_id}
    person_call = next(call for call in mirror_writer.calls if call[0] == "MDM_PERSON")
    assert person_call[1][0]["entity_id"] == person_id
    # GOLD writer also receives domain rows for change-log-less stubs.
    assert {call[0] for call in domain_writer.calls} == {"MDM_PERSON", "MDM_COMPANY_ENTITY"}


def test_export_active_relationship_endpoints_returns_zero_without_mirror_writer(session):
    exporter = MDMExporter(session=session, writer=FakeWriter())
    assert exporter.export_active_relationship_endpoints() == 0


def test_company_gold_and_mirror_targets_diverge_by_design(session):
    """Ticket 06 (.scratch/unified-company-dimension/issues/06-*.md): the GOLD
    landing table renamed MDM_COMPANY -> MDM_COMPANY_ENTITY to free the old
    name for a future compat view, but the MDM-schema graph-sync mirror
    (snowflake_graph.py still reads the literal name "MDM_COMPANY") must not
    follow that rename. A future refactor that collapses DOMAIN_TO_TABLE and
    DOMAIN_TO_MIRROR_TABLE back into one name would silently break sync-graph
    without failing here -- same shape as the FakePipeline/issuer_ciks drift.
    """
    rel_type_id = str(uuid.uuid4())
    session.add(db.MdmRelationshipType(
        rel_type_id=rel_type_id, rel_type_name="MANAGES_FUND",
        source_node_type="adviser", target_node_type="fund",
        direction="outbound", is_temporal=True, merge_strategy="extend_temporal", is_active=True,
    ))
    company_id = str(uuid.uuid4())
    session.add(db.MdmEntity(entity_id=company_id, entity_type="company"))
    session.add(db.MdmCompany(entity_id=company_id, cik=320193, canonical_name="Issuer Corp"))
    session.commit()

    domain_writer = FakeWriter()
    mirror_writer = FakeWriter()
    exporter = MDMExporter(session=session, writer=domain_writer, mirror_writer=mirror_writer)

    exporter._mirror_entity_ids([company_id])

    domain_company_calls = [call for call in domain_writer.calls if call[0] not in ("MDM_ENTITY",)]
    mirror_company_calls = [call for call in mirror_writer.calls if call[0] not in ("MDM_ENTITY",)]
    assert {call[0] for call in domain_company_calls} == {"MDM_COMPANY_ENTITY"}
    assert {call[0] for call in mirror_company_calls} == {"MDM_COMPANY"}
