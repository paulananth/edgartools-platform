"""An invented exposure manifest for the exposure scripts' tests: tables described as a store would hold them."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "skills/data-platform/scripts/exposure"))

from exposure_manifest import build_manifest  # noqa: E402


def invented_manifest(*tables: dict, database: str = "INVENTED_MIRROR", schemas: dict | None = None) -> dict:
    """Each table: {"layer", "table", "description", "columns": [(name, type, description)], "lineage": [...]}."""
    layers = {
        name: {
            "connection": f"INVENTED_{name.upper()}_URL",
            "source_schema": name,
            "target_schema": (schemas or {}).get(name, name.upper()),
            "authority": name,
        }
        for name in sorted({t["layer"] for t in tables} | {"silver"})
    }
    config = {
        "version": "invented",
        "approval": {"date": "2026-01-01", "words": ["invented"]},
        "target": {"database": database, "verified": False},
        "layers": layers,
        "tables": [
            {
                "layer": t["layer"],
                "table": t["table"],
                "scope": "current",
                "grain": "one row per thing",
                "requirement": "invented.yaml",
                "lineage": t.get("lineage", []),
            }
            for t in tables
        ],
    }
    stores: dict[str, dict] = {}
    for t in tables:
        stores.setdefault(t["layer"], {})[t["table"]] = {
            "comment": t["description"],
            "columns": [
                {"name": name, "data_type": kind, "nullable": True, "comment": words}
                for name, kind, words in t["columns"]
            ],
        }
    return build_manifest(config, stores, config_digest="0" * 64, requirements={"invented.yaml": "1" * 64})
