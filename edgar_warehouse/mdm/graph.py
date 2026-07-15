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
    MdmRelationshipSourcePriority,
    MdmRelationshipType,
    MdmSecurity,
    relationship_logical_id,
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
        valid_from_date=None,
        valid_to_date=None,
        date_provenance: str = "unknown",
        relationship_kind: str = "direct",
    ) -> tuple[MdmRelationshipInstance, bool]:
        """Write a relationship-version row to mdm_relationship_instance (PG mirror).

        Returns (row, created). ``relationship_id`` (the immutable logical
        ID for this rel_type/source/target triple) is deterministic, so
        every version of the same logical relationship shares it.

        Conflict policy against the triple's current versions (active,
        non-quarantined, not superseded):
          * Identical evidence (same properties + validity window) from a
            new source/accession merges provenance into the existing
            version's ``source_evidence`` instead of inserting a duplicate.
          * Overlapping validity windows with *different* properties are a
            real conflict, resolved via ``mdm_relationship_source_priority``
            (lower priority number wins): the losing version is superseded
            (never deleted). With no configured priority for either source,
            the new version is inserted quarantined and the existing
            version stays authoritative -- no silent last-writer-wins.
          * Non-overlapping windows (e.g. two distinct employment stints)
            are not a conflict; both remain current.
        """
        rec = self.registry.rel_type_by_name.get(rel_type_name)
        if rec is None:
            raise KeyError(f"Unknown relationship type '{rel_type_name}'")
        clean_properties = properties or {}
        resolved_valid_from = valid_from_date if valid_from_date is not None else effective_from
        resolved_valid_to = valid_to_date if valid_to_date is not None else effective_to
        rel_type_id = rec["rel_type_id"]
        rel_id = relationship_logical_id(rel_type_id, source_entity_id, target_entity_id)

        current = list(
            self.session.scalars(
                select(MdmRelationshipInstance).where(
                    MdmRelationshipInstance.relationship_id == rel_id,
                    MdmRelationshipInstance.is_active == True,
                    MdmRelationshipInstance.quarantined == False,
                    MdmRelationshipInstance.superseded_by_version_id.is_(None),
                )
            )
        )

        for existing in current:
            if (
                (existing.properties or {}) == clean_properties
                and existing.valid_from_date == resolved_valid_from
                and existing.valid_to_date == resolved_valid_to
            ):
                _merge_source_evidence(existing, source_system, source_accession)
                return existing, False

        conflict = None
        for existing in current:
            if _intervals_overlap(
                existing.valid_from_date, existing.valid_to_date, resolved_valid_from, resolved_valid_to
            ) and (existing.properties or {}) != clean_properties:
                conflict = existing
                break

        row = MdmRelationshipInstance(
            relationship_id=rel_id,
            rel_type_id=rel_type_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            properties=clean_properties,
            effective_from=effective_from,
            effective_to=effective_to,
            valid_from_date=resolved_valid_from,
            valid_to_date=resolved_valid_to,
            date_provenance=date_provenance,
            relationship_kind=relationship_kind,
            source_system=source_system,
            source_accession=source_accession,
            source_evidence=[_evidence_entry(source_system, source_accession)],
        )
        self.session.add(row)
        self.session.flush()

        if conflict is not None:
            winner = _resolve_source_priority(
                self.session, rel_type_id, conflict.source_system, source_system
            )
            if winner == "new":
                conflict.superseded_by_version_id = row.instance_id
            elif winner == "existing":
                row.superseded_by_version_id = conflict.instance_id
            else:
                row.quarantined = True
                row.quarantine_reason = (
                    "conflicting overlapping evidence with no configured "
                    f"mdm_relationship_source_priority winner between "
                    f"'{conflict.source_system}' and '{source_system}'"
                )

        _emit_graph_event(
            "mdm_relationship_created",
            rel_type_name=rel_type_name,
            relationship_id=rel_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            source_system=source_system,
            source_accession=source_accession,
            effective_from=effective_from.isoformat() if hasattr(effective_from, "isoformat") else effective_from,
            effective_to=effective_to.isoformat() if hasattr(effective_to, "isoformat") else effective_to,
            quarantined=row.quarantined,
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


# ---------------------------------------------------------------------------
# Temporal conflict/lifecycle helpers (07-01)
# ---------------------------------------------------------------------------

def _intervals_overlap(a_from, a_to, b_from, b_to) -> bool:
    """Half-open interval overlap; None means unbounded on that side."""
    starts_before_b_ends = b_to is None or a_from is None or a_from < b_to
    starts_before_a_ends = a_to is None or b_from is None or b_from < a_to
    return starts_before_b_ends and starts_before_a_ends


def _evidence_entry(source_system: Optional[str], source_accession: Optional[str]) -> dict:
    return {
        "source_system": source_system,
        "source_accession": source_accession,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _merge_source_evidence(
    existing: MdmRelationshipInstance,
    source_system: Optional[str],
    source_accession: Optional[str],
) -> None:
    """Append a new source's confirmation of identical evidence, without a duplicate row."""
    evidence = list(existing.source_evidence or [])
    already_recorded = any(
        e.get("source_system") == source_system and e.get("source_accession") == source_accession
        for e in evidence
    )
    if not already_recorded:
        evidence.append(_evidence_entry(source_system, source_accession))
        existing.source_evidence = evidence


def _resolve_source_priority(
    session: Session,
    rel_type_id: str,
    existing_source: Optional[str],
    new_source: Optional[str],
) -> str:
    """Return 'existing', 'new', or 'none' (no configured, deterministic winner).

    Lower ``priority`` wins (matches mdm_source_priority's convention).
    """
    rows = {
        row.source_system: row.priority
        for row in session.scalars(
            select(MdmRelationshipSourcePriority).where(
                MdmRelationshipSourcePriority.rel_type_id == rel_type_id,
                MdmRelationshipSourcePriority.is_active == True,
                MdmRelationshipSourcePriority.source_system.in_(
                    [s for s in (existing_source, new_source) if s is not None]
                ),
            )
        )
    }
    existing_priority = rows.get(existing_source) if existing_source else None
    new_priority = rows.get(new_source) if new_source else None
    if existing_priority is None or new_priority is None or existing_priority == new_priority:
        return "none"
    return "existing" if existing_priority < new_priority else "new"


def close_relationship_version(
    session: Session, instance_id: str, valid_to_date
) -> MdmRelationshipInstance:
    """Business-close a version (set its end date). Never deletes the row."""
    row = session.get(MdmRelationshipInstance, instance_id)
    if row is None:
        raise KeyError(f"No mdm_relationship_instance with instance_id={instance_id}")
    row.valid_to_date = valid_to_date
    row.effective_to = valid_to_date
    return row


def supersede_relationship_version(
    session: Session, old_instance_id: str, new_instance_id: str
) -> MdmRelationshipInstance:
    """Mark ``old_instance_id`` as superseded by ``new_instance_id``. Never deletes the row."""
    row = session.get(MdmRelationshipInstance, old_instance_id)
    if row is None:
        raise KeyError(f"No mdm_relationship_instance with instance_id={old_instance_id}")
    row.superseded_by_version_id = new_instance_id
    return row


def quarantine_relationship_version(
    session: Session, instance_id: str, reason: str
) -> MdmRelationshipInstance:
    """Quarantine a version so it is excluded from 'current' reads. Never deletes the row."""
    row = session.get(MdmRelationshipInstance, instance_id)
    if row is None:
        raise KeyError(f"No mdm_relationship_instance with instance_id={instance_id}")
    row.quarantined = True
    row.quarantine_reason = reason
    return row


def _emit_graph_event(event: str, **payload: object) -> None:
    document = {
        "event": event,
        "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **payload,
    }
    print(json.dumps(document, sort_keys=True, default=str), file=sys.stderr, flush=True)
