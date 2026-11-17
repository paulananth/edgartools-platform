"""Build the approved Snowflake exposure manifest from repository rules.

The manifest deliberately separates physical Snowflake identity from business
meaning. Consumers can therefore reject a changed physical target without
mistaking it for a business-definition change.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MANIFEST_VERSION = 1
_ALLOWED_DATABASES = {"EDGARTOOLS_PROD"}
_ALLOWED_SCHEMAS = {"EDGARTOOLS_GOLD", "EDGARTOOLS_SILVER"}
_FORBIDDEN_NAME_MARKERS = ("CONTROL", "STAGING", "LANDING", "INFORMATION_SCHEMA", "INTERNAL")
_REQUIRED_TABLE_KEYS = {"database", "schema", "table", "description", "authority"}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _manifest_digest(unsigned: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(unsigned).encode("utf-8")).hexdigest()


def _normalized_column(column: dict[str, Any]) -> dict[str, str]:
    if not isinstance(column, dict) or not column.get("name") or not column.get("data_type"):
        raise ValueError("each column needs name and data_type")
    return {
        "name": str(column["name"]),
        "data_type": str(column["data_type"]),
        "description": str(column.get("description", "")).strip(),
    }


def validate_manifest(manifest: dict[str, Any]) -> None:
    """Reject an unsupported or tampered manifest before a consumer uses it."""
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise ValueError("unsupported manifest version")
    unsigned = {
        "manifest_version": manifest.get("manifest_version"),
        "tables": manifest.get("tables"),
    }
    if manifest.get("digest") != _manifest_digest(unsigned):
        raise ValueError("manifest digest does not match its contents")
    if not isinstance(manifest.get("tables"), list):
        raise ValueError("manifest tables must be a list")


def _manifest_table(source: dict[str, Any]) -> dict[str, Any]:
    _validate_table(source)
    database = str(source["database"]).upper()
    schema = str(source["schema"]).upper()
    table_name = str(source["table"]).upper()
    return {
        "physical": {"database": database, "schema": schema, "table": table_name},
        "business": {
            "description": str(source["description"]).strip(),
            "authority": str(source["authority"]).strip(),
        },
        "columns": sorted(
            (_normalized_column(column) for column in source.get("columns", [])),
            key=lambda column: column["name"],
        ),
        "lineage": sorted(
            (
                value
                if isinstance(value, dict)
                else {"reference": str(value)}
            )
            for value in source.get("lineage", [])
        ),
    }


def _manifest_tables(tables: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for source in tables:
        if not isinstance(source, dict):
            raise ValueError("each table must be an object")
        item = _manifest_table(source)
        identity = tuple(item["physical"].values())
        if identity in seen:
            raise ValueError(f"duplicate physical table: {'.'.join(identity)}")
        seen.add(identity)
        normalized.append(item)
    return sorted(normalized, key=lambda item: tuple(item["physical"].values()))


def _unsigned_manifest(tables: list[dict[str, Any]]) -> dict[str, Any]:
    return {"manifest_version": MANIFEST_VERSION, "tables": tables}


def _validate_table(table: dict[str, Any]) -> None:
    missing = sorted(_REQUIRED_TABLE_KEYS - table.keys())
    if missing:
        raise ValueError(f"table is missing required metadata: {', '.join(missing)}")

    database = str(table["database"]).upper()
    schema = str(table["schema"]).upper()
    if database not in _ALLOWED_DATABASES or schema not in _ALLOWED_SCHEMAS:
        raise ValueError(f"table is outside approved table scope: {database}.{schema}")
    table_name = str(table["table"]).upper()
    if any(marker in table_name for marker in _FORBIDDEN_NAME_MARKERS):
        raise ValueError(f"table is outside approved table scope: {database}.{schema}.{table_name}")
    if not table_name:
        raise ValueError("table name must not be empty")
    if not str(table["description"]).strip():
        raise ValueError("table description must not be empty")
    if not str(table["authority"]).strip():
        raise ValueError("table authority must not be empty")


def build_manifest(rules: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic manifest from an approved rules document.

    ``rules`` is intentionally a plain mapping so callers can load YAML, JSON,
    or a generated catalog plan without credentials or live services.
    """
    tables = rules.get("tables")
    if not isinstance(tables, list):
        raise ValueError("rules must contain a tables list")
    unsigned = _unsigned_manifest(_manifest_tables(tables))
    return {**unsigned, "digest": _manifest_digest(unsigned)}


def write_manifest(destination: Path, rules: dict[str, Any]) -> dict[str, Any]:
    """Write a canonical manifest and return the exact object written."""
    manifest = build_manifest(rules)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(_canonical_json(manifest) + "\n", encoding="utf-8")
    return manifest
