"""Publish the approved Snowflake exposure manifest to OpenMetadata."""

from __future__ import annotations

from typing import Any, Callable

from edgar_warehouse.rules.catalog import GOLD, SILVER_MARK, fqn
from edgar_warehouse.rules.exposure_manifest import validate_manifest

SERVICE = "edgartools-snowflake"
QUALIFIED_VERSIONS = frozenset({"2.0.2", "2.0.7"})
Call = Callable[..., Any]


def _identity(table: dict[str, Any]) -> tuple[str, str, str]:
    physical = table["physical"]
    return physical["database"], physical["schema"], physical["table"]


def _certification(schema: str) -> str:
    if schema == "EDGARTOOLS_GOLD":
        return GOLD
    if schema == "EDGARTOOLS_SILVER":
        return SILVER_MARK
    raise ValueError(f"no certification convention for schema {schema}")


def plan_exposure(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return the OpenMetadata writes for one validated exposure manifest."""
    validate_manifest(manifest)
    tables = []
    lineage = []
    known = {".".join(_identity(table)) for table in manifest["tables"]}
    for table in manifest["tables"]:
        database, schema, name = _identity(table)
        tables.append(
            {
                "name": name,
                "database": database,
                "databaseSchema": fqn(SERVICE, database, schema),
                "description": table["business"]["description"],
                "columns": [
                    {
                        "name": column["name"],
                        "dataType": column["data_type"],
                        "description": column["description"],
                    }
                    for column in table["columns"]
                ],
                "certification": _certification(schema),
                "glossaryTerm": table["business"]["authority"],
            }
        )
        target = ".".join((database, schema, name))
        for edge in table["lineage"]:
            source = edge.get("from") or edge.get("reference")
            if source in known and source != target:
                lineage.append({"from": source, "to": target})
    return {"service": SERVICE, "tables": tables, "lineage": lineage, "digest": manifest["digest"]}


def publish_exposure(manifest: dict[str, Any], call: Call) -> dict[str, Any]:
    """Publish and read back one manifest. Repeated calls send the same plan."""
    version = (call("GET", "/system/version") or {}).get("version")
    if version not in QUALIFIED_VERSIONS:
        raise RuntimeError(f"unsupported OpenMetadata version: {version}")
    plan = plan_exposure(manifest)
    for table in plan["tables"]:
        call("PUT", "/tables", table)
        call("PUT", "/glossaryTerms", {"name": table["glossaryTerm"], "description": table["description"]})
    for edge in plan["lineage"]:
        call("PUT", "/lineage", edge)
    readback = call("GET", f"/services/databaseServices/name/{SERVICE}/tables") or {}
    published = {item.get("fullyQualifiedName") for item in readback.get("data") or []}
    expected = {
        fqn(SERVICE, table["database"], table["databaseSchema"].rsplit(".", 1)[-1], table["name"])
        for table in plan["tables"]
    }
    if published != expected:
        raise RuntimeError("OpenMetadata readback does not match the approved exposure")
    return {"plan": plan, "readback": sorted(published)}
