"""Operation-scoped identity for durable MDM commit evidence."""
from __future__ import annotations

import uuid

from edgar_warehouse.mdm.observability import emit_mdm_event


def normalize_or_create_run_id(run_id: object | None) -> tuple[str, str]:
    """Return a non-empty opaque identity and whether it was supplied."""
    value = "" if run_id is None else str(run_id).strip()
    if value:
        return value, "provided"
    return str(uuid.uuid4()), "generated"


def bind_mdm_run_identity(run_id: object | None) -> str:
    """Resolve and report the identity at a public mutation boundary."""
    value, source = normalize_or_create_run_id(run_id)
    emit_mdm_event("mdm_run_identity", run_id=value, source=source)
    return value
