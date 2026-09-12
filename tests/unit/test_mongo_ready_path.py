"""Warehouse READY path: Mongo Decision Projection after aggregator (ticket 03).

Seams:
- ``run_ready_mongo_projection`` — public path: aggregator rollup, then publisher
- Aggregator / observe-only CLI stay free of Mongo writes
- Agent View still reads Snowflake Decision Contract objects only
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from edgar_warehouse.serving.subject_bundle_read import build_issuer_subject_bundle
from edgar_warehouse.serving.subject_feature_screen import build_subject_feature_screen
from edgar_warehouse.serving.watermark_aggregator import (
    MemoryAlignmentStore,
    StageObservation,
)


class _RaisingStore:
    def replace_document(self, database, collection, document) -> None:
        raise AssertionError("not-READY path must not write Mongo documents")

    def list_documents(self, database, collection):
        raise AssertionError("not-READY path must not read Mongo documents")


class _MemoryStore:
    def __init__(self) -> None:
        self._docs: dict[tuple[str, str, object], dict] = {}

    def replace_document(self, database: str, collection: str, document: dict) -> None:
        stored = dict(document)
        self._docs[(database, collection, stored["_id"])] = stored

    def list_documents(self, database: str, collection: str) -> list[dict]:
        return [
            dict(doc)
            for (db, col, _), doc in self._docs.items()
            if db == database and col == collection
        ]


def _complete(identity: str = "id-1") -> StageObservation:
    return StageObservation(complete=True, identity=identity)


def _incomplete() -> StageObservation:
    return StageObservation(complete=False)


def _watermark(**overrides):
    base = {
        "business_date": "2026-08-29",
        "gold_run_id": "g-1",
        "graph_generation_id": "gen-1",
        "silver_completeness_ok": True,
        "graph_parity_ok": True,
        "bronze_persist_used": False,
    }
    base.update(overrides)
    return base


def _issuer(cik: int = 320193, watermark=None):
    wm = watermark if watermark is not None else _watermark()
    bundle = build_issuer_subject_bundle(subject_cik=cik, watermark_components=wm)
    screen = build_subject_feature_screen(
        warehouse_active_ciks=(cik,),
        mdm_active_ciks=(cik,),
        period_rows=(),
        watermark_components=wm,
    )
    return {
        "subject_cik": cik,
        "bundle": bundle,
        "feature_screen_row": screen["rows"][0],
    }


class RunReadyMongoProjectionTests(unittest.TestCase):
    def test_incomplete_rollup_does_not_touch_mongo(self) -> None:
        from edgar_warehouse.serving.mongo_ready_path import run_ready_mongo_projection

        alignment = MemoryAlignmentStore()
        now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
        grade, result = run_ready_mongo_projection(
            _RaisingStore(),
            alignment_store=alignment,
            business_date="2026-08-29",
            cause_references=("cause-a",),
            silver=lambda _: _incomplete(),
            mdm=lambda _: _complete(),
            gold=lambda _: _complete("g-1"),
            graph=lambda _: _complete("gen-1"),
            issuers=(_issuer(),),
            now=now,
        )
        self.assertFalse(grade.agent_grade)
        self.assertEqual(result.documents_written, 0)
        self.assertEqual(result.documents_hidden, 0)
        self.assertEqual(result.skip_reason, "publication_not_ready")
        row = alignment.get("cause-a")
        self.assertIsNotNone(row)
        self.assertFalse(row.aligned)
        self.assertEqual(row.stuck_stage, "silver")

    def test_ready_rollup_projects_issuer_documents(self) -> None:
        from edgar_warehouse.serving.mongo_decision_projection import (
            COLLECTION_FEATURE_SCREEN,
            COLLECTION_ISSUER_BUNDLE,
            DATABASE_NAME,
        )
        from edgar_warehouse.serving.mongo_ready_path import run_ready_mongo_projection

        alignment = MemoryAlignmentStore()
        now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
        mongo = _MemoryStore()
        grade, result = run_ready_mongo_projection(
            mongo,
            alignment_store=alignment,
            business_date="2026-08-29",
            cause_references=("cause-a",),
            silver=lambda _: _complete(),
            mdm=lambda _: _complete(),
            gold=lambda _: _complete("g-1"),
            graph=lambda _: _complete("gen-1"),
            issuers=(_issuer(),),
            now=now,
        )
        self.assertTrue(grade.agent_grade)
        self.assertIsNone(result.skip_reason)
        self.assertEqual(result.documents_written, 2)
        bundles = mongo.list_documents(DATABASE_NAME, COLLECTION_ISSUER_BUNDLE)
        screens = mongo.list_documents(DATABASE_NAME, COLLECTION_FEATURE_SCREEN)
        self.assertEqual(len(bundles), 1)
        self.assertEqual(len(screens), 1)
        self.assertEqual(bundles[0]["_id"], 320193)
        self.assertEqual(bundles[0]["readiness_state"], "agent_ready")
        self.assertTrue(bundles[0]["agent_grade"])
        self.assertEqual(
            bundles[0]["decision_watermark"]["graph_generation_id"], "gen-1"
        )
        self.assertEqual(screens[0]["_id"], 320193)
        self.assertEqual(screens[0]["readiness_state"], "agent_ready")
