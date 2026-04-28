"""Unit and integration tests for the Neo4j graph layer.

Layers (each builds on the previous):
  1. Cypher builders        — pure string generation, no DB/driver needed
  2. GraphRegistry          — loads from in-memory SQLite
  3. GraphSyncEngine        — record_relationship + sync_pending with mock bolt
  4. backfill_relationship_instances — derives rows from mdm_fund/mdm_security
  5. CLI commands           — verify-graph, backfill-relationships, sync-graph
  6. CLI bolt:// URI fix    — neo4j:// -> bolt:// normalisation
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import pytest

from edgar_warehouse.mdm.database import (
    MdmEntity,
    MdmFund,
    MdmRelationshipInstance,
    MdmSecurity,
)
from edgar_warehouse.mdm.graph import (
    GraphRegistry,
    GraphSyncEngine,
    Neo4jGraphClient,
    backfill_relationship_instances,
    node_merge_cypher,
    relationship_merge_cypher,
)


# ===========================================================================
# Layer 1 — Cypher template builders (no fixtures needed)
# ===========================================================================

class TestCypherBuilders:
    def _registry(self) -> GraphRegistry:
        reg = GraphRegistry()
        reg.labels_by_entity_type = {
            "company":  "Company",
            "adviser":  "Adviser",
            "fund":     "Fund",
            "security": "Security",
        }
        reg.rel_type_by_name = {
            "MANAGES_FUND": {
                "rel_type_id":      "rt-mf",
                "rel_type_name":    "MANAGES_FUND",
                "source_node_type": "adviser",
                "target_node_type": "fund",
                "direction":        "outbound",
                "is_temporal":      True,
                "merge_strategy":   "extend_temporal",
            },
            "ISSUED_BY": {
                "rel_type_id":      "rt-ib",
                "rel_type_name":    "ISSUED_BY",
                "source_node_type": "security",
                "target_node_type": "company",
                "direction":        "outbound",
                "is_temporal":      True,
                "merge_strategy":   "extend_temporal",
            },
        }
        return reg

    def test_node_merge_uses_entity_label(self):
        cypher = node_merge_cypher(self._registry(), "company")
        assert "Company" in cypher
        assert "entity_id: $entity_id" in cypher
        assert "MERGE" in cypher
        assert "SET" in cypher

    def test_node_merge_unknown_type_raises(self):
        with pytest.raises(KeyError, match="unknown_type"):
            node_merge_cypher(self._registry(), "unknown_type")

    def test_relationship_merge_manages_fund(self):
        cypher = relationship_merge_cypher(self._registry(), "MANAGES_FUND")
        assert "Adviser" in cypher
        assert "Fund" in cypher
        assert "MANAGES_FUND" in cypher
        assert "$source_entity_id" in cypher
        assert "$target_entity_id" in cypher

    def test_relationship_merge_issued_by(self):
        cypher = relationship_merge_cypher(self._registry(), "ISSUED_BY")
        assert "Security" in cypher
        assert "Company" in cypher
        assert "ISSUED_BY" in cypher

    def test_relationship_merge_unknown_type_raises(self):
        with pytest.raises(KeyError, match="NO_SUCH_REL"):
            relationship_merge_cypher(self._registry(), "NO_SUCH_REL")


# ===========================================================================
# Layer 2 — GraphRegistry loads from DB (uses db_session fixture)
# ===========================================================================

class TestGraphRegistry:
    def test_loads_entity_types(self, db_session):
        reg = GraphRegistry.load(db_session)
        assert "company"  in reg.labels_by_entity_type
        assert "adviser"  in reg.labels_by_entity_type
        assert "fund"     in reg.labels_by_entity_type
        assert "security" in reg.labels_by_entity_type

    def test_loads_relationship_types(self, db_session):
        reg = GraphRegistry.load(db_session)
        assert "MANAGES_FUND" in reg.rel_type_by_name
        assert "ISSUED_BY"    in reg.rel_type_by_name

    def test_rel_type_by_id_is_populated(self, db_session):
        reg = GraphRegistry.load(db_session)
        for rec in reg.rel_type_by_name.values():
            assert rec["rel_type_id"] in reg.rel_type_by_id

    def test_label_returns_correct_neo4j_label(self, db_session):
        reg = GraphRegistry.load(db_session)
        assert reg.label("company") == "Company"
        assert reg.label("fund")    == "Fund"

    def test_label_unknown_raises(self, db_session):
        reg = GraphRegistry.load(db_session)
        with pytest.raises(KeyError):
            reg.label("nonexistent")


# ===========================================================================
# Layer 3 — GraphSyncEngine: record_relationship + sync_pending
# ===========================================================================

def _make_entity(session, entity_type: str) -> str:
    eid = str(uuid.uuid4())
    session.add(MdmEntity(entity_id=eid, entity_type=entity_type))
    session.flush()
    return eid


class TestGraphSyncEngine:
    def test_record_relationship_writes_instance_row(self, db_session):
        adviser_id = _make_entity(db_session, "adviser")
        fund_id    = _make_entity(db_session, "fund")
        db_session.commit()

        engine = GraphSyncEngine.build(db_session)
        engine.record_relationship("MANAGES_FUND", adviser_id, fund_id)
        db_session.commit()

        rows = list(db_session.scalars(
            __import__("sqlalchemy", fromlist=["select"]).select(MdmRelationshipInstance)
        ))
        assert len(rows) == 1
        assert rows[0].source_entity_id == adviser_id
        assert rows[0].target_entity_id == fund_id
        assert rows[0].graph_synced_at is None

    def test_record_relationship_unknown_type_raises(self, db_session):
        engine = GraphSyncEngine.build(db_session)
        with pytest.raises(KeyError, match="NO_SUCH_REL"):
            engine.record_relationship("NO_SUCH_REL", "src", "tgt")

    def test_sync_pending_returns_zero_without_neo4j(self, db_session):
        adviser_id = _make_entity(db_session, "adviser")
        fund_id    = _make_entity(db_session, "fund")
        db_session.commit()
        engine = GraphSyncEngine.build(db_session, neo4j=None)
        engine.record_relationship("MANAGES_FUND", adviser_id, fund_id)
        db_session.commit()
        assert engine.sync_pending() == 0

    def test_sync_pending_calls_bolt_and_stamps_synced_at(self, db_session, neo4j_client):
        adviser_id = _make_entity(db_session, "adviser")
        fund_id    = _make_entity(db_session, "fund")
        db_session.commit()

        engine = GraphSyncEngine.build(db_session, neo4j=neo4j_client)
        engine.record_relationship("MANAGES_FUND", adviser_id, fund_id)
        db_session.commit()

        synced = engine.sync_pending()
        assert synced == 1

        row = db_session.scalars(
            __import__("sqlalchemy", fromlist=["select"]).select(MdmRelationshipInstance)
        ).first()
        assert row.graph_synced_at is not None

        with neo4j_client.session() as s:
            s.run("MATCH (n) WHERE n.entity_id IN $ids DETACH DELETE n",
                  ids=[adviser_id, fund_id])

    def test_sync_pending_respects_limit(self, db_session, neo4j_client):
        from sqlalchemy import select
        adviser_id = _make_entity(db_session, "adviser")
        fund_ids = []
        for _ in range(5):
            fund_id = _make_entity(db_session, "fund")
            fund_ids.append(fund_id)
            db_session.flush()
            db_session.add(MdmRelationshipInstance(
                rel_type_id=list(GraphRegistry.load(db_session).rel_type_by_name.values())[0]["rel_type_id"],
                source_entity_id=adviser_id,
                target_entity_id=fund_id,
                source_system="test",
            ))
        db_session.commit()

        engine = GraphSyncEngine.build(db_session, neo4j=neo4j_client)
        synced = engine.sync_pending(limit=3)
        assert synced == 3

        pending = list(db_session.scalars(
            select(MdmRelationshipInstance).where(MdmRelationshipInstance.graph_synced_at.is_(None))
        ))
        assert len(pending) == 2

        with neo4j_client.session() as s:
            s.run("MATCH (n) WHERE n.entity_id IN $ids DETACH DELETE n",
                  ids=[adviser_id] + fund_ids)

    def test_sync_pending_skips_already_synced(self, db_session, neo4j_client):
        from sqlalchemy import select
        adviser_id = _make_entity(db_session, "adviser")
        fund_id    = _make_entity(db_session, "fund")
        db_session.commit()

        engine = GraphSyncEngine.build(db_session, neo4j=neo4j_client)
        engine.record_relationship("MANAGES_FUND", adviser_id, fund_id)
        db_session.commit()

        first  = engine.sync_pending()
        second = engine.sync_pending()
        assert first  == 1
        assert second == 0

        with neo4j_client.session() as s:
            s.run("MATCH (n) WHERE n.entity_id IN $ids DETACH DELETE n",
                  ids=[adviser_id, fund_id])


# ===========================================================================
# Layer 4 — backfill_relationship_instances
# ===========================================================================

def _make_full_entity(session, entity_type: str) -> str:
    """Create MdmEntity + domain row so _ensure_node_exists can look it up."""
    eid = str(uuid.uuid4())
    session.add(MdmEntity(entity_id=eid, entity_type=entity_type))
    session.flush()
    return eid


class TestBackfillRelationshipInstances:
    def test_backfill_derives_manages_fund_rows(self, db_session):
        from sqlalchemy import select
        adviser_id = _make_full_entity(db_session, "adviser")
        fund_id    = _make_full_entity(db_session, "fund")
        db_session.add(MdmFund(
            entity_id=fund_id,
            adviser_entity_id=adviser_id,
            canonical_name="Test Fund",
        ))
        db_session.commit()

        result = backfill_relationship_instances(db_session, neo4j=None, limit=100)
        assert result["backfilled"] == 1
        assert result["synced"] == 0

        rows = list(db_session.scalars(select(MdmRelationshipInstance)))
        assert len(rows) == 1
        assert rows[0].source_entity_id == adviser_id
        assert rows[0].target_entity_id == fund_id
        assert rows[0].source_system == "mdm_backfill"

    def test_backfill_derives_issued_by_rows(self, db_session):
        from sqlalchemy import select
        company_id  = _make_full_entity(db_session, "company")
        security_id = _make_full_entity(db_session, "security")
        db_session.add(MdmSecurity(
            entity_id=security_id,
            issuer_entity_id=company_id,
            canonical_title="Common Stock",
            security_type="common_stock",
        ))
        db_session.commit()

        result = backfill_relationship_instances(db_session, neo4j=None, limit=100)
        assert result["backfilled"] == 1
        rows = list(db_session.scalars(select(MdmRelationshipInstance)))
        assert rows[0].source_entity_id == security_id
        assert rows[0].target_entity_id == company_id

    def test_backfill_skips_duplicates(self, db_session):
        adviser_id = _make_full_entity(db_session, "adviser")
        fund_id    = _make_full_entity(db_session, "fund")
        db_session.add(MdmFund(entity_id=fund_id, adviser_entity_id=adviser_id, canonical_name="F"))
        db_session.commit()

        r1 = backfill_relationship_instances(db_session, neo4j=None, limit=100)
        r2 = backfill_relationship_instances(db_session, neo4j=None, limit=100)
        assert r1["backfilled"] == 1
        assert r2["backfilled"] == 0

    def test_backfill_respects_limit(self, db_session):
        adviser_id = _make_full_entity(db_session, "adviser")
        for i in range(5):
            fid = _make_full_entity(db_session, "fund")
            db_session.add(MdmFund(entity_id=fid, adviser_entity_id=adviser_id, canonical_name=f"F{i}"))
        db_session.commit()

        result = backfill_relationship_instances(db_session, neo4j=None, limit=3)
        assert result["backfilled"] == 3

    def test_backfill_triggers_sync_when_neo4j_provided(self, db_session, neo4j_client):
        adviser_id = _make_full_entity(db_session, "adviser")
        fund_id    = _make_full_entity(db_session, "fund")
        db_session.add(MdmFund(entity_id=fund_id, adviser_entity_id=adviser_id, canonical_name="F"))
        db_session.commit()

        result = backfill_relationship_instances(db_session, neo4j=neo4j_client, limit=100)
        assert result["backfilled"] == 1
        assert result["synced"] == 1

        with neo4j_client.session() as s:
            s.run("MATCH (n) WHERE n.entity_id IN $ids DETACH DELETE n",
                  ids=[adviser_id, fund_id])

    def test_backfill_skips_funds_without_adviser(self, db_session):
        fund_id = _make_full_entity(db_session, "fund")
        db_session.add(MdmFund(entity_id=fund_id, adviser_entity_id=None, canonical_name="Orphan"))
        db_session.commit()

        result = backfill_relationship_instances(db_session, neo4j=None, limit=100)
        assert result["backfilled"] == 0


# ===========================================================================
# Layer 5 — CLI commands
# ===========================================================================

class TestCLICommands:
    def test_parser_exposes_backfill_relationships(self):
        from edgar_warehouse.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["mdm", "backfill-relationships", "--limit", "50"])
        assert args.mdm_command == "backfill-relationships"
        assert args.limit == 50

    def test_parser_backfill_default_limit_100(self):
        from edgar_warehouse.cli import build_parser
        args = build_parser().parse_args(["mdm", "backfill-relationships"])
        assert args.limit == 100

    def test_parser_exposes_verify_graph(self):
        from edgar_warehouse.cli import build_parser
        args = build_parser().parse_args(["mdm", "verify-graph"])
        assert args.mdm_command == "verify-graph"

    def test_parser_exposes_sync_graph(self):
        from edgar_warehouse.cli import build_parser
        args = build_parser().parse_args(["mdm", "sync-graph"])
        assert args.mdm_command == "sync-graph"

    def test_parser_sync_graph_limit(self):
        from edgar_warehouse.cli import build_parser
        args = build_parser().parse_args(["mdm", "sync-graph", "--limit", "25"])
        assert args.limit == 25

    def test_runtime_ops_exposes_new_commands(self):
        """Extend existing e2e-operations test to include graph commands."""
        from edgar_warehouse.cli import build_parser
        parser = build_parser()
        for cmd in ("backfill-relationships", "verify-graph", "sync-graph"):
            args = parser.parse_args(["mdm", cmd])
            assert args.mdm_command == cmd

    def test_verify_graph_returns_1_when_neo4j_not_configured(self):
        from edgar_warehouse.mdm.cli import _handle_verify_graph
        import argparse
        with patch.dict("os.environ", {}, clear=True):
            # Remove any existing NEO4J env vars
            import os
            for k in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "NEO4J_SECRET_JSON"):
                os.environ.pop(k, None)
            result = _handle_verify_graph(argparse.Namespace())
        assert result == 1

    def test_backfill_handler_returns_0_on_success(self, db_session):
        import argparse
        from edgar_warehouse.mdm.cli import _handle_backfill_relationships

        # Route _session() through the test engine. Clear NEO4J_* so the real
        # _neo4j_client() returns None (empty strings are falsy in the check).
        env = {"NEO4J_URI": "", "NEO4J_USER": "", "NEO4J_PASSWORD": ""}
        with patch("edgar_warehouse.mdm.cli._session", return_value=db_session), \
             patch.dict(os.environ, env):
            result = _handle_backfill_relationships(argparse.Namespace(limit=10))
        assert result == 0


# ===========================================================================
# Layer 6 — bolt:// URI normalisation in _neo4j_client
# ===========================================================================

class TestNeo4jClientURINormalisation:
    """The cli._neo4j_client() must rewrite neo4j:// -> bolt:// so that
    single-instance Azure Container Apps Neo4j (no bolt_advertised_address)
    doesn't fail routing discovery.

    Neo4jGraphClient is a @dataclass with uri: str as a public field and lazy
    connection (connect() is not called at construction time), so we can
    inspect client.uri directly without mocking the class or connecting.
    """

    def _call_neo4j_client(self, uri: str):
        from edgar_warehouse.mdm.cli import _neo4j_client

        with patch.dict(os.environ, {
            "NEO4J_URI":      uri,
            "NEO4J_USER":     "neo4j",
            "NEO4J_PASSWORD": "secret",
        }):
            return _neo4j_client()

    def test_neo4j_scheme_rewritten_to_bolt(self):
        client = self._call_neo4j_client("neo4j://host:7687")
        assert client is not None
        assert client.uri.startswith("bolt://"), f"Expected bolt://, got: {client.uri}"

    def test_bolt_scheme_unchanged(self):
        client = self._call_neo4j_client("bolt://host:7687")
        assert client is not None
        assert client.uri.startswith("bolt://")

    def test_returns_none_when_env_vars_missing(self):
        from edgar_warehouse.mdm.cli import _neo4j_client
        for k in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "NEO4J_SECRET_JSON"):
            os.environ.pop(k, None)
        with patch.dict(os.environ, {}, clear=True):
            assert _neo4j_client() is None
