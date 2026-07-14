"""Parallel graph generation builder: partition planning, content-addressed
reuse, and fan-in verification (07-04, RSYNC-04).

One immutable partition per active node (entity) type and one per active
relationship type by default; configured high-volume types can be
hash-sharded across multiple partitions. Each partition's content address
(kind, type, shard, MDM watermark, rule/schema version, input fingerprint)
determines whether a prior generation's built output can be reused instead
of rebuilt. Fan-in verifies the complete set before a generation is marked
``verified`` -- activation (the shared Snowflake pointer) is 07-05's scope.

Building a partition's actual Snowflake rows is out of this module's scope
(existing ``snowflake_graph.py``/``SnowflakeGraphSyncExecutor`` machinery
does that); ``build_partition`` here only tracks the MDM-side manifest state
an ECS worker would drive.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import (
    MdmEntity,
    MdmEntityTypeDefinition,
    MdmGraphGeneration,
    MdmGraphPartition,
    MdmRelationshipInstance,
    MdmRelationshipType,
)

BUILT_STATUSES = ("built", "reused")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _sha256(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def shard_index_for_key(key: str, shard_count: int) -> int:
    """Deterministic hash-mod shard assignment for a stable source key."""
    if shard_count <= 1:
        return 0
    return int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % shard_count


def create_generation(
    session: Session,
    *,
    rule_version: str,
    schema_version: str,
    committed_watermark: Optional[datetime] = None,
) -> MdmGraphGeneration:
    """Freeze a committed MDM watermark and open a new generation in 'building'."""
    generation = MdmGraphGeneration(
        status="building",
        committed_watermark=committed_watermark or _utcnow(),
        rule_version=rule_version,
        schema_version=schema_version,
    )
    session.add(generation)
    session.flush()
    return generation


def _active_entity_types(session: Session) -> list[str]:
    return sorted(
        session.scalars(
            select(MdmEntityTypeDefinition.entity_type).where(
                MdmEntityTypeDefinition.is_active == True
            )
        )
    )


def _active_relationship_types(session: Session) -> list[MdmRelationshipType]:
    return list(
        session.scalars(
            select(MdmRelationshipType).where(MdmRelationshipType.is_active == True)
        )
    )


def _node_stable_keys(session: Session, entity_type: str) -> list[str]:
    return sorted(
        session.scalars(
            select(MdmEntity.entity_id).where(
                MdmEntity.entity_type == entity_type,
                MdmEntity.is_quarantined == False,
            )
        )
    )


def _edge_stable_keys(session: Session, rel_type_id: str) -> list[tuple[str, dict]]:
    """Return (instance_id, properties) for every current version of this type.

    "Current" matches 07-01's definition: active, non-quarantined, not
    superseded -- the same set graph sync treats as live edges.
    """
    rows = session.scalars(
        select(MdmRelationshipInstance).where(
            MdmRelationshipInstance.rel_type_id == rel_type_id,
            MdmRelationshipInstance.is_active == True,
            MdmRelationshipInstance.quarantined == False,
            MdmRelationshipInstance.superseded_by_version_id.is_(None),
        )
    )
    return sorted(
        ((row.instance_id, row.properties or {}) for row in rows),
        key=lambda item: item[0],
    )


def _make_partition(
    session: Session,
    *,
    generation: MdmGraphGeneration,
    kind: str,
    type_name: str,
    shard_index: int,
    shard_count: int,
    stable_keys: list[str],
    property_repr: str,
) -> MdmGraphPartition:
    watermark_iso = _as_aware(generation.committed_watermark).isoformat()
    input_fingerprint = _sha256(*stable_keys)
    content_hash = _sha256(
        kind, type_name, str(shard_index), watermark_iso,
        generation.rule_version, generation.schema_version, input_fingerprint,
    )
    partition = MdmGraphPartition(
        generation_id=generation.generation_id,
        kind=kind,
        type_name=type_name,
        shard_index=shard_index,
        shard_count=shard_count,
        mdm_watermark=generation.committed_watermark,
        rule_version=generation.rule_version,
        schema_version=generation.schema_version,
        input_fingerprint=input_fingerprint,
        content_hash=content_hash,
        row_count=len(stable_keys),
        stable_key_hash=_sha256(*stable_keys),
        property_hash=_sha256(property_repr),
        status="pending",
    )
    session.add(partition)
    session.flush()
    _apply_reuse_if_available(session, partition)
    return partition


def _apply_reuse_if_available(session: Session, partition: MdmGraphPartition) -> None:
    """Reuse only an exact content-address match from a prior BUILT partition."""
    prior = session.scalars(
        select(MdmGraphPartition)
        .where(
            MdmGraphPartition.content_hash == partition.content_hash,
            MdmGraphPartition.partition_id != partition.partition_id,
            MdmGraphPartition.status == "built",
        )
        .order_by(MdmGraphPartition.created_at.desc())
    ).first()
    if prior is None:
        return
    partition.status = "reused"
    partition.reused_from_partition_id = prior.partition_id
    partition.row_count = prior.row_count
    partition.stable_key_hash = prior.stable_key_hash
    partition.property_hash = prior.property_hash
    partition.updated_at = _utcnow()
    session.flush()


def plan_generation_partitions(
    session: Session,
    generation_id: str,
    *,
    sharding: Optional[dict[str, int]] = None,
) -> list[MdmGraphPartition]:
    """Create one partition per active node/relationship type (default), or N
    hash-sharded partitions for any type name in ``sharding``."""
    generation = session.get(MdmGraphGeneration, generation_id)
    if generation is None:
        raise KeyError(f"No mdm_graph_generation with generation_id={generation_id}")
    sharding = sharding or {}
    partitions: list[MdmGraphPartition] = []

    for entity_type in _active_entity_types(session):
        shard_count = max(1, sharding.get(entity_type, 1))
        keys = _node_stable_keys(session, entity_type)
        for shard_index in range(shard_count):
            shard_keys = [k for k in keys if shard_index_for_key(k, shard_count) == shard_index]
            partitions.append(_make_partition(
                session, generation=generation, kind="node", type_name=entity_type,
                shard_index=shard_index, shard_count=shard_count,
                stable_keys=shard_keys, property_repr=_sha256(*shard_keys),
            ))

    for rel_type in _active_relationship_types(session):
        shard_count = max(1, sharding.get(rel_type.rel_type_name, 1))
        edges = _edge_stable_keys(session, rel_type.rel_type_id)
        for shard_index in range(shard_count):
            shard_edges = [
                e for e in edges if shard_index_for_key(e[0], shard_count) == shard_index
            ]
            shard_keys = [instance_id for instance_id, _ in shard_edges]
            property_repr = _sha256(*(
                f"{instance_id}:{sorted(props.items())}" for instance_id, props in shard_edges
            ))
            partitions.append(_make_partition(
                session, generation=generation, kind="edge", type_name=rel_type.rel_type_name,
                shard_index=shard_index, shard_count=shard_count,
                stable_keys=shard_keys, property_repr=property_repr,
            ))

    return partitions


def build_partition(session: Session, partition_id: str) -> MdmGraphPartition:
    """Mark a pending partition built.

    The actual Snowflake row write is existing snowflake_graph.py/
    SnowflakeGraphSyncExecutor machinery (an ECS worker invokes both); this
    function only advances the MDM-side manifest state that machinery reports
    back through.
    """
    partition = session.get(MdmGraphPartition, partition_id)
    if partition is None:
        raise KeyError(f"No mdm_graph_partition with partition_id={partition_id}")
    if partition.status == "reused":
        return partition
    partition.status = "built"
    partition.updated_at = _utcnow()
    session.flush()
    return partition


def mark_partition_failed(session: Session, partition_id: str, error: str) -> MdmGraphPartition:
    partition = session.get(MdmGraphPartition, partition_id)
    if partition is None:
        raise KeyError(f"No mdm_graph_partition with partition_id={partition_id}")
    partition.status = "failed"
    partition.error = error
    partition.updated_at = _utcnow()
    session.flush()
    return partition


def retry_failed_partitions(session: Session, generation_id: str) -> list[MdmGraphPartition]:
    """Reset only failed partitions to pending; built/reused partitions are untouched."""
    failed = list(
        session.scalars(
            select(MdmGraphPartition).where(
                MdmGraphPartition.generation_id == generation_id,
                MdmGraphPartition.status == "failed",
            )
        )
    )
    for partition in failed:
        partition.status = "pending"
        partition.error = None
        partition.updated_at = _utcnow()
    session.flush()
    return failed


@dataclass(frozen=True)
class FanInResult:
    passed: bool
    violations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "violations": list(self.violations)}


def fan_in_generation(session: Session, generation_id: str) -> FanInResult:
    """Verify a generation's partitions are complete, consistent, and built.

    Rejects: missing/duplicate shards, mixed watermarks/rule/schema versions,
    endpoint gaps (an edge type's source/target node type isn't present and
    built), and any partition not yet built/reused (pending/building/failed).
    """
    generation = session.get(MdmGraphGeneration, generation_id)
    if generation is None:
        raise KeyError(f"No mdm_graph_generation with generation_id={generation_id}")

    partitions = list(
        session.scalars(
            select(MdmGraphPartition).where(MdmGraphPartition.generation_id == generation_id)
        )
    )
    violations: list[str] = []

    expected_node_types = set(_active_entity_types(session))
    expected_edge_types = {rt.rel_type_name: rt for rt in _active_relationship_types(session)}

    by_type: dict[tuple[str, str], list[MdmGraphPartition]] = {}
    for partition in partitions:
        by_type.setdefault((partition.kind, partition.type_name), []).append(partition)

    for entity_type in expected_node_types:
        _check_shards(("node", entity_type), by_type.get(("node", entity_type), []), violations)
    for rel_type_name in expected_edge_types:
        _check_shards(("edge", rel_type_name), by_type.get(("edge", rel_type_name), []), violations)

    present_types = {key[1] for key in by_type}
    for missing in sorted(expected_node_types - present_types):
        violations.append(f"missing node partition for entity_type={missing!r}")
    for missing in sorted(set(expected_edge_types) - present_types):
        violations.append(f"missing edge partition for relationship_type={missing!r}")

    watermark_iso = _as_aware(generation.committed_watermark).isoformat()
    for partition in partitions:
        if _as_aware(partition.mdm_watermark).isoformat() != watermark_iso:
            violations.append(f"partition {partition.partition_id} has a mismatched mdm_watermark")
        if partition.rule_version != generation.rule_version:
            violations.append(f"partition {partition.partition_id} has a mismatched rule_version")
        if partition.schema_version != generation.schema_version:
            violations.append(f"partition {partition.partition_id} has a mismatched schema_version")
        if partition.status not in BUILT_STATUSES:
            violations.append(
                f"partition {partition.partition_id} ({partition.kind}:{partition.type_name}) "
                f"is not built (status={partition.status!r})"
            )

    built_node_types = {
        partition.type_name for partition in partitions
        if partition.kind == "node" and partition.status in BUILT_STATUSES
    }
    for rel_type_name, rel_type in expected_edge_types.items():
        if rel_type_name not in present_types:
            continue
        for endpoint in (rel_type.source_node_type, rel_type.target_node_type):
            if endpoint not in built_node_types:
                violations.append(
                    f"endpoint gap: {rel_type_name!r} references node type {endpoint!r} "
                    "which has no built/reused node partition in this generation"
                )

    passed = not violations
    generation.status = "verified" if passed else "failed"
    generation.failure_reasons = violations or None
    if passed:
        generation.verified_at = _utcnow()
    session.flush()
    return FanInResult(passed=passed, violations=violations)


def _check_shards(
    key: tuple[str, str], partitions: list[MdmGraphPartition], violations: list[str]
) -> None:
    if not partitions:
        return  # reported separately as a missing-type violation
    shard_count = partitions[0].shard_count
    shard_indices = [p.shard_index for p in partitions]
    if len(shard_indices) != len(set(shard_indices)):
        violations.append(f"duplicate shard indices for {key[0]}:{key[1]!r}: {shard_indices}")
    expected_indices = set(range(shard_count))
    actual_indices = set(shard_indices)
    if actual_indices != expected_indices:
        violations.append(
            f"missing shards for {key[0]}:{key[1]!r}: expected {sorted(expected_indices)}, "
            f"got {sorted(actual_indices)}"
        )
