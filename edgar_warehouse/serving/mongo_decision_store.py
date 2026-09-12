"""PyMongo adapter for MongoDecisionStore (ADR 0009, ticket 04).

The publisher talks to ``MongoDecisionStore``. This wraps an injected Mongo
client so unit tests never import pymongo or reach Atlas.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


class PyMongoDecisionStore:
    """Adapter: pymongo-style client → Decision Store Protocol."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def replace_document(
        self, database: str, collection: str, document: Mapping[str, Any]
    ) -> None:
        stored = dict(document)
        self._client[database][collection].replace_one(
            {"_id": stored["_id"]}, stored, upsert=True
        )

    def list_documents(
        self, database: str, collection: str
    ) -> Sequence[Mapping[str, Any]]:
        return [dict(doc) for doc in self._client[database][collection].find()]

    def find_document(
        self, database: str, collection: str, document_id: object
    ) -> Mapping[str, Any] | None:
        found = list(
            self._client[database][collection].find({"_id": document_id})
        )
        if not found:
            return None
        return dict(found[0])


def mongo_client_from_uri(uri: str) -> Any:
    """Lazy pymongo connect. TLS is required on Atlas ``mongodb+srv``."""
    from pymongo import MongoClient

    return MongoClient(uri, tls=True, serverSelectionTimeoutMS=15_000)
