"""Ticket 30 contract tests for durable MDM run identity binding."""
from __future__ import annotations

import argparse
import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy import select

from edgar_warehouse.cli import build_parser
from edgar_warehouse.mdm import database as db
from edgar_warehouse.mdm.graph import GraphSyncEngine
from edgar_warehouse.mdm.resolvers.base import BaseResolver, ResolverContext
from edgar_warehouse.mdm.rules import MDMRuleEngine
from edgar_warehouse.mdm.stewardship import quarantine
from edgar_warehouse.mdm.survivorship import MergeResult


def _merge_result(entity_id: str, field_name: str, winning_value: str) -> MergeResult:
    return MergeResult(
        entity_id=entity_id,
        field_name=field_name,
        winning_value=winning_value,
        winning_stage_id=None,
        winning_source=None,
        rule_applied="test",
    )


def _make_entity(session, entity_type: str) -> str:
    entity_id = str(uuid.uuid4())
    session.add(db.MdmEntity(entity_id=entity_id, entity_type=entity_type))
    session.flush()
    return entity_id


def test_evidence_models_expose_nullable_run_identity_with_partial_indexes() -> None:
    for model, index_name in (
        (db.MdmChangeLog, "idx_change_log_run_id"),
        (db.MdmRelationshipInstance, "idx_rel_instance_run_id"),
    ):
        column = model.__table__.c.run_id
        assert column.nullable is True
        index = next(item for item in model.__table__.indexes if item.name == index_name)
        assert str(index.dialect_options["postgresql"]["where"]) == "run_id IS NOT NULL"


def test_resolver_change_evidence_preserves_operation_run_id(db_session) -> None:
    entity_id = _make_entity(db_session, "company")
    ctx = ResolverContext(
        session=db_session,
        engine=MDMRuleEngine.load(db_session),
        silver=MagicMock(),
        run_id="pipeline-run-123",
    )

    BaseResolver(entity_type="company")._log_change(
        ctx, entity_id, existing={}, merge_results={"name": _merge_result(entity_id, "name", "Issuer")}
    )
    db_session.flush()

    row = db_session.scalar(select(db.MdmChangeLog).where(db.MdmChangeLog.entity_id == entity_id))
    assert row is not None
    assert row.run_id == "pipeline-run-123"


def test_resolver_generates_one_identity_for_blank_context_and_reuses_it(db_session) -> None:
    first_entity_id = _make_entity(db_session, "company")
    second_entity_id = _make_entity(db_session, "company")
    ctx = ResolverContext(
        session=db_session,
        engine=MDMRuleEngine.load(db_session),
        silver=MagicMock(),
        run_id="   ",
    )
    resolver = BaseResolver(entity_type="company")

    resolver._log_change(
        ctx, first_entity_id, existing={}, merge_results={"name": _merge_result(first_entity_id, "name", "A")}
    )
    resolver._log_change(
        ctx, second_entity_id, existing={}, merge_results={"name": _merge_result(second_entity_id, "name", "B")}
    )
    db_session.flush()

    rows = list(db_session.scalars(select(db.MdmChangeLog).order_by(db.MdmChangeLog.entity_id)))
    assert len(rows) == 2
    assert rows[0].run_id == rows[1].run_id == ctx.run_id
    uuid.UUID(ctx.run_id)


def test_relationship_identity_is_immutable_origin_on_idempotent_rerun(db_session) -> None:
    adviser_id = _make_entity(db_session, "adviser")
    fund_id = _make_entity(db_session, "fund")
    db_session.commit()

    first_engine = GraphSyncEngine.build(db_session, run_id="relationship-run-1")
    first, created = first_engine.ensure_relationship("MANAGES_FUND", adviser_id, fund_id)
    db_session.commit()
    assert created is True
    assert first.run_id == "relationship-run-1"

    second_engine = GraphSyncEngine.build(db_session, run_id="relationship-run-2")
    second, created = second_engine.ensure_relationship("MANAGES_FUND", adviser_id, fund_id)
    db_session.commit()

    assert created is False
    assert second.instance_id == first.instance_id
    assert second.run_id == "relationship-run-1"


def test_manual_mutation_binds_explicit_run_identity(db_session) -> None:
    entity_id = _make_entity(db_session, "company")
    db_session.commit()

    quarantine(db_session, entity_id, run_id="manual-run-1")

    row = db_session.scalar(select(db.MdmChangeLog).where(db.MdmChangeLog.entity_id == entity_id))
    assert row is not None
    assert row.run_id == "manual-run-1"


def test_all_evidence_producing_pipeline_commands_accept_run_id() -> None:
    parser = build_parser()
    for command in (
        "mastering",
        "derive-relationships",
        "infer-relationships",
        "load-relationships",
    ):
        args = parser.parse_args(["mdm", command, "--run-id", "execution-123"])
        assert args.run_id == "execution-123"


def test_run_handler_normalizes_reports_and_propagates_identity(monkeypatch, capsys) -> None:
    import edgar_warehouse.mdm.cli as mdm_cli
    import edgar_warehouse.mdm.pipeline as mdm_pipeline

    fake_session = MagicMock()
    fake_bookkeeping = MagicMock()
    observed: dict[str, str] = {}
    monkeypatch.setattr(mdm_cli, "_require_silver_reader", lambda *_args: (object(), 0))
    monkeypatch.setattr(mdm_cli, "_session", lambda: fake_session)
    monkeypatch.setattr(mdm_cli, "_bookkeeping_store", lambda: fake_bookkeeping)

    class FakePipeline:
        def __init__(self, *, session, silver, run_id):
            assert session is fake_session
            observed["constructor"] = run_id

        def run_all(
            self,
            limit=None,
            *,
            resume_ledger_run_id=None,
            run_id=None,
            bookkeeping=None,
        ):
            assert bookkeeping is fake_bookkeeping
            observed["run_all"] = run_id
            return SimpleNamespace(
                companies_processed=0,
                advisers_processed=0,
                securities_processed=0,
                persons_processed=0,
                funds_processed=0,
                relationships_written=0,
                relationship_counts_by_type={},
                graph_nodes_synced=0,
                graph_edges_synced=0,
            )

    monkeypatch.setattr(mdm_pipeline, "MDMPipeline", FakePipeline)
    args = argparse.Namespace(
        entity_type="all",
        limit=None,
        cik=None,
        run_id="  explicit-execution  ",
        resume_ledger_run_id=None,
    )

    assert mdm_cli._handle_run(args) == 0
    assert observed == {
        "constructor": "explicit-execution",
        "run_all": "explicit-execution",
    }
    events = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    identity_event = next(event for event in events if event["event"] == "mdm_run_identity")
    assert identity_event["run_id"] == "explicit-execution"
    assert identity_event["source"] == "provided"


def test_run_handler_generates_uuid_for_blank_identity(monkeypatch, capsys) -> None:
    import edgar_warehouse.mdm.cli as mdm_cli
    import edgar_warehouse.mdm.pipeline as mdm_pipeline

    fake_session = MagicMock()
    fake_bookkeeping = MagicMock()
    observed: dict[str, str] = {}
    monkeypatch.setattr(mdm_cli, "_require_silver_reader", lambda *_args: (object(), 0))
    monkeypatch.setattr(mdm_cli, "_session", lambda: fake_session)
    monkeypatch.setattr(mdm_cli, "_bookkeeping_store", lambda: fake_bookkeeping)

    class FakePipeline:
        def __init__(self, *, session, silver, run_id):
            observed["run_id"] = run_id

        def run_all(
            self,
            limit=None,
            *,
            resume_ledger_run_id=None,
            run_id=None,
            bookkeeping=None,
        ):
            assert bookkeeping is fake_bookkeeping
            assert run_id == observed["run_id"]
            return SimpleNamespace()

    monkeypatch.setattr(mdm_pipeline, "MDMPipeline", FakePipeline)
    args = argparse.Namespace(
        entity_type="all",
        limit=None,
        cik=None,
        run_id="   ",
        resume_ledger_run_id=None,
    )

    assert mdm_cli._handle_run(args) == 0
    uuid.UUID(observed["run_id"])
    events = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    identity_event = next(event for event in events if event["event"] == "mdm_run_identity")
    assert identity_event["run_id"] == observed["run_id"]
    assert identity_event["source"] == "generated"


def test_derive_handler_passes_bound_identity(monkeypatch) -> None:
    import edgar_warehouse.mdm.cli as mdm_cli
    import edgar_warehouse.mdm.pipeline as mdm_pipeline

    fake_session = MagicMock()
    observed: dict[str, str] = {}
    monkeypatch.setattr(mdm_cli, "_require_silver_reader", lambda *_args: (object(), 0))
    monkeypatch.setattr(mdm_cli, "_session", lambda: fake_session)

    class FakePipeline:
        def __init__(self, *, session, silver, run_id):
            observed["run_id"] = run_id

        def derive_relationships(self, **_kwargs):
            return {}

    monkeypatch.setattr(mdm_pipeline, "MDMPipeline", FakePipeline)
    args = argparse.Namespace(
        target_per_type=10,
        relationship_type=None,
        cik=None,
        run_id="derive-run",
    )

    assert mdm_cli._handle_derive_relationships(args) == 0
    assert observed["run_id"] == "derive-run"


def test_load_handler_passes_bound_identity(monkeypatch) -> None:
    import edgar_warehouse.mdm.cli as mdm_cli
    import edgar_warehouse.mdm.pipeline as mdm_pipeline

    fake_session = MagicMock()
    observed: dict[str, str] = {}
    monkeypatch.setattr(mdm_cli, "_require_silver_reader", lambda *_args: (object(), 0))
    monkeypatch.setattr(mdm_cli, "_session", lambda: fake_session)

    class FakePipeline:
        def __init__(self, *, session, silver, run_id):
            observed["run_id"] = run_id

        def derive_relationships(self, **_kwargs):
            return {}

    monkeypatch.setattr(mdm_pipeline, "MDMPipeline", FakePipeline)
    args = argparse.Namespace(
        target_per_type=10,
        relationship_type=None,
        cik=None,
        run_id="load-run",
        entity_limit=None,
        skip_entity_resolution=True,
        graph_sync=False,
        skip_graph_sync=True,
    )

    assert mdm_cli._handle_load_relationships(args) == 0
    assert observed["run_id"] == "load-run"


def test_backfill_handler_passes_bound_identity(monkeypatch) -> None:
    import edgar_warehouse.mdm.cli as mdm_cli
    import edgar_warehouse.mdm.graph as mdm_graph

    fake_session = MagicMock()
    observed: dict[str, str] = {}
    monkeypatch.setattr(mdm_cli, "_session", lambda: fake_session)
    monkeypatch.setattr(mdm_cli, "_silver_reader", lambda: None)

    def fake_backfill(session, limit=None, run_id=None):
        observed["run_id"] = run_id
        return {"backfilled": 0, "synced": 0}

    monkeypatch.setattr(mdm_graph, "backfill_relationship_instances", fake_backfill)
    args = argparse.Namespace(limit=10, run_id="backfill-run")

    assert mdm_cli._handle_backfill_relationships(args) == 0
    assert observed["run_id"] == "backfill-run"
