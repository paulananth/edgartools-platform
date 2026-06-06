"""MDM graph sync helpers — Postgres mirror only.

Writes mdm_relationship_instance rows (the Postgres mirror) which are then
exported to Snowflake NEO4J_GRAPH_MIGRATION via SnowflakeGraphSyncExecutor.
The Neo4j bolt driver and AuraDB are no longer used.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import (
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


@dataclass
class GraphSyncEngine:
    session: Session
    registry: GraphRegistry

    @classmethod
    def build(cls, session: Session) -> "GraphSyncEngine":
        return cls(session=session, registry=GraphRegistry.load(session))

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
        row, _created = self.ensure_relationship(
            rel_type_name=rel_type_name,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            properties=properties,
            effective_from=effective_from,
            effective_to=effective_to,
            source_system=source_system,
            source_accession=source_accession,
        )
        return row

    def ensure_relationship(
        self,
        rel_type_name: str,
        source_entity_id: str,
        target_entity_id: str,
        properties: Optional[dict] = None,
        effective_from=None,
        effective_to=None,
        source_system: Optional[str] = None,
        source_accession: Optional[str] = None,
    ) -> tuple[MdmRelationshipInstance, bool]:
        """Write to mdm_relationship_instance (PG mirror).

        Returns (row, created). Existing active rows with the same source,
        target, relationship type, temporal bounds, source accession, and
        properties are reused so reruns do not create duplicate MDM edges.
        """
        rec = self.registry.rel_type_by_name.get(rel_type_name)
        if rec is None:
            raise KeyError(f"Unknown relationship type '{rel_type_name}'")
        clean_properties = properties or {}
        candidates = self.session.scalars(
            select(MdmRelationshipInstance).where(
                MdmRelationshipInstance.rel_type_id == rec["rel_type_id"],
                MdmRelationshipInstance.source_entity_id == source_entity_id,
                MdmRelationshipInstance.target_entity_id == target_entity_id,
                MdmRelationshipInstance.is_active == True,
            )
        )
        for existing in candidates:
            if (
                (existing.properties or {}) == clean_properties
                and existing.effective_from == effective_from
                and existing.effective_to == effective_to
                and existing.source_accession == source_accession
            ):
                return existing, False

        row = MdmRelationshipInstance(
            rel_type_id=rec["rel_type_id"],
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            properties=clean_properties,
            effective_from=effective_from,
            effective_to=effective_to,
            source_system=source_system,
            source_accession=source_accession,
        )
        self.session.add(row)
        _emit_graph_event(
            "mdm_relationship_created",
            rel_type_name=rel_type_name,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            source_system=source_system,
            source_accession=source_accession,
            effective_from=effective_from.isoformat() if hasattr(effective_from, "isoformat") else effective_from,
            effective_to=effective_to.isoformat() if hasattr(effective_to, "isoformat") else effective_to,
            property_keys=sorted(clean_properties),
        )
        return row, True

    def pending_counts(self) -> dict[str, int]:
        """Return count of unsynced (graph_synced_at IS NULL, is_active) rows by rel_type_name."""
        rows = self.session.execute(
            select(
                MdmRelationshipType.rel_type_name,
                func.count(MdmRelationshipInstance.instance_id),
            )
            .select_from(MdmRelationshipInstance)
            .join(
                MdmRelationshipType,
                MdmRelationshipInstance.rel_type_id == MdmRelationshipType.rel_type_id,
            )
            .where(
                MdmRelationshipInstance.graph_synced_at.is_(None),
                MdmRelationshipInstance.is_active == True,
            )
            .group_by(MdmRelationshipType.rel_type_name)
        )
        return {name: int(count) for name, count in rows}

    def _pending_relationship_rows(
        self,
        *,
        limit: Optional[int],
        relationship_types: Optional[Iterable[str]],
        limit_per_type: Optional[int],
    ) -> list[MdmRelationshipInstance]:
        rel_type_names = list(relationship_types or [])
        rel_type_ids = [
            self.registry.rel_type_by_name[name]["rel_type_id"]
            for name in rel_type_names
            if name in self.registry.rel_type_by_name
        ]

        def base_stmt():
            stmt = select(MdmRelationshipInstance).where(
                MdmRelationshipInstance.graph_synced_at.is_(None),
                MdmRelationshipInstance.is_active == True,
            )
            if rel_type_ids:
                stmt = stmt.where(MdmRelationshipInstance.rel_type_id.in_(rel_type_ids))
            return stmt.order_by(MdmRelationshipInstance.created_at, MdmRelationshipInstance.instance_id)

        if limit_per_type is None:
            stmt = base_stmt()
            if limit:
                stmt = stmt.limit(limit)
            return list(self.session.scalars(stmt))

        selected: list[MdmRelationshipInstance] = []
        source_type_ids = rel_type_ids or [
            record["rel_type_id"] for record in self.registry.rel_type_by_name.values()
        ]
        for rel_type_id in source_type_ids:
            stmt = (
                select(MdmRelationshipInstance)
                .where(
                    MdmRelationshipInstance.graph_synced_at.is_(None),
                    MdmRelationshipInstance.is_active == True,
                    MdmRelationshipInstance.rel_type_id == rel_type_id,
                )
                .order_by(MdmRelationshipInstance.created_at, MdmRelationshipInstance.instance_id)
                .limit(limit_per_type)
            )
            for row in self.session.scalars(stmt):
                selected.append(row)
                if limit is not None and len(selected) >= limit:
                    return selected
        return selected


def backfill_relationship_instances(
    session: Session,
    limit: Optional[int] = None,
) -> dict:
    """Derive mdm_relationship_instance rows from existing mdm_fund and mdm_security data.

    Sources:
      MANAGES_FUND : mdm_fund.adviser_entity_id  -> mdm_fund.entity_id
      ISSUED_BY    : mdm_security.entity_id       -> mdm_security.issuer_entity_id

    Rows already present in mdm_relationship_instance are skipped.
    limit=None (default) means process all available rows.
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

    def _under_limit() -> bool:
        return limit is None or backfilled < limit

    if manages_fund and _under_limit():
        q = select(MdmFund).where(MdmFund.adviser_entity_id.isnot(None))
        if limit is not None:
            q = q.limit(limit - backfilled)
        for fund in session.scalars(q):
            if not _under_limit():
                break
            key = (manages_fund["rel_type_id"], fund.adviser_entity_id, fund.entity_id)
            if key in existing:
                continue
            _row, created = GraphSyncEngine(session, registry).ensure_relationship(
                "MANAGES_FUND",
                fund.adviser_entity_id,
                fund.entity_id,
                source_system="mdm_backfill",
            )
            if created:
                existing.add(key)
                backfilled += 1

    if issued_by and _under_limit():
        q = select(MdmSecurity).where(MdmSecurity.issuer_entity_id.isnot(None))
        if limit is not None:
            q = q.limit(limit - backfilled)
        for sec in session.scalars(q):
            if not _under_limit():
                break
            key = (issued_by["rel_type_id"], sec.entity_id, sec.issuer_entity_id)
            if key in existing:
                continue
            _row, created = GraphSyncEngine(session, registry).ensure_relationship(
                "ISSUED_BY",
                sec.entity_id,
                sec.issuer_entity_id,
                source_system="mdm_backfill",
            )
            if created:
                existing.add(key)
                backfilled += 1

    session.commit()

    return {"backfilled": backfilled, "synced": 0}


def _emit_graph_event(event: str, **payload: object) -> None:
    document = {
        "event": event,
        "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **payload,
    }
    print(json.dumps(document, sort_keys=True, default=str), file=sys.stderr, flush=True)
