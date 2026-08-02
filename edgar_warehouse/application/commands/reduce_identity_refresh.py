"""Reducer entry point for a completed run-scoped Daily Identity Refresh."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from edgar_warehouse.application.commands.bootstrap_fundamentals import (
    _build_silver_context,
)
from edgar_warehouse.application.identity_refresh_publication import (
    reduce_identity_refresh,
)
from edgar_warehouse.infrastructure.warehouse_settings import resolve_edgar_identity


def execute(args: Any) -> int:
    run_id = str(getattr(args, "run_id", None) or "")
    if not run_id:
        print("reduce-identity-refresh requires --run-id", file=sys.stderr)
        return 2
    image_identity = os.environ.get("WAREHOUSE_IMAGE_REF", "").strip()
    if not image_identity:
        print("reduce-identity-refresh requires WAREHOUSE_IMAGE_REF", file=sys.stderr)
        return 2
    try:
        context = _build_silver_context(identity=resolve_edgar_identity(), silver_root_override="")
        completed = reduce_identity_refresh(
            context.storage_root,
            run_id=run_id,
            image_identity=image_identity,
            max_attempts=int(getattr(args, "max_attempts", 3) or 3),
        )
    except Exception as exc:  # noqa: BLE001 - CLI must return a nonzero disposition for every reducer failure.
        print(f"reduce-identity-refresh failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"command": "reduce-identity-refresh", "run_id": run_id, "reducer": completed["reducer"], "status": "ok"}, indent=2, sort_keys=True))
    return 0
