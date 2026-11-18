#!/usr/bin/env python3
"""Publish an exposure manifest to OpenMetadata, through the repository's catalog publisher, and read it back.

Generic: it projects any manifest (`exposure_manifest.py`) into one database service the manifest owns. Inside
that service the publication is the whole truth: `catalog.publish` creates or updates every table the manifest
names and deletes, in that service only, what it no longer names. Nothing outside the service is written but the
`exposure` classification this script owns.

Of the two classifications this publication speaks for, each table carries exactly its two tags, so a removed
one does not linger: `exposure.approved` (the consumer eligibility the manifest records, apart from data class and
certification) and its layer's data class (a tag the rules catalog already defines; this script never writes that
classification). A tag of any other classification, such as one a steward added, is kept as it is.
No glossary term and no certification is published: the manifest names neither. Lineage is only what the
manifest states. Columns keep the store's own type in `dataTypeDisplay` beside OpenMetadata's type.
Publishing the same manifest again changes no entity's version: that is what idempotent means here, and
`verify` reads it back.

    uv run --no-project --with pyyaml python exposure_publish.py --manifest <manifest.json> \\
        --config rules/exposure.yaml [--root .] [--service <name>] [--check]

It reads `OPENMETADATA_URL` and `OPENMETADATA_TOKEN` from the environment (a private file, never an argument).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote as escape

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the sibling exposure scripts

from exposure_manifest import validate_manifest  # noqa: E402

from edgar_warehouse.rules import catalog  # noqa: E402
from edgar_warehouse.rules.catalog import fqn  # noqa: E402

SERVICE = "edgartools-exposure"
QUALIFIED_VERSIONS = frozenset({"2.0.7"})
EXPOSURE = "exposure"
APPROVED = EXPOSURE + ".approved"
# A layer's data class, as the rules catalog names its tags. An unknown layer is refused.
DATA_CLASS = {"mdm": "data_class.master_data", "rdm": "data_class.reference_data",
              "silver": "data_class.transaction_data"}
# A PostgreSQL type, by its base name, as OpenMetadata types it; the length goes in dataLength.
TYPES = {"text": "TEXT", "character varying": "VARCHAR", "character": "CHAR", "bigint": "BIGINT",
         "integer": "INT", "smallint": "SMALLINT", "numeric": "NUMERIC", "double precision": "DOUBLE",
         "real": "FLOAT", "boolean": "BOOLEAN", "date": "DATE", "timestamp with time zone": "TIMESTAMPZ",
         "timestamp without time zone": "TIMESTAMP", "jsonb": "JSON", "json": "JSON", "uuid": "UUID"}
LENGTHS = {"VARCHAR", "CHAR"}
OWNED = (EXPOSURE + ".", "data_class.")  # the classifications whose tags this publication sets on its tables
Call = Callable[..., Any]


class PublishError(RuntimeError):
    """The catalog does not hold what the manifest says, or the manifest cannot be projected."""


def column_type(data_type: str) -> dict:
    """OpenMetadata's type for a PostgreSQL one; the store's own spelling is kept for display."""
    match = re.fullmatch(r"([a-z ]+?)(?:\((\d+)(?:,(\d+))?\))?", data_type)
    if not match or match[1] not in TYPES:
        raise PublishError(f"no catalog type for the store type {data_type!r}")
    kind = TYPES[match[1]]
    if kind == "VARCHAR" and match[2] is None:
        kind = "TEXT"  # a varchar with no declared length is unbounded, as text is
    typed = {"dataType": kind, "dataTypeDisplay": data_type}
    if kind in LENGTHS:
        typed["dataLength"] = int(match[2] or 1)
    return typed


def _identity(physical: dict) -> tuple[str, str, str]:
    return physical["database"], physical["schema"], physical["table"]


def exposure_plan(manifest: dict, *, service: str = SERVICE) -> dict:
    """The catalog plan for the manifest's tables, and the tags each must carry."""
    validate_manifest(manifest)
    tables = {_identity(t["physical"]): t for t in manifest["tables"]}
    verified = "read back from the mirror" if manifest["target"]["verified"] else "planned, not yet read back"
    plan_tables, lineage, tags = [], [], {}
    for identity, table in sorted(tables.items()):
        database, schema, name = identity
        if table["layer"] not in DATA_CLASS:
            raise PublishError(f"{name} is in layer {table['layer']!r}, which has no data class")
        plan_tables.append({
            "name": name,
            "databaseSchema": fqn(service, database, schema),
            "description": table["business"]["description"],
            "columns": [{"name": c["name"], **column_type(c["data_type"]), "description": c["description"]}
                        for c in table["columns"]],
        })
        tags[fqn(service, *identity)] = sorted({APPROVED, DATA_CLASS[table["layer"]]})
        for reference in table["lineage"]:
            source = _identity(reference)
            if source not in tables:
                raise PublishError(f"{name} names lineage to a table the manifest does not hold")
            lineage.append({"from": fqn(service, *source), "to": fqn(service, *identity), "columns": [],
                            "description": "The manifest states this table is filled from that one."})
    databases = sorted({d for d, _, _ in tables})
    schemas = sorted({(d, s) for d, s, _ in tables})
    return {
        "service": {"name": service, "serviceType": "CustomDatabase",
                    "description": f"The approved exposure ({manifest['version']}): Snowflake identities {verified}. "
                                   f"Manifest digest `{manifest['digest']}`."},
        "databases": [{"name": d, "service": service, "description": f"Exposed database {d}."} for d in databases],
        "schemas": [{"name": s, "database": fqn(service, d), "description": f"Exposed schema {s}."}
                    for d, s in schemas],
        "tables": plan_tables,
        "lineage": sorted(lineage, key=lambda e: (e["to"], e["from"])),
        "tags": tags,
    }


def _labels(names: list[str]) -> list[dict]:
    return [{"tagFQN": n, "source": "Classification", "labelType": "Manual", "state": "Confirmed"} for n in names]


def _held(call: Call, table: str) -> tuple[str, list[dict]]:
    held = call("GET", f"/tables/name/{escape(table, safe='')}", params={"fields": "tags"}) or {}
    return held.get("id"), list(held.get("tags") or [])


def _owned(tags: list[dict]) -> list[str]:
    return sorted(t["tagFQN"] for t in tags if t["tagFQN"].startswith(OWNED))


def retagged(tags: list[dict], wanted: list[str]) -> list[dict] | None:
    """The table's tags with the owned ones made exactly `wanted` and every other tag kept; None if already so."""
    if _owned(tags) == wanted:
        return None
    return [t for t in tags if not t["tagFQN"].startswith(OWNED)] + _labels(wanted)


def _require_vocabulary(call: Call, plan: dict) -> None:
    """The data class tags belong to the rules catalog: refuse rather than create them."""
    needed = {t for tags in plan["tags"].values() for t in tags if t != APPROVED}
    missing = sorted(t for t in needed if call("GET", f"/tags/name/{escape(t, safe='')}") is None)
    if missing:
        raise PublishError(f"the catalog lacks the data class tags {missing}: publish the rules catalog first")
    wanted = {"name": EXPOSURE, "description": "Whether a table may leave the processing stores for its consumers "
                                               "(the managed mirror, AutoOntology), as the exposure list approves."}
    held = call("GET", f"/classifications/name/{EXPOSURE}")
    if held is None or held.get("description") != wanted["description"]:
        call("PUT", "/classifications", wanted)
    tag = {"classification": EXPOSURE, "name": "approved",
           "description": "Listed in the approved exposure: the mirror and AutoOntology may read it."}
    held = call("GET", f"/tags/name/{APPROVED}")
    if held is None or held.get("description") != tag["description"]:
        call("PUT", "/tags", tag)


def _require_qualified(call: Call) -> None:
    version = (call("GET", "/system/version") or {}).get("version")
    if version not in QUALIFIED_VERSIONS:
        raise PublishError(f"OpenMetadata {version} is not a qualified version")


def publish(manifest: dict, call: Call, *, service: str = SERVICE) -> dict:
    """Make the service equal to the manifest, tags exactly, then read it all back."""
    _require_qualified(call)
    plan = exposure_plan(manifest, service=service)
    _require_vocabulary(call, plan)
    core = {k: v for k, v in plan.items() if k != "tags"}
    published = catalog.publish(core, call)
    changed = 0
    for table, wanted in sorted(plan["tags"].items()):
        table_id, tags = _held(call, table)
        value = retagged(tags, wanted)
        if value is not None:
            call("PATCH", f"/tables/{table_id}", [{"op": "add", "path": "/tags", "value": value}])
            changed += 1
    return {"published": published, "tags_set": changed, "verified": verify(manifest, call, service=service)}


def verify(manifest: dict, call: Call, *, service: str = SERVICE) -> dict:
    """Read back the service, lineage and exact tags, and that no table outside it carries the exposure tag."""
    _require_qualified(call)
    plan = exposure_plan(manifest, service=service)
    core = {k: v for k, v in plan.items() if k != "tags"}
    differences = list(catalog.verify(core, call)["differences"])
    for table, wanted in sorted(plan["tags"].items()):
        held = _owned(_held(call, table)[1])
        if held != wanted:
            differences.append(f"{table}: tags {held}, expected {wanted}")
    used = (call("GET", f"/tags/name/{APPROVED}", params={"fields": "usageCount"}) or {}).get("usageCount")
    if used != len(plan["tags"]):
        differences.append(f"{APPROVED} is on {used} assets; the manifest exposes {len(plan['tags'])} tables")
    if differences:
        raise PublishError("the catalog differs from the manifest: " + "; ".join(differences))
    return {"tables": len(plan["tables"]), "lineage": len(plan["lineage"]), "differences": []}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path, help="The exposure list, to refuse a stale manifest")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="The folder requirement paths are under")
    parser.add_argument("--service", default=SERVICE)
    parser.add_argument("--check", action="store_true", help="Read back only; write nothing")
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        validate_manifest(manifest, config=args.config, root=args.root)
        call = catalog.connect(os.environ["OPENMETADATA_URL"], os.environ["OPENMETADATA_TOKEN"])
        result = verify(manifest, call, service=args.service) if args.check else publish(
            manifest, call, service=args.service)
    except KeyError as missing:
        print(f"{missing.args[0]} is not set: source the private OpenMetadata env file", file=sys.stderr)
        return 2
    except (ValueError, PublishError, catalog.CatalogError) as error:
        print(error, file=sys.stderr)
        return 1
    print(json.dumps(result, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
