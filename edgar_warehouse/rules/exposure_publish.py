"""Publish the approved Snowflake exposure through the rules catalog publisher."""

from __future__ import annotations

from typing import Any, Callable

from edgar_warehouse.rules import catalog
from edgar_warehouse.rules.catalog import GOLD, SILVER_MARK, fqn
from edgar_warehouse.rules.exposure_manifest import validate_manifest

SERVICE = "edgartools-snowflake"
QUALIFIED_VERSIONS = frozenset({"2.0.2", "2.0.7"})
CERTIFICATION = {"EDGARTOOLS_GOLD": GOLD, "EDGARTOOLS_SILVER": SILVER_MARK}
AUTHORITY_TAG = {
    "mdm": "data_class.master_data",
    "rdm": "data_class.reference_data",
    "silver": "data_class.transaction_data",
    "source": "data_class.transaction_data",
}
Call = Callable[..., Any]


def _physical(table: dict[str, Any]) -> tuple[str, str, str]:
    item = table["physical"]
    return item["database"], item["schema"], item["table"]


def exposure_plan(manifest: dict[str, Any]) -> dict[str, Any]:
    """Build a rules-catalog plan. Unverified lineage is omitted."""
    validate_manifest(manifest)
    known = {".".join(_physical(table)): table for table in manifest["tables"]}
    databases = sorted({database for database, _, _ in (key.split(".") for key in known)})
    schemas = sorted({(database, schema) for database, schema, _ in (key.split(".") for key in known)})
    tables = []
    certifications = []
    marks = []
    lineage = []
    for key, table in sorted(known.items()):
        database, schema, name = _physical(table)
        table_name = fqn(SERVICE, database, schema, name)
        tables.append({
            "name": name,
            "databaseSchema": fqn(SERVICE, database, schema),
            "description": table["business"]["description"],
            "columns": [
                {"name": column["name"], "dataType": column["data_type"], "description": column["description"]}
                for column in table["columns"]
            ],
        })
        if schema in CERTIFICATION:
            certifications.append({"table": table_name, "tag": CERTIFICATION[schema]})
        tag = AUTHORITY_TAG.get(table["business"]["authority"])
        if tag:
            marks.append({"table": table_name, "tag": tag})
        for edge in table["lineage"]:
            source = edge.get("from") or edge.get("reference")
            if source in known and source != key:
                lineage.append({
                    "from": fqn(SERVICE, *source.split(".")),
                    "to": table_name,
                    "description": f"Approved exposure lineage from {source}.",
                    "columns": [],
                })
    return {
        "service": {
            "name": SERVICE,
            "serviceType": "CustomDatabase",
            "description": f"Approved Snowflake exposure. Manifest digest: `{manifest['digest']}`.",
        },
        "databases": [
            {"name": name, "service": SERVICE, "description": f"Approved Snowflake database {name}."}
            for name in databases
        ],
        "schemas": [
            {"name": schema, "database": fqn(SERVICE, database), "description": f"Approved Snowflake schema {schema}."}
            for database, schema in schemas
        ],
        "tables": tables,
        "lineage": lineage,
        "certifications": certifications,
        "classifications": [{
            "name": "data_class",
            "description": "The class of data a table holds.",
            "tags": [{"name": name, "description": description} for name, _, description in catalog.DATA_CLASSES],
        }],
        "data_class_marks": marks,
    }


def publish_exposure(manifest: dict[str, Any], call: Call) -> dict[str, Any]:
    """Publish through the rules catalog publisher and verify the readback."""
    version = (call("GET", "/system/version") or {}).get("version")
    if version not in QUALIFIED_VERSIONS:
        raise RuntimeError(f"unsupported OpenMetadata version: {version}")
    plan = exposure_plan(manifest)
    published = catalog.publish(plan, call)
    verified = catalog.verify(plan, call)
    if verified["differences"]:
        raise RuntimeError("OpenMetadata readback does not match the approved exposure")
    return {"published": published, "verified": verified}
