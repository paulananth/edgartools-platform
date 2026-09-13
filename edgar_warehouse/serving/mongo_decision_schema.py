"""Atlas $jsonSchema and indexes for the Mongo Decision Projection.

Empty collections only (data-contract.md): validationLevel strict,
validationAction error. Not applied until an operator cluster exists.
"""

from __future__ import annotations

from typing import Any

from edgar_warehouse.serving.decision_contract import DECISION_CONTRACT_VERSION
from edgar_warehouse.serving.mongo_decision_projection import (
    COLLECTION_FEATURE_SCREEN,
    COLLECTION_ISSUER_BUNDLE,
    DATABASE_NAME,
    READINESS_AGENT_READY,
    READINESS_NOT_READY,
)

GENERATION_INDEX = [("readiness_state", 1), ("decision_watermark.graph_generation_id", 1)]

DECISION_DOCUMENT_VALIDATOR: dict[str, Any] = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "_id",
            "decision_contract_version",
            "agent_grade",
            "readiness_state",
            "decision_watermark",
        ],
        "properties": {
            "_id": {"bsonType": ["int", "long"]},
            "decision_contract_version": {"enum": [DECISION_CONTRACT_VERSION]},
            "agent_grade": {"bsonType": "bool"},
            "readiness_state": {"enum": [READINESS_AGENT_READY, READINESS_NOT_READY]},
            "decision_watermark": {
                "bsonType": "object",
                "required": [
                    "business_date",
                    "gold_run_id",
                    "graph_generation_id",
                    "decision_contract_version",
                    "silver_completeness_ok",
                    "graph_parity_ok",
                ],
                "properties": {
                    "business_date": {"bsonType": "string"},
                    "gold_run_id": {"bsonType": "string"},
                    "graph_generation_id": {"bsonType": "string"},
                    "decision_contract_version": {"enum": [DECISION_CONTRACT_VERSION]},
                    "bronze_content_digest": {"bsonType": ["string", "null"]},
                    "silver_completeness_ok": {"bsonType": "bool"},
                    "graph_parity_ok": {"bsonType": "bool"},
                },
            },
        },
    }
}


def apply_decision_projection_schema(client: Any) -> None:
    """Create both collections with $jsonSchema and the generation index."""
    db = client[DATABASE_NAME]
    existing = set(db.list_collection_names())
    for name in (COLLECTION_ISSUER_BUNDLE, COLLECTION_FEATURE_SCREEN):
        if name not in existing:
            db.create_collection(
                name,
                validator=DECISION_DOCUMENT_VALIDATOR,
                validationLevel="strict",
                validationAction="error",
            )
        else:
            db.command(
                "collMod",
                name,
                validator=DECISION_DOCUMENT_VALIDATOR,
                validationLevel="strict",
                validationAction="error",
            )
        db[name].create_index(GENERATION_INDEX)
