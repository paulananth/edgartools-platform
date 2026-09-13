"""PyMongo Decision Store adapter (ticket 04). Injected client; no live Atlas."""

from __future__ import annotations

import unittest

from edgar_warehouse.serving.mongo_decision_projection import (
    COLLECTION_ISSUER_BUNDLE,
    DATABASE_NAME,
)


class _FakeCollection:
    def __init__(self) -> None:
        self.docs: dict[object, dict] = {}
        self.replace_one_calls: list[tuple] = []
        self.write_forbidden = False
        self.indexes: list[object] = []

    def replace_one(self, filt, document, upsert=False):
        if self.write_forbidden:
            raise PermissionError("not authorized on this resource")
        self.replace_one_calls.append((dict(filt), dict(document), upsert))
        stored = dict(document)
        self.docs[stored["_id"]] = stored
        return None

    def find(self, filt=None):
        if not filt:
            return [dict(doc) for doc in self.docs.values()]
        wanted = filt.get("_id")
        if wanted in self.docs:
            return [dict(self.docs[wanted])]
        return []

    def create_index(self, keys):
        self.indexes.append(keys)


class _FakeDatabase:
    def __init__(self) -> None:
        self._collections: dict[str, _FakeCollection] = {}
        self.created: list[tuple] = []

    def __getitem__(self, name: str) -> _FakeCollection:
        return self._collections.setdefault(name, _FakeCollection())

    def list_collection_names(self) -> list[str]:
        return list(self._collections)

    def create_collection(self, name: str, **kwargs):
        self.created.append((name, kwargs))
        return self[name]


class _FakeClient:
    def __init__(self) -> None:
        self._databases: dict[str, _FakeDatabase] = {}

    def __getitem__(self, name: str) -> _FakeDatabase:
        return self._databases.setdefault(name, _FakeDatabase())


class PyMongoDecisionStoreTests(unittest.TestCase):
    def test_replace_document_upserts_by_cik(self) -> None:
        from edgar_warehouse.serving.mongo_decision_store import PyMongoDecisionStore

        client = _FakeClient()
        store = PyMongoDecisionStore(client)
        store.replace_document(
            DATABASE_NAME,
            COLLECTION_ISSUER_BUNDLE,
            {"_id": 320193, "agent_grade": True, "readiness_state": "agent_ready"},
        )
        coll = client[DATABASE_NAME][COLLECTION_ISSUER_BUNDLE]
        self.assertEqual(len(coll.replace_one_calls), 1)
        filt, doc, upsert = coll.replace_one_calls[0]
        self.assertEqual(filt, {"_id": 320193})
        self.assertTrue(upsert)
        self.assertEqual(doc["_id"], 320193)
        listed = store.list_documents(DATABASE_NAME, COLLECTION_ISSUER_BUNDLE)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["_id"], 320193)
        found = store.find_document(DATABASE_NAME, COLLECTION_ISSUER_BUNDLE, 320193)
        self.assertIsNotNone(found)
        self.assertEqual(found["_id"], 320193)


class DecisionProjectionSchemaTests(unittest.TestCase):
    def test_json_schema_requires_watermark_and_ready_enum(self) -> None:
        from edgar_warehouse.serving.mongo_decision_schema import (
            DECISION_DOCUMENT_VALIDATOR,
        )

        schema = DECISION_DOCUMENT_VALIDATOR["$jsonSchema"]
        self.assertEqual(
            set(schema["required"]),
            {
                "_id",
                "decision_contract_version",
                "agent_grade",
                "readiness_state",
                "decision_watermark",
            },
        )
        self.assertEqual(schema["properties"]["readiness_state"]["enum"], ["agent_ready", "not_ready"])
        self.assertEqual(schema["properties"]["decision_contract_version"]["enum"], ["1"])

    def test_apply_schema_creates_both_collections_and_generation_index(self) -> None:
        from edgar_warehouse.serving.mongo_decision_projection import (
            COLLECTION_FEATURE_SCREEN,
        )
        from edgar_warehouse.serving.mongo_decision_schema import (
            GENERATION_INDEX,
            apply_decision_projection_schema,
        )

        client = _FakeClient()
        apply_decision_projection_schema(client)
        db = client[DATABASE_NAME]
        created = {name for name, _ in db.created}
        self.assertEqual(created, {COLLECTION_ISSUER_BUNDLE, COLLECTION_FEATURE_SCREEN})
        for name, kwargs in db.created:
            self.assertEqual(kwargs["validationLevel"], "strict")
            self.assertEqual(kwargs["validationAction"], "error")
            self.assertIn("$jsonSchema", kwargs["validator"])
        for name in (COLLECTION_ISSUER_BUNDLE, COLLECTION_FEATURE_SCREEN):
            self.assertIn(GENERATION_INDEX, db[name].indexes)
