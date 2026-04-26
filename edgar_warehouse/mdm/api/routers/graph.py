"""Graph endpoints — neighborhood, traversal, sync status.

The relationship-types listing reads the registry directly. The neighborhood
and traversal endpoints try Neo4j first; if Neo4j is unconfigured they
fall back to the PostgreSQL mirror (`mdm_relationship_instance`).
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm import database as db
from edgar_warehouse.mdm.api.deps import get_db, get_neo4j
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


def _node_for(session: Session, registry: GraphRegistry, entity_id: str) -> Optional[GraphNode]:
    e = session.get(db.MdmEntity, entity_id)
    if e is None:
        return None
    label = registry.labels_by_entity_type.get(e.entity_type, e.entity_type.title())
    return GraphNode(
        entity_id=entity_id,
        label=label,
        properties={"entity_type": e.entity_type, "is_quarantined": e.is_quarantined},
    )


@router.get("/neighborhood/{entity_id}", response_model=Neighborhood)
def neighborhood(
    entity_id: str,
    depth: int = Query(default=1, ge=1, le=3),
    rel_types: Optional[str] = Query(default=None),
    as_of: Optional[date] = Query(default=None),
    session: Session = Depends(get_db),
) -> Neighborhood:
    registry = _registry(session)
    types = _validate_rel_types(session, [t for t in (rel_types or "").split(",") if t])

    seen_nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    frontier = {entity_id}
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
        q = select(db.MdmRelationshipInstance).where(
            db.MdmRelationshipInstance.is_active == True,
            (
                db.MdmRelationshipInstance.source_entity_id.in_(frontier)
                | db.MdmRelationshipInstance.target_entity_id.in_(frontier)
            ),
        )
        if rel_type_ids:
            q = q.where(db.MdmRelationshipInstance.rel_type_id.in_(rel_type_ids))
        if as_of is not None:
            q = q.where(
                (db.MdmRelationshipInstance.effective_from.is_(None))
                | (db.MdmRelationshipInstance.effective_from <= as_of)
            ).where(
                (db.MdmRelationshipInstance.effective_to.is_(None))
                | (db.MdmRelationshipInstance.effective_to > as_of)
            )
        rows = session.scalars(q).all()
        next_frontier: set[str] = set()
        for row in rows:
            rt_name = registry.rel_type_by_id[row.rel_type_id]["rel_type_name"]
            edges.append(
                GraphEdge(
                    source_entity_id=row.source_entity_id,
                    target_entity_id=row.target_entity_id,
                    rel_type=rt_name,
                    properties=row.properties or {},
                    effective_from=row.effective_from,
                    effective_to=row.effective_to,
                )
            )
            for ep in (row.source_entity_id, row.target_entity_id):
                if ep not in seen_nodes:
                    n = _node_for(session, registry, ep)
                    if n is not None:
                        seen_nodes[ep] = n
                if ep not in frontier:
                    next_frontier.add(ep)
        frontier = next_frontier

    if entity_id not in seen_nodes:
        n = _node_for(session, registry, entity_id)
        if n is not None:
            seen_nodes[entity_id] = n

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
