"""Graph endpoints — neighborhood, traversal, sync status.

All graph data is read from the PostgreSQL mirror (mdm_relationship_instance).
Graph analytics run via the Snowflake-hosted Neo4j Graph Analytics native app.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm import database as db
from edgar_warehouse.mdm.api.deps import get_db
from edgar_warehouse.mdm.api.schemas.graph import (
    GraphEdge,
    GraphNode,
    Neighborhood,
    RelTypeDetail,
    RelTypeOut,
    SyncStatus,
    TraversalRequest,
)
from edgar_warehouse.mdm.graph import GraphRegistry

router = APIRouter(prefix="/graph", tags=["graph"])


def _registry(session: Session) -> GraphRegistry:
    return GraphRegistry.load(session)


@router.get("/relationship-types", response_model=list[RelTypeOut])
def list_relationship_types(session: Session = Depends(get_db)) -> list[RelTypeOut]:
    rows = session.scalars(
        select(db.MdmRelationshipType).where(db.MdmRelationshipType.is_active == True)
    ).all()
    return [
        RelTypeOut(
            rel_type_name=r.rel_type_name,
            source_node_type=r.source_node_type,
            target_node_type=r.target_node_type,
            direction=r.direction,
            is_temporal=r.is_temporal,
            description=r.description,
        )
        for r in rows
    ]


@router.get("/relationship-types/{rel_type_name}", response_model=RelTypeDetail)
def get_relationship_type(
    rel_type_name: str, session: Session = Depends(get_db)
) -> RelTypeDetail:
    rt = session.scalar(
        select(db.MdmRelationshipType).where(
            db.MdmRelationshipType.rel_type_name == rel_type_name
        )
    )
    if rt is None:
        raise HTTPException(404, "relationship type not found")
    props = session.scalars(
        select(db.MdmRelationshipPropertyDef).where(
            db.MdmRelationshipPropertyDef.rel_type_id == rt.rel_type_id
        )
    ).all()
    return RelTypeDetail(
        rel_type_name=rt.rel_type_name,
        source_node_type=rt.source_node_type,
        target_node_type=rt.target_node_type,
        direction=rt.direction,
        is_temporal=rt.is_temporal,
        description=rt.description,
        properties=[
            {
                "name": p.property_name,
                "data_type": p.data_type,
                "is_required": p.is_required,
                "default_value": p.default_value,
                "description": p.description,
            }
            for p in props
        ],
    )


def _validate_rel_types(session: Session, names: list[str]) -> list[str]:
    if not names:
        return []
    existing = set(
        session.scalars(
            select(db.MdmRelationshipType.rel_type_name).where(
                db.MdmRelationshipType.rel_type_name.in_(names)
            )
        ).all()
    )
    bad = [n for n in names if n not in existing]
    if bad:
        raise HTTPException(422, f"unknown relationship types: {bad}")
    return names


def _node_for(
    session: Session,
    registry: GraphRegistry,
    canonical_entity_id: str,
    merged_from: tuple[str, ...] = (),
) -> Optional[GraphNode]:
    e = session.get(db.MdmEntity, canonical_entity_id)
    if e is None:
        return None
    label = registry.labels_by_entity_type.get(e.entity_type, e.entity_type.title())
    return GraphNode(
        entity_id=canonical_entity_id,
        label=label,
        properties={"entity_type": e.entity_type, "is_quarantined": e.is_quarantined},
        merged_from=sorted(merged_from),
    )


def _merge_lineage(session: Session) -> dict[str, str]:
    """discarded_entity_id -> kept_entity_id (one hop), from mdm_change_log's
    merged_from records (RLINE-01). merge_entities() re-points source_refs and
    tombstones the discarded entity but never rewrites
    mdm_relationship_instance.source_entity_id/target_entity_id, so edges
    still reference the discarded id -- this is the lineage traversal needs
    to remap them at query time."""
    rows = session.scalars(
        select(db.MdmChangeLog).where(db.MdmChangeLog.changed_fields.is_not(None))
    ).all()
    lineage: dict[str, str] = {}
    for row in rows:
        fields = row.changed_fields or {}
        discarded = fields.get("merged_from")
        if discarded:
            lineage[str(discarded)] = row.entity_id
    return lineage


def _canonicalize(entity_id: str, lineage: dict[str, str], *, max_hops: int = 10) -> str:
    """Follow a (possibly multi-hop) merge chain to its final kept entity_id."""
    current = entity_id
    seen = {current}
    for _ in range(max_hops):
        nxt = lineage.get(current)
        if nxt is None or nxt in seen:
            break
        current = nxt
        seen.add(current)
    return current


def _canonical_groups(session: Session) -> tuple[dict[str, str], dict[str, set[str]]]:
    """Returns (raw_id -> canonical_id, canonical_id -> {raw ids merged into it})."""
    lineage = _merge_lineage(session)
    canonical_of: dict[str, str] = {}
    reverse: dict[str, set[str]] = {}
    for discarded in lineage:
        canonical = _canonicalize(discarded, lineage)
        canonical_of[discarded] = canonical
        reverse.setdefault(canonical, set()).add(discarded)
    return canonical_of, reverse


@router.get("/neighborhood/{entity_id}", response_model=Neighborhood)
def neighborhood(
    entity_id: str,
    depth: int = Query(default=1, ge=1, le=3),
    rel_types: Optional[str] = Query(default=None),
    as_of: Optional[date] = Query(default=None),
    include_unknown_dates: bool = Query(default=False),
    session: Session = Depends(get_db),
) -> Neighborhood:
    registry = _registry(session)
    types = _validate_rel_types(session, [t for t in (rel_types or "").split(",") if t])

    # RLINE-01: resolve every raw id to its canonical (post-merge) id, and
    # keep the reverse mapping so a canonical id in the frontier can still be
    # matched against relationship rows stored under a discarded raw id.
    canonical_of, discarded_by_canonical = _canonical_groups(session)

    def _canon(raw_id: str) -> str:
        return canonical_of.get(raw_id, raw_id)

    def _raw_ids_for(canonical_ids: set[str]) -> set[str]:
        expanded = set(canonical_ids)
        for cid in canonical_ids:
            expanded |= discarded_by_canonical.get(cid, set())
        return expanded

    seen_nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    canonical_entity_id = _canon(entity_id)
    frontier = {canonical_entity_id}
    rel_type_ids: list[str] = []
    if types:
        rel_type_ids = list(
            session.scalars(
                select(db.MdmRelationshipType.rel_type_id).where(
                    db.MdmRelationshipType.rel_type_name.in_(types)
                )
            ).all()
        )

    for _ in range(depth):
        if not frontier:
            break
        query_ids = _raw_ids_for(frontier)
        q = select(db.MdmRelationshipInstance).where(
            db.MdmRelationshipInstance.quarantined == False,
            (
                db.MdmRelationshipInstance.source_entity_id.in_(query_ids)
                | db.MdmRelationshipInstance.target_entity_id.in_(query_ids)
            ),
        )
        if rel_type_ids:
            q = q.where(db.MdmRelationshipInstance.rel_type_id.in_(rel_type_ids))
        if as_of is not None:
            # RTEMP-02: strict as_of_date traversal on the typed temporal
            # columns (valid_from_date/valid_to_date/date_provenance), not
            # the legacy effective_from/effective_to pair. Half-open
            # interval: inclusive start, exclusive end -- an edge ending
            # exactly on as_of is excluded, one starting exactly on as_of is
            # included. date_provenance == 'unknown' edges cannot prove
            # validity at any date, so they are excluded unless the caller
            # explicitly opts in via include_unknown_dates.
            #
            # is_active is intentionally NOT filtered here: a superseded
            # (is_active=False) version is exactly what "true at as_of_date"
            # can mean for a date in the past, before that version was
            # superseded -- excluding it would make historical traversal
            # silently see only whichever version happens to be current
            # today, defeating the point of a strict as_of query.
            bounds = (
                (db.MdmRelationshipInstance.valid_from_date.is_(None))
                | (db.MdmRelationshipInstance.valid_from_date <= as_of)
            ) & (
                (db.MdmRelationshipInstance.valid_to_date.is_(None))
                | (db.MdmRelationshipInstance.valid_to_date > as_of)
            )
            if include_unknown_dates:
                q = q.where(
                    (db.MdmRelationshipInstance.date_provenance == "unknown") | bounds
                )
            else:
                q = q.where(db.MdmRelationshipInstance.date_provenance != "unknown").where(bounds)
        else:
            # Current-by-default (no as_of): the pre-existing "live now"
            # contract -- only the currently active version of each
            # relationship, matching the neighborhood/traversal behavior
            # before this plan.
            q = q.where(db.MdmRelationshipInstance.is_active == True)
        rows = session.scalars(q).all()
        next_frontier: set[str] = set()
        for row in rows:
            rt_name = registry.rel_type_by_id[row.rel_type_id]["rel_type_name"]
            source_canonical = _canon(row.source_entity_id)
            target_canonical = _canon(row.target_entity_id)
            edges.append(
                GraphEdge(
                    source_entity_id=source_canonical,
                    target_entity_id=target_canonical,
                    rel_type=rt_name,
                    properties=row.properties or {},
                    effective_from=row.effective_from,
                    effective_to=row.effective_to,
                    source_entity_id_original=row.source_entity_id,
                    target_entity_id_original=row.target_entity_id,
                    valid_from_date=row.valid_from_date,
                    valid_to_date=row.valid_to_date,
                    date_provenance=row.date_provenance,
                    date_uncertain=(row.date_provenance == "unknown"),
                )
            )
            for ep in (source_canonical, target_canonical):
                if ep not in seen_nodes:
                    n = _node_for(session, registry, ep, tuple(discarded_by_canonical.get(ep, ())))
                    if n is not None:
                        seen_nodes[ep] = n
                if ep not in frontier:
                    next_frontier.add(ep)
        frontier = next_frontier

    if canonical_entity_id not in seen_nodes:
        n = _node_for(
            session,
            registry,
            canonical_entity_id,
            tuple(discarded_by_canonical.get(canonical_entity_id, ())),
        )
        if n is not None:
            seen_nodes[canonical_entity_id] = n

    return Neighborhood(nodes=list(seen_nodes.values()), edges=edges)


@router.post("/traversal", response_model=Neighborhood)
def traversal(
    body: TraversalRequest, session: Session = Depends(get_db)
) -> Neighborhood:
    _validate_rel_types(session, body.relationship_types)
    return neighborhood(
        entity_id=body.start_entity_id,
        depth=body.max_depth,
        rel_types=",".join(body.relationship_types) or None,
        as_of=body.as_of_date,
        include_unknown_dates=body.include_unknown_dates,
        session=session,
    )


@router.get("/connections/shared-insiders")
def shared_insiders(
    company_a: int,
    company_b: int,
    as_of: Optional[date] = Query(default=None),
    session: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    a = session.scalar(select(db.MdmCompany).where(db.MdmCompany.cik == company_a))
    b = session.scalar(select(db.MdmCompany).where(db.MdmCompany.cik == company_b))
    if a is None or b is None:
        raise HTTPException(404, "company not found")
    rt = session.scalar(
        select(db.MdmRelationshipType).where(db.MdmRelationshipType.rel_type_name == "IS_INSIDER")
    )
    if rt is None:
        return []

    def _ids_for(company_eid: str) -> set[str]:
        q = select(db.MdmRelationshipInstance.source_entity_id).where(
            db.MdmRelationshipInstance.rel_type_id == rt.rel_type_id,
            db.MdmRelationshipInstance.target_entity_id == company_eid,
            db.MdmRelationshipInstance.is_active == True,
        )
        if as_of is not None:
            q = q.where(
                (db.MdmRelationshipInstance.effective_from.is_(None))
                | (db.MdmRelationshipInstance.effective_from <= as_of)
            ).where(
                (db.MdmRelationshipInstance.effective_to.is_(None))
                | (db.MdmRelationshipInstance.effective_to > as_of)
            )
        return set(session.scalars(q).all())

    shared = _ids_for(a.entity_id) & _ids_for(b.entity_id)
    if not shared:
        return []
    persons = session.scalars(
        select(db.MdmPerson).where(db.MdmPerson.entity_id.in_(shared))
    ).all()
    return [{"entity_id": p.entity_id, "canonical_name": p.canonical_name} for p in persons]


@router.get("/sync-status", response_model=SyncStatus)
def sync_status(session: Session = Depends(get_db)) -> SyncStatus:
    rel_count = session.scalar(
        select(func.count(db.MdmRelationshipInstance.instance_id)).where(
            db.MdmRelationshipInstance.graph_synced_at.is_(None)
        )
    ) or 0
    return SyncStatus(pending_relationships=int(rel_count), pending_nodes=0)
