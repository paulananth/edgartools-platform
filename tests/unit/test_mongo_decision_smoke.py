"""Operator M0 smoke (ticket 04): mocked stores, no Atlas."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from edgar_warehouse.serving.mongo_decision_store import PyMongoDecisionStore
from edgar_warehouse.serving.subject_bundle_read import build_issuer_subject_bundle
from edgar_warehouse.serving.subject_feature_screen import build_subject_feature_screen
from edgar_warehouse.serving.watermark_aggregator import (
    MemoryAlignmentStore,
    StageObservation,
)
from tests.unit.test_mongo_decision_store import _FakeClient


class _RoleStore:
    """Publisher may write; agent may only list — same cluster, different users."""

    def __init__(self, inner: PyMongoDecisionStore, *, can_write: bool) -> None:
        self._inner = inner
        self._can_write = can_write

    def replace_document(self, database, collection, document) -> None:
        if not self._can_write:
            raise PermissionError("not authorized on this resource")
        self._inner.replace_document(database, collection, document)

    def list_documents(self, database, collection):
        return self._inner.list_documents(database, collection)

    def find_document(self, database, collection, document_id):
        return self._inner.find_document(database, collection, document_id)


def _complete(identity: str = "g-1") -> StageObservation:
    return StageObservation(complete=True, identity=identity)


def _watermark():
    return {
        "business_date": "2026-08-29",
        "gold_run_id": "g-1",
        "graph_generation_id": "gen-1",
        "silver_completeness_ok": True,
        "graph_parity_ok": True,
        "bronze_persist_used": False,
    }


def _issuer(cik: int = 320193):
    wm = _watermark()
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


class MongoDecisionSmokeTests(unittest.TestCase):
    def test_publisher_upsert_then_read_only_find_and_write_rejected(self) -> None:
        from edgar_warehouse.serving.mongo_decision_smoke import run_mongo_decision_smoke

        shared = PyMongoDecisionStore(_FakeClient())
        publisher = _RoleStore(shared, can_write=True)
        agent = _RoleStore(shared, can_write=False)

        result = run_mongo_decision_smoke(
            publisher,
            agent,
            alignment_store=MemoryAlignmentStore(),
            business_date="2026-08-29",
            cause_references=("cause-a",),
            silver=lambda _: _complete(),
            mdm=lambda _: _complete(),
            gold=lambda _: _complete("g-1"),
            graph=lambda _: _complete("gen-1"),
            issuers=(_issuer(),),
            now=datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        )
        self.assertEqual(result.documents_written, 2)
        self.assertTrue(result.agent_found_agent_grade)
        self.assertTrue(result.agent_write_rejected)
        self.assertEqual(result.found_cik, 320193)
