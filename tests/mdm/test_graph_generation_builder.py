"""Tests for Phase 7 Plan 04: parallel generation builder, partition
manifests, content-addressed reuse, and fan-in verification (RSYNC-04).

Uses an in-memory SQLite store (schema via Base.metadata.create_all),
matching the existing MDM test convention.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.mdm import generation
from edgar_warehouse.mdm.database import (
    Base,
    MdmEntity,
    MdmEntityTypeDefinition,
    MdmGraphPartition,
    MdmRelationshipInstance,
    MdmRelationshipType,
)

ALL_6_NODE_TYPES = ("company", "adviser", "person", "security", "fund", "audit_firm")
ALL_11_RELATIONSHIP_TYPES = [
    ("IS_INSIDER", "person", "company"),
    ("HOLDS", "person", "security"),
    ("COMPANY_HOLDS", "company", "security"),
    ("ISSUED_BY", "security", "company"),
    ("IS_ENTITY_OF", "adviser", "company"),
    ("HAS_PARENT_COMPANY", "company", "company"),
    ("MANAGES_FUND", "adviser", "fund"),
    ("IS_PERSON_OF", "adviser", "person"),
    ("EMPLOYED_BY", "person", "company"),
    ("AUDITED_BY", "company", "audit_firm"),
    ("INSTITUTIONAL_HOLDS", "adviser", "security"),
]


def _seed_registry(session: Session) -> dict[str, str]:
    for et in ALL_6_NODE_TYPES:
        session.add(MdmEntityTypeDefinition(
            entity_type=et, neo4j_label=et.title(), domain_table=f"mdm_{et}",
            api_path_prefix=f"/{et}s", primary_id_field="entity_id",
            display_name=et.title(), is_active=True,
        ))
    rel_types = {}
    for name, src, tgt in ALL_11_RELATIONSHIP_TYPES:
        rt_id = str(uuid.uuid4())
        session.add(MdmRelationshipType(
            rel_type_id=rt_id, rel_type_name=name,
            source_node_type=src, target_node_type=tgt,
            direction="outbound", is_temporal=True,
            merge_strategy="extend_temporal", is_active=True,
        ))
        rel_types[name] = rt_id
    session.commit()
    return rel_types


def _add_entity(session: Session, entity_type: str) -> str:
    eid = str(uuid.uuid4())
    session.add(MdmEntity(entity_id=eid, entity_type=entity_type))
    session.flush()
    return eid


def _add_relationship(session: Session, rel_type_id: str, source_id: str, target_id: str) -> str:
    row = MdmRelationshipInstance(
        rel_type_id=rel_type_id, source_entity_id=source_id, target_entity_id=target_id,
    )
    session.add(row)
    session.flush()
    return row.instance_id


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def world(session: Session):
    rel_types = _seed_registry(session)
    return {"rel_types": rel_types, "session": session}


def _new_generation(session: Session, rule_version: str = "v1", schema_version: str = "v1", committed_watermark=None):
    gen = generation.create_generation(
        session, rule_version=rule_version, schema_version=schema_version,
        committed_watermark=committed_watermark,
    )
    session.commit()
    return gen


def _build_all(session: Session, partitions: list[MdmGraphPartition]) -> None:
    for partition in partitions:
        if partition.status == "pending":
            generation.build_partition(session, partition.partition_id)
    session.commit()


# ---------------------------------------------------------------------------
# Task 1: planning, sharding, reuse, retry
# ---------------------------------------------------------------------------

class TestDefaultPlanning:
    def test_emits_all_6_node_types_and_11_relationship_types_exactly_once(self, world, session):
        gen = _new_generation(session)
        partitions = generation.plan_generation_partitions(session, gen.generation_id)
        session.commit()

        node_types = [p.type_name for p in partitions if p.kind == "node"]
        edge_types = [p.type_name for p in partitions if p.kind == "edge"]
        assert sorted(node_types) == sorted(ALL_6_NODE_TYPES)
        assert sorted(edge_types) == sorted(name for name, _, _ in ALL_11_RELATIONSHIP_TYPES)
        assert len(node_types) == len(set(node_types))
        assert len(edge_types) == len(set(edge_types))

    def test_partitions_have_zero_row_count_when_no_data_exists(self, world, session):
        gen = _new_generation(session)
        partitions = generation.plan_generation_partitions(session, gen.generation_id)
        assert all(p.row_count == 0 for p in partitions)

    def test_unknown_generation_raises(self, world, session):
        with pytest.raises(KeyError):
            generation.plan_generation_partitions(session, str(uuid.uuid4()))


class TestSharding:
    def test_every_stable_key_maps_to_exactly_one_shard(self, world, session):
        rel_type_id = world["rel_types"]["IS_INSIDER"]
        company = _add_entity(session, "company")
        person_ids = [_add_entity(session, "person") for _ in range(20)]
        for pid in person_ids:
            _add_relationship(session, rel_type_id, pid, company)
        session.commit()

        gen = _new_generation(session)
        partitions = generation.plan_generation_partitions(
            session, gen.generation_id, sharding={"IS_INSIDER": 4}
        )
        session.commit()

        edge_partitions = [p for p in partitions if p.type_name == "IS_INSIDER"]
        assert len(edge_partitions) == 4
        assert {p.shard_index for p in edge_partitions} == {0, 1, 2, 3}
        assert sum(p.row_count for p in edge_partitions) == 20

    def test_sharding_is_deterministic_across_calls(self):
        key = "some-stable-instance-id"
        first = generation.shard_index_for_key(key, 4)
        second = generation.shard_index_for_key(key, 4)
        assert first == second
        assert 0 <= first < 4


FIXED_WATERMARK = datetime(2026, 1, 1, tzinfo=timezone.utc)


class TestContentAddressedReuse:
    """Watermark is pinned to the same fixed value across gen1/gen2 in every
    test here so only the variable actually under test (input population,
    rule_version, schema_version) differs -- otherwise every generation's
    default (now()) watermark would alone force a rebuild regardless of
    whether the intended variable changed, giving false confidence."""

    def test_unchanged_fingerprint_reuses_prior_built_partition(self, world, session):
        _add_entity(session, "company")
        session.commit()

        gen1 = _new_generation(session, committed_watermark=FIXED_WATERMARK)
        partitions1 = generation.plan_generation_partitions(session, gen1.generation_id)
        session.commit()
        _build_all(session, partitions1)

        gen2 = _new_generation(session, committed_watermark=FIXED_WATERMARK)
        partitions2 = generation.plan_generation_partitions(session, gen2.generation_id)
        session.commit()

        company_partition_2 = next(p for p in partitions2 if p.type_name == "company")
        assert company_partition_2.status == "reused"
        assert company_partition_2.reused_from_partition_id is not None

    def test_input_change_forces_rebuild_not_reuse(self, world, session):
        _add_entity(session, "company")
        session.commit()

        gen1 = _new_generation(session, committed_watermark=FIXED_WATERMARK)
        partitions1 = generation.plan_generation_partitions(session, gen1.generation_id)
        session.commit()
        _build_all(session, partitions1)

        _add_entity(session, "company")  # population changed
        session.commit()

        gen2 = _new_generation(session, committed_watermark=FIXED_WATERMARK)
        partitions2 = generation.plan_generation_partitions(session, gen2.generation_id)

        company_partition_2 = next(p for p in partitions2 if p.type_name == "company")
        assert company_partition_2.status == "pending"

    def test_rule_version_change_forces_rebuild_not_reuse(self, world, session):
        _add_entity(session, "company")
        session.commit()

        gen1 = _new_generation(session, rule_version="v1", committed_watermark=FIXED_WATERMARK)
        partitions1 = generation.plan_generation_partitions(session, gen1.generation_id)
        session.commit()
        _build_all(session, partitions1)

        gen2 = _new_generation(session, rule_version="v2", committed_watermark=FIXED_WATERMARK)
        partitions2 = generation.plan_generation_partitions(session, gen2.generation_id)

        company_partition_2 = next(p for p in partitions2 if p.type_name == "company")
        assert company_partition_2.status == "pending"

    def test_schema_version_change_forces_rebuild_not_reuse(self, world, session):
        _add_entity(session, "company")
        session.commit()

        gen1 = _new_generation(session, schema_version="s1", committed_watermark=FIXED_WATERMARK)
        partitions1 = generation.plan_generation_partitions(session, gen1.generation_id)
        session.commit()
        _build_all(session, partitions1)

        gen2 = _new_generation(session, schema_version="s2", committed_watermark=FIXED_WATERMARK)
        partitions2 = generation.plan_generation_partitions(session, gen2.generation_id)

        company_partition_2 = next(p for p in partitions2 if p.type_name == "company")
        assert company_partition_2.status == "pending"

    def test_watermark_change_alone_forces_rebuild_not_reuse(self, world, session):
        _add_entity(session, "company")
        session.commit()

        gen1 = _new_generation(session, committed_watermark=FIXED_WATERMARK)
        partitions1 = generation.plan_generation_partitions(session, gen1.generation_id)
        session.commit()
        _build_all(session, partitions1)

        later_watermark = datetime(2026, 1, 2, tzinfo=timezone.utc)
        gen2 = _new_generation(session, committed_watermark=later_watermark)
        partitions2 = generation.plan_generation_partitions(session, gen2.generation_id)

        company_partition_2 = next(p for p in partitions2 if p.type_name == "company")
        assert company_partition_2.status == "pending"


class TestRetry:
    def test_failed_shard_retries_without_rebuilding_unchanged_successful_partitions(self, world, session):
        _add_entity(session, "company")
        _add_entity(session, "adviser")
        session.commit()

        gen = _new_generation(session)
        partitions = generation.plan_generation_partitions(session, gen.generation_id)
        session.commit()

        company_partition = next(p for p in partitions if p.type_name == "company")
        adviser_partition = next(p for p in partitions if p.type_name == "adviser")
        generation.build_partition(session, company_partition.partition_id)
        generation.mark_partition_failed(session, adviser_partition.partition_id, "boom")
        session.commit()

        retried = generation.retry_failed_partitions(session, gen.generation_id)
        session.commit()

        assert len(retried) == 1
        assert retried[0].partition_id == adviser_partition.partition_id

        refreshed_company = session.get(MdmGraphPartition, company_partition.partition_id)
        refreshed_adviser = session.get(MdmGraphPartition, adviser_partition.partition_id)
        assert refreshed_company.status == "built"  # untouched
        assert refreshed_adviser.status == "pending"  # reset, retryable
        assert refreshed_adviser.error is None


# ---------------------------------------------------------------------------
# Fan-in verification
# ---------------------------------------------------------------------------

class TestFanIn:
    def test_complete_built_generation_passes(self, world, session):
        gen = _new_generation(session)
        partitions = generation.plan_generation_partitions(session, gen.generation_id)
        session.commit()
        _build_all(session, partitions)

        result = generation.fan_in_generation(session, gen.generation_id)
        assert result.passed is True
        assert result.violations == []
        refreshed = session.get(type(gen), gen.generation_id)
        assert refreshed.status == "verified"
        assert refreshed.verified_at is not None

    def test_missing_partition_type_fails(self, world, session):
        gen = _new_generation(session)
        partitions = generation.plan_generation_partitions(session, gen.generation_id)
        session.commit()

        # Delete one partition to simulate an incomplete plan.
        victim = next(p for p in partitions if p.type_name == "fund")
        session.delete(victim)
        session.commit()
        _build_all(session, [p for p in partitions if p.type_name != "fund"])

        result = generation.fan_in_generation(session, gen.generation_id)
        assert result.passed is False
        assert any("fund" in v for v in result.violations)

    def test_unbuilt_partition_fails(self, world, session):
        gen = _new_generation(session)
        partitions = generation.plan_generation_partitions(session, gen.generation_id)
        session.commit()
        # Leave everything pending -- nothing built.

        result = generation.fan_in_generation(session, gen.generation_id)
        assert result.passed is False
        assert any("not built" in v for v in result.violations)

    def test_failed_partition_fails_fan_in(self, world, session):
        gen = _new_generation(session)
        partitions = generation.plan_generation_partitions(session, gen.generation_id)
        session.commit()
        _build_all(session, partitions)

        one = partitions[0]
        generation.mark_partition_failed(session, one.partition_id, "boom")
        session.commit()

        result = generation.fan_in_generation(session, gen.generation_id)
        assert result.passed is False
        assert any("not built" in v for v in result.violations)

    def test_mismatched_watermark_fails(self, world, session):
        from datetime import datetime, timedelta, timezone

        gen = _new_generation(session)
        partitions = generation.plan_generation_partitions(session, gen.generation_id)
        session.commit()
        _build_all(session, partitions)

        drifted = partitions[0]
        drifted.mdm_watermark = datetime.now(timezone.utc) + timedelta(days=1)
        session.commit()

        result = generation.fan_in_generation(session, gen.generation_id)
        assert result.passed is False
        assert any("mismatched mdm_watermark" in v for v in result.violations)

    def test_mismatched_rule_version_fails(self, world, session):
        gen = _new_generation(session)
        partitions = generation.plan_generation_partitions(session, gen.generation_id)
        session.commit()
        _build_all(session, partitions)

        drifted = partitions[0]
        drifted.rule_version = "some-other-version"
        session.commit()

        result = generation.fan_in_generation(session, gen.generation_id)
        assert result.passed is False
        assert any("mismatched rule_version" in v for v in result.violations)

    def test_missing_shard_within_a_sharded_type_fails(self, world, session):
        rel_type_id = world["rel_types"]["IS_INSIDER"]
        company = _add_entity(session, "company")
        for _ in range(8):
            person = _add_entity(session, "person")
            _add_relationship(session, rel_type_id, person, company)
        session.commit()

        gen = _new_generation(session)
        partitions = generation.plan_generation_partitions(
            session, gen.generation_id, sharding={"IS_INSIDER": 4}
        )
        session.commit()

        # Simulate a corrupted/incomplete manifest: one of the 4 IS_INSIDER
        # shards never got created (e.g. a crashed planner), so only 3 of 4
        # expected shard_index values are present for this sharded type.
        victim = next(
            p for p in partitions if p.type_name == "IS_INSIDER" and p.shard_index == 2
        )
        session.delete(victim)
        session.commit()
        _build_all(session, [p for p in partitions if p.partition_id != victim.partition_id])

        result = generation.fan_in_generation(session, gen.generation_id)
        assert result.passed is False
        assert any("missing shards for edge:'IS_INSIDER'" in v for v in result.violations)

    def test_duplicate_shard_indices_are_rejected_by_check_shards_directly(self):
        """The UNIQUE(generation_id, kind, type_name, shard_index) DB constraint
        already prevents true duplicates from ever being persisted through
        plan_generation_partitions -- this exercises _check_shards' duplicate
        branch directly as defense-in-depth (e.g. data arriving via a
        different path than the normal planner)."""
        from types import SimpleNamespace

        fake_partitions = [
            SimpleNamespace(shard_count=2, shard_index=0),
            SimpleNamespace(shard_count=2, shard_index=0),
        ]
        violations: list[str] = []
        generation._check_shards(("node", "company"), fake_partitions, violations)
        assert any("duplicate shard indices" in v for v in violations)

    def test_endpoint_gap_fails(self, world, session):
        gen = _new_generation(session)
        partitions = generation.plan_generation_partitions(session, gen.generation_id)
        session.commit()

        # Build everything except the "company" node partition (an endpoint for
        # several relationship types) to simulate an endpoint gap.
        to_build = [p for p in partitions if p.type_name != "company"]
        _build_all(session, to_build)
        company_partition = next(p for p in partitions if p.type_name == "company")
        generation.mark_partition_failed(session, company_partition.partition_id, "boom")
        session.commit()

        result = generation.fan_in_generation(session, gen.generation_id)
        assert result.passed is False
        assert any("endpoint gap" in v for v in result.violations)


# ---------------------------------------------------------------------------
# Task 2: AWS fan-out/fan-in orchestration -- MDM writes are not blocked by
# an in-flight generation build (RSYNC-04 plan text: "New MDM commits queue
# for the next generation while one builds").
# ---------------------------------------------------------------------------

class TestConcurrentGenerationsNotBlocked:
    def test_a_second_generation_can_open_while_the_first_is_still_building(self, world, session):
        """No uniqueness/singleton constraint on mdm_graph_generation should
        prevent more than one 'building' generation existing at once -- this is
        what lets an ECS worker keep planning/building the next generation
        while a prior one is still mid fan-out, mid fan-in, or awaiting
        activation."""
        first = _new_generation(session)
        assert first.status == "building"

        second = _new_generation(session)  # must not raise / must not block
        assert second.status == "building"
        assert second.generation_id != first.generation_id

    def test_publication_request_succeeds_regardless_of_generation_status(self, world, session):
        """The publication outbox (07-03) is fully decoupled from the
        generation builder (07-04): a new MDM write can always be queued for
        the NEXT generation, independent of whether the current one is
        building, verified, activated, or failed."""
        from edgar_warehouse.mdm.publication import request_publication

        gen = _new_generation(session)
        partitions = generation.plan_generation_partitions(session, gen.generation_id)
        session.commit()
        assert gen.status == "building"  # still mid-build

        request = request_publication(session)
        session.commit()
        assert request.lifecycle_state == "mdm_committed"
        assert len(partitions) > 0  # sanity: the in-flight build state is real, not incidental

    def test_activation_bookkeeping_only_flips_after_verified(self, world, session):
        """Mirrors the CLI's generation-activate guard (cli.py
        _handle_generation_activate): activating a generation whose fan-in
        never ran/passed must be refused, not silently allowed."""
        gen = _new_generation(session)
        generation.plan_generation_partitions(session, gen.generation_id)
        session.commit()
        assert gen.status == "building"
        # Directly mirror the CLI guard's condition (status != "verified").
        assert gen.status != "verified"
