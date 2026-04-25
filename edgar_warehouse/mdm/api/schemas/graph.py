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


class GraphEdge(BaseModel):
    source_entity_id: str
    target_entity_id: str
    rel_type: str
    properties: dict[str, Any]
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


class Neighborhood(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class TraversalRequest(BaseModel):
    start_entity_id: str
    relationship_types: list[str]
    direction: str = "both"
    max_depth: int = 2
    as_of_date: Optional[date] = None
    filters: Optional[dict[str, Any]] = None


class SyncStatus(BaseModel):
    pending_relationships: int
    pending_nodes: int
