"""Mongo Decision Projection publisher: READY write (ticket 01) and in-place hide (ticket 02)."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from edgar_warehouse.serving.decision_contract import DECISION_CONTRACT_VERSION
from edgar_warehouse.serving.mongo_decision_projection import (
    COLLECTION_FEATURE_SCREEN,
    COLLECTION_ISSUER_BUNDLE,
    DATABASE_NAME,
    publish_ready_issuer_documents,
)
from edgar_warehouse.serving.subject_bundle_read import (
    SECTION_ADV,
    SECTION_AUDITOR,
    SECTION_HOLDERS_OF_SUBJECT,
    SECTION_PARENT,
    SECTION_SUBJECT_AS_MANAGER_PORTFOLIO,
    build_issuer_subject_bundle,
)
from edgar_warehouse.serving.subject_feature_screen import (
    COVERAGE_NOT_APPLICABLE,
    COVERAGE_UNAVAILABLE,
    build_subject_feature_screen,
)


class _MemoryStore:
    def __init__(self) -> None:
        self._docs: dict[tuple[str, str, object], dict] = {}
        self.replaced: list[tuple[str, str, dict]] = []

    def replace_document(
        self, database: str, collection: str, document: dict
    ) -> None:
        stored = dict(document)
        self._docs[(database, collection, stored["_id"])] = stored
        self.replaced.append((database, collection, stored))

    def list_documents(self, database: str, collection: str) -> list[dict]:
        return [
            dict(doc)
            for (db, col, _), doc in self._docs.items()
            if db == database and col == collection
        ]


def _ok_watermark(**overrides):
    base = {
        "business_date": "2024-06-30",
        "gold_run_id": "gold-1",
        "graph_generation_id": "gen-1",
        "silver_completeness_ok": True,
        "graph_parity_ok": True,
        "bronze_persist_used": False,
    }
    base.update(overrides)
    return base


def _issuer(cik: int = 320193, watermark=None):
    wm = watermark if watermark is not None else _ok_watermark()
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


class PublishReadyIssuerDocumentsTests(unittest.TestCase):
    def test_not_ready_publication_writes_nothing(self) -> None:
        store = _MemoryStore()
        result = publish_ready_issuer_documents(
            store,
            publication_status="draft",
            watermark_components=_ok_watermark(),
            issuers=(_issuer(),),
        )
        self.assertEqual(store.replaced, [])
        self.assertEqual(result.documents_written, 0)
        self.assertEqual(result.skip_reason, "publication_not_ready")

    def test_not_agent_grade_watermark_writes_nothing(self) -> None:
        store = _MemoryStore()
        wm = _ok_watermark(graph_parity_ok=False)
        result = publish_ready_issuer_documents(
            store,
            publication_status="ready",
            watermark_components=wm,
            issuers=(_issuer(watermark=wm),),
        )
        self.assertEqual(store.replaced, [])
        self.assertEqual(result.documents_written, 0)
        self.assertEqual(result.skip_reason, "not_agent_grade")

    def test_ready_writes_bundle_and_feature_screen_for_one_cik(self) -> None:
        store = _MemoryStore()
        clock = datetime(2026, 9, 11, 20, 0, tzinfo=UTC)
        wm = _ok_watermark(
            bronze_persist_used=True,
            bronze_content_hashes=("hash-a", "hash-b"),
        )
        result = publish_ready_issuer_documents(
            store,
            publication_status="ready",
            watermark_components=wm,
            issuers=(_issuer(watermark=wm),),
            now=clock,
        )
        self.assertEqual(result.documents_written, 2)
        self.assertIsNone(result.skip_reason)
        self.assertEqual(
            [(db, col) for db, col, _ in store.replaced],
            [
                (DATABASE_NAME, COLLECTION_ISSUER_BUNDLE),
                (DATABASE_NAME, COLLECTION_FEATURE_SCREEN),
            ],
        )
        bundle = store.replaced[0][2]
        screen = store.replaced[1][2]
        self.assertEqual(bundle["_id"], 320193)
        self.assertEqual(bundle["bundle_subject_cik"], 320193)
        self.assertTrue(bundle["agent_grade"])
        self.assertEqual(bundle["readiness_state"], "agent_ready")
        self.assertEqual(bundle["projected_from"], "snowflake_decision_contract")
        self.assertEqual(bundle["projected_at"], "2026-09-11T20:00:00+00:00")
        self.assertEqual(bundle["decision_contract_version"], DECISION_CONTRACT_VERSION)
        digest = bundle["decision_watermark"]["bronze_content_digest"]
        self.assertEqual(
            digest,
            "237a82edc16d51c7a586c366dc357db8b85a142222b66c8552783927496a4fbb",
        )
        self.assertEqual(bundle["decision_watermark"]["gold_run_id"], "gold-1")
        self.assertTrue(bundle["decision_watermark"]["silver_completeness_ok"])
        self.assertTrue(bundle["decision_watermark"]["graph_parity_ok"])
        sections = bundle["sections"]
        self.assertEqual(sections[SECTION_ADV]["coverage"], COVERAGE_NOT_APPLICABLE)
        self.assertEqual(sections[SECTION_HOLDERS_OF_SUBJECT]["coverage"], COVERAGE_UNAVAILABLE)
        self.assertEqual(sections[SECTION_AUDITOR]["coverage"], COVERAGE_UNAVAILABLE)
        self.assertEqual(sections[SECTION_PARENT]["coverage"], COVERAGE_UNAVAILABLE)
        self.assertEqual(
            sections[SECTION_SUBJECT_AS_MANAGER_PORTFOLIO]["coverage"],
            COVERAGE_UNAVAILABLE,
        )
        self.assertEqual(screen["_id"], 320193)
        self.assertEqual(screen["cik"], 320193)
        self.assertEqual(screen["readiness_state"], "agent_ready")
        self.assertTrue(screen["agent_grade"])
        self.assertEqual(screen["projected_from"], "snowflake_decision_contract")
        self.assertEqual(
            screen["decision_watermark"]["bronze_content_digest"],
            digest,
        )
        self.assertIn("fy_features", screen)
        self.assertNotIn("rows", screen)
        self.assertNotIn("universe_size", screen)


class HideRetiredGenerationTests(unittest.TestCase):
    def test_pointer_move_fail_closes_prior_generation_in_place(self) -> None:
        store = _MemoryStore()
        gen1 = _ok_watermark(graph_generation_id="gen-1")
        publish_ready_issuer_documents(
            store,
            publication_status="ready",
            watermark_components=gen1,
            issuers=(_issuer(cik=320193, watermark=gen1),),
        )
        gen1_sections = store.list_documents(
            DATABASE_NAME, COLLECTION_ISSUER_BUNDLE
        )[0]["sections"]

        gen2 = _ok_watermark(graph_generation_id="gen-2", gold_run_id="gold-2")
        result = publish_ready_issuer_documents(
            store,
            publication_status="ready",
            watermark_components=gen2,
            issuers=(_issuer(cik=1, watermark=gen2),),
        )
        self.assertEqual(result.documents_hidden, 2)
        self.assertEqual(result.documents_written, 2)

        apple = next(
            doc
            for doc in store.list_documents(DATABASE_NAME, COLLECTION_ISSUER_BUNDLE)
            if doc["_id"] == 320193
        )
        self.assertFalse(apple["agent_grade"])
        self.assertEqual(apple["readiness_state"], "not_ready")
        self.assertEqual(
            apple["decision_watermark"]["graph_generation_id"], "gen-1"
        )
        self.assertEqual(apple["sections"], gen1_sections)

        apple_screen = next(
            doc
            for doc in store.list_documents(DATABASE_NAME, COLLECTION_FEATURE_SCREEN)
            if doc["_id"] == 320193
        )
        self.assertFalse(apple_screen["agent_grade"])
        self.assertEqual(apple_screen["readiness_state"], "not_ready")
        self.assertIn("fy_features", apple_screen)

        fresh = next(
            doc
            for doc in store.list_documents(DATABASE_NAME, COLLECTION_ISSUER_BUNDLE)
            if doc["_id"] == 1
        )
        self.assertTrue(fresh["agent_grade"])
        self.assertEqual(fresh["readiness_state"], "agent_ready")
        self.assertEqual(
            fresh["decision_watermark"]["graph_generation_id"], "gen-2"
        )
        self.assertEqual(len(store.list_documents(DATABASE_NAME, COLLECTION_ISSUER_BUNDLE)), 2)
        self.assertEqual(len(store.list_documents(DATABASE_NAME, COLLECTION_FEATURE_SCREEN)), 2)

    def test_empty_issuer_list_still_hides_retired_generation(self) -> None:
        store = _MemoryStore()
        gen1 = _ok_watermark(graph_generation_id="gen-1")
        publish_ready_issuer_documents(
            store,
            publication_status="ready",
            watermark_components=gen1,
            issuers=(_issuer(watermark=gen1),),
        )
        gen2 = _ok_watermark(graph_generation_id="gen-2")
        result = publish_ready_issuer_documents(
            store,
            publication_status="ready",
            watermark_components=gen2,
            issuers=(),
        )
        self.assertEqual(result.documents_written, 0)
        self.assertEqual(result.documents_hidden, 2)
        leftover = store.list_documents(DATABASE_NAME, COLLECTION_ISSUER_BUNDLE)[0]
        self.assertFalse(leftover["agent_grade"])
        self.assertEqual(leftover["readiness_state"], "not_ready")
