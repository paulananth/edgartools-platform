"""Neo4j AuraDB sync engine.

Fully data-driven: Neo4j labels come from mdm_entity_type_definition and
relationship types from mdm_relationship_type. No label strings or Cypher
templates are hardcoded. Adding a new relationship type is a SQL INSERT.

Sync pattern:
  1. Build Cypher MERGE templates per entity type / rel type from the
     registry tables.
  2. Write mdm_relationship_instance rows first (PostgreSQL mirror).
  3. Push node + edge upserts to Neo4j via neo4j-python-driver Bolt.
  4. Stamp graph_synced_at on mdm_relationship_instance.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

try:  # optional dependency from the [mdm] extra
    from neo4j import GraphDatabase  # type: ignore
except ImportError:  # pragma: no cover
    GraphDatabase = None  # type: ignore

from edgar_warehouse.mdm.database import (
    MdmEntity,
    MdmEntityTypeDefinition,
    MdmFund,
    MdmRelationshipInstance,
    MdmRelationshipType,
    MdmSecurity,
)


@dataclass
class GraphRegistry:
    """Snapshot of graph configuration; built once per pipeline run."""

    labels_by_entity_type: dict[str, str] = field(default_factory=dict)
    domain_tables: dict[str, str] = field(default_factory=dict)
    primary_id_fields: dict[str, str] = field(default_factory=dict)
    rel_type_by_id: dict[str, dict] = field(default_factory=dict)
    rel_type_by_name: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def load(cls, session: Session) -> "GraphRegistry":
        reg = cls()
        for et in session.scalars(
            select(MdmEntityTypeDefinition).where(
                MdmEntityTypeDefinition.is_active == True
            )
        ):
            reg.labels_by_entity_type[et.entity_type] = et.neo4j_label
            reg.domain_tables[et.entity_type] = et.domain_table
            reg.primary_id_fields[et.entity_type] = et.primary_id_field

        for rt in session.scalars(
            select(MdmRelationshipType).where(MdmRelationshipType.is_active == True)
        ):
            record = {
                "rel_type_id": rt.rel_type_id,
                "rel_type_name": rt.rel_type_name,
                "source_node_type": rt.source_node_type,
                "target_node_type": rt.target_node_type,
                "direction": rt.direction,
                "is_temporal": rt.is_temporal,
                "merge_strategy": rt.merge_strategy,
            }
            reg.rel_type_by_id[rt.rel_type_id] = record
            reg.rel_type_by_name[rt.rel_type_name] = record
        return reg

    def label(self, entity_type: str) -> str:
        try:
            return self.labels_by_entity_type[entity_type]
        except KeyError as e:
            raise KeyError(f"Unknown entity_type '{entity_type}' in graph registry") from e


# ---------------------------------------------------------------------------
# Cypher template builders (generated, never hardcoded)
# ---------------------------------------------------------------------------

def node_merge_cypher(registry: GraphRegistry, entity_type: str) -> str:
    label = registry.label(entity_type)
    # Always merge by entity_id; domain-specific IDs become properties.
    return (
        f"MERGE (n:{label} {{entity_id: $entity_id}}) "
        f"SET n += $properties "
        f"RETURN n.entity_id AS entity_id"
    )


def relationship_merge_cypher(registry: GraphRegistry, rel_type_name: str) -> str:
    rec = registry.rel_type_by_name.get(rel_type_name)
    if rec is None:
        raise KeyError(f"Unknown relationship type '{rel_type_name}'")
    src_label = registry.label(rec["source_node_type"])
    tgt_label = registry.label(rec["target_node_type"])
    return (
        f"MATCH (s:{src_label} {{entity_id: $source_entity_id}}), "
        f"(t:{tgt_label} {{entity_id: $target_entity_id}}) "
        f"MERGE (s)-[r:{rel_type_name}]->(t) "
        f"SET r += $properties "
        f"RETURN id(r) AS rel_id"
    )


# ---------------------------------------------------------------------------
# Graph client
# ---------------------------------------------------------------------------

@dataclass
class Neo4jGraphClient:
    uri: str
    user: str
    password: str
    _driver: Any = field(default=None, init=False, repr=False)

    def connect(self) -> None:
        if GraphDatabase is None:
            raise RuntimeError(
                "neo4j driver not installed. Install with: pip install edgartools-platform[mdm]"
            )
        self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    @contextmanager
    def session(self):
        if self._driver is None:
            self.connect()
        with self._driver.session() as s:
            yield s


@dataclass
class GraphSyncEngine:
    session: Session
    registry: GraphRegistry
    neo4j: Optional[Neo4jGraphClient] = None

    @classmethod
    def build(cls, session: Session, neo4j: Optional[Neo4jGraphClient] = None) -> "GraphSyncEngine":
        return cls(session=session, registry=GraphRegistry.load(session), neo4j=neo4j)

    def upsert_node(self, entity_id: str, entity_type: str, properties: dict) -> None:
        cypher = node_merge_cypher(self.registry, entity_type)
        props = {k: v for k, v in properties.items() if v is not None}
        props.setdefault("entity_id", entity_id)
        if self.neo4j is None:
            return
        with self.neo4j.session() as s:
            s.run(cypher, entity_id=entity_id, properties=props)

    def record_relationship(
        self,
        rel_type_name: str,
        source_entity_id: str,
        target_entity_id: str,
        properties: Optional[dict] = None,
        effective_from=None,
        effective_to=None,
        source_system: Optional[str] = None,
        source_accession: Optional[str] = None,
    ) -> MdmRelationshipInstance:
        """Write to mdm_relationship_instance first (PG mirror), leave
        graph_synced_at NULL so sync_pending() picks it up."""
        rec = self.registry.rel_type_by_name.get(rel_type_name)
        if rec is None:
            raise KeyError(f"Unknown relationship type '{rel_type_name}'")

        row = MdmRelationshipInstance(
            rel_type_id=rec["rel_type_id"],
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            properties=properties or {},
            effective_from=effective_from,
            effective_to=effective_to,
            source_system=source_system,
            source_accession=source_accession,
        )
        self.session.add(row)
        return row

    def sync_pending(self, limit: Optional[int] = None) -> int:
        """Push every mdm_relationship_instance with graph_synced_at IS NULL
        to Neo4j. Returns count of rows synced."""
        if self.neo4j is None:
            return 0
        stmt = select(MdmRelationshipInstance).where(
            MdmRelationshipInstance.graph_synced_at.is_(None),
            MdmRelationshipInstance.is_active == True,
        )
        if limit:
            stmt = stmt.limit(limit)
        rows: list[MdmRelationshipInstance] = list(self.session.scalars(stmt))
        if not rows:
            return 0

        now = datetime.now(timezone.utc)
        with self.neo4j.session() as s:
            for row in rows:
                rec = self.registry.rel_type_by_id[row.rel_type_id]
                # Ensure both end-point nodes exist
                self._ensure_node_exists(s, row.source_entity_id, rec["source_node_type"])
                self._ensure_node_exists(s, row.target_entity_id, rec["target_node_type"])

                props = dict(row.properties or {})
                if row.effective_from:
                    props["effective_from"] = row.effective_from.isoformat()
                if row.effective_to:
                    props["effective_to"] = row.effective_to.isoformat()
                if row.source_accession:
                    props["source_accession"] = row.source_accession

                cypher = relationship_merge_cypher(self.registry, rec["rel_type_name"])
                s.run(
                    cypher,
                    source_entity_id=row.source_entity_id,
                    target_entity_id=row.target_entity_id,
                    properties=props,
                )

        self.session.execute(
            update(MdmRelationshipInstance)
            .where(MdmRelationshipInstance.instance_id.in_([r.instance_id for r in rows]))
            .values(graph_synced_at=now)
        )
        return len(rows)

    def _ensure_node_exists(self, neo4j_session, entity_id: str, entity_type: str) -> None:
        entity = self.session.get(MdmEntity, entity_id)
        if entity is None or entity.is_quarantined:
            return
        props: dict = {"entity_id": entity_id}
        domain_table = self.registry.domain_tables.get(entity_type)
        if domain_table:
            row = self.session.execute(
                select(*self._domain_columns(domain_table))
                .select_from(self._domain_selectable(domain_table))
                .where(self._domain_entity_id_col(domain_table) == entity_id)
            ).first()
            if row:
                for col, val in row._mapping.items():
                    if val is None:
                        continue
                    props[col] = val.isoformat() if hasattr(val, "isoformat") else val
        cypher = node_merge_cypher(self.registry, entity_type)
        neo4j_session.run(cypher, entity_id=entity_id, properties=props)

    @staticmethod
    def _domain_selectable(table_name: str):
        from edgar_warehouse.mdm import database as db
        mapping = {
            "mdm_company": db.MdmCompany,
            "mdm_adviser": db.MdmAdviser,
            "mdm_person": db.MdmPerson,
            "mdm_security": db.MdmSecurity,
            "mdm_fund": db.MdmFund,
        }
        return mapping[table_name].__table__

    @classmethod
    def _domain_columns(cls, table_name: str) -> Iterable:
        return list(cls._domain_selectable(table_name).c)

    @classmethod
    def _domain_entity_id_col(cls, table_name: str):
        return cls._domain_selectable(table_name).c.entity_id


def backfill_relationship_instances(
    session: Session,
    neo4j: Optional[Neo4jGraphClient] = None,
    limit: int = 100,
) -> dict:
    """Derive mdm_relationship_instance rows from existing mdm_fund and
    mdm_security data, then sync up to *limit* rows to Neo4j.

    Sources:
      MANAGES_FUND : mdm_fund.adviser_entity_id  -> mdm_fund.entity_id
      ISSUED_BY    : mdm_security.entity_id       -> mdm_security.issuer_entity_id

    Rows already present in mdm_relationship_instance are skipped.
    Returns a summary dict with keys backfilled, synced.
    """
    registry = GraphRegistry.load(session)
    manages_fund = registry.rel_type_by_name.get("MANAGES_FUND")
    issued_by = registry.rel_type_by_name.get("ISSUED_BY")

    existing: set[tuple] = {
        (r.rel_type_id, r.source_entity_id, r.target_entity_id)
        for r in session.scalars(select(MdmRelationshipInstance))
    }

    backfilled = 0

    if manages_fund and backfilled < limit:
        for fund in session.scalars(
            select(MdmFund)
            .where(MdmFund.adviser_entity_id.isnot(None))
            .limit(limit - backfilled)
        ):
            key = (manages_fund["rel_type_id"], fund.adviser_entity_id, fund.entity_id)
            if key in existing:
                continue
            session.add(
                MdmRelationshipInstance(
                    rel_type_id=manages_fund["rel_type_id"],
                    source_entity_id=fund.adviser_entity_id,
                    target_entity_id=fund.entity_id,
                    source_system="mdm_backfill",
                )
            )
            existing.add(key)
            backfilled += 1

    if issued_by and backfilled < limit:
        for sec in session.scalars(
            select(MdmSecurity)
            .where(MdmSecurity.issuer_entity_id.isnot(None))
            .limit(limit - backfilled)
        ):
            key = (issued_by["rel_type_id"], sec.entity_id, sec.issuer_entity_id)
            if key in existing:
                continue
            session.add(
                MdmRelationshipInstance(
                    rel_type_id=issued_by["rel_type_id"],
                    source_entity_id=sec.entity_id,
                    target_entity_id=sec.issuer_entity_id,
                    source_system="mdm_backfill",
                )
            )
            existing.add(key)
            backfilled += 1

    session.commit()

    synced = 0
    if neo4j is not None and backfilled > 0:
        engine = GraphSyncEngine.build(session, neo4j)
        synced = engine.sync_pending(limit=limit)
        session.commit()

    return {"backfilled": backfilled, "synced": synced}
