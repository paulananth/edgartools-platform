"""Pure publication preparation; the immutable database intent is the authority."""

from __future__ import annotations

import hashlib
import json

from edgar_warehouse.rules.source_engine import postgres_jsonb_object


def payload_text(row) -> str:
    """Keep raw numeric scale until the original PostgreSQL hash is checked."""
    if row["payload_text"] is not None:
        return row["payload_text"]
    parts = {
        "contract_version": "2",
        "generation": str(row["generation"]),
        "run_id": json.dumps(row["run_id"]),
        "policy_digest": json.dumps(row["policy_digest"], ensure_ascii=False),
        "objects": row["projections_text"] or "null",
    }
    if row["consumer"] == "journal":
        parts["effects"] = row["effects_text"]
    return postgres_jsonb_object(parts, canonical_inputs=True)


def prepare(row) -> dict:
    """Refuse a mismatching preparation before any external publication."""
    from .store import Conflict

    raw = payload_text(row)
    if hashlib.sha256(raw.encode()).hexdigest() != row["payload_hash"]:
        raise Conflict("Publication preparation disagrees with committed payload hash")
    return json.loads(raw)
