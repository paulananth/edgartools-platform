"""Pydantic schemas for graph endpoints."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel


class RelTypeOut(BaseModel):
    rel_type_name: str
    source_node_type: str
    target_node_type: str
    direction: str
    is_temporal: bool
    description: Optional[str] = None


class RelTypeDetail(RelTypeOut):
    properties: list[dict[str, Any]]


class GraphNode(BaseModel):
    entity_id: str
    label: str
    properties: dict[str, Any]
    # RLINE-01: entity_id is always the CANONICAL (post-merge) id -- traversal
    # converges a merged-away entity's edges onto the entity it was kept as.
    # merged_from lists every raw entity_id that canonically resolves here
    # (empty when this node was never a merge target), so callers can still
    # see the original identities behind a canonical node.
    merged_from: list[str] = []


class GraphEdge(BaseModel):
    source_entity_id: str
    target_entity_id: str
    rel_type: str
    properties: dict[str, Any]
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    # RLINE-01: canonical (post-merge) endpoints above; the raw MDM-stored
    # endpoints are preserved here for provenance even when unchanged.
    source_entity_id_original: Optional[str] = None
    target_entity_id_original: Optional[str] = None
    # RTEMP-02: strict typed temporal fields backing as_of_date filtering.
    valid_from_date: Optional[date] = None
    valid_to_date: Optional[date] = None
    date_provenance: Optional[str] = None
    # True when this edge was only returned because the caller passed
    # include_unknown_dates=True -- its validity at the requested as_of_date
    # could not be proven (date_provenance == 'unknown').
    date_uncertain: bool = False


class Neighborhood(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class TraversalRequest(BaseModel):
    start_entity_id: str
    relationship_types: list[str]
    direction: str = "both"
    max_depth: int = 2
    as_of_date: Optional[date] = None
    include_unknown_dates: bool = False
    filters: Optional[dict[str, Any]] = None


class SyncStatus(BaseModel):
    pending_relationships: int
    pending_nodes: int
