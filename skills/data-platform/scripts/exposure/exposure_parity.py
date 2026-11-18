"""Deterministic parity checks for the approved exposure across systems."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the sibling exposure scripts

from typing import Any

from exposure_manifest import validate_manifest


def _identity(row: dict[str, Any]) -> str:
    return ".".join((row["database"], row["schema"], row["table"]))


def _manifest_tables(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {".".join(table["physical"][k] for k in ("database", "schema", "table")): table for table in manifest["tables"]}


def _system_tables(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {_identity(table): table for table in snapshot.get("tables", [])}


def _mismatch(kind: str, owner: str, message: str, remediation: str) -> dict[str, str]:
    return {"kind": kind, "owner": owner, "message": message, "remediation": remediation}


def check_parity(
    manifest: dict[str, Any],
    *,
    snowflake: dict[str, Any],
    openmetadata: dict[str, Any],
    autoontology: dict[str, Any],
) -> dict[str, Any]:
    """Compare credential-free metadata snapshots against the approved manifest."""
    validate_manifest(manifest)
    expected = _manifest_tables(manifest)
    mismatches: list[dict[str, str]] = []
    snapshots = {"Snowflake": snowflake, "OpenMetadata": openmetadata, "AutoOntology": autoontology}

    for owner, snapshot in snapshots.items():
        actual = _system_tables(snapshot)
        for identity in sorted(set(expected) - set(actual)):
            mismatches.append(_mismatch("missing_asset", owner, identity, f"Refresh {owner} metadata from the approved manifest."))
        for identity in sorted(set(actual) - set(expected)):
            mismatches.append(_mismatch("extra_asset", owner, identity, f"Remove {identity} from {owner} exposure or update the manifest."))
        for identity in sorted(set(expected) & set(actual)):
            wanted = expected[identity]
            found = actual[identity]
            expected_columns = {column["name"]: column["data_type"] for column in wanted["columns"]}
            actual_columns = {column["name"]: column["data_type"] for column in found.get("columns", [])}
            for column in sorted(set(expected_columns) - set(actual_columns)):
                mismatches.append(_mismatch("missing_column", owner, f"{identity}.{column}", f"Refresh {owner} schema metadata."))
            for column in sorted(set(actual_columns) - set(expected_columns)):
                mismatches.append(_mismatch("extra_column", owner, f"{identity}.{column}", f"Remove the extra column from {owner} exposure or update the manifest."))
            for column in sorted(set(expected_columns) & set(actual_columns)):
                if expected_columns[column] != actual_columns[column]:
                    mismatches.append(_mismatch("type_drift", owner, f"{identity}.{column}: expected {expected_columns[column]}, found {actual_columns[column]}", f"Align {owner} column type with the manifest."))
            if found.get("description") != wanted["business"]["description"]:
                mismatches.append(_mismatch("description_drift", owner, identity, f"Update the {owner} description from the manifest."))
            if found.get("authority") != wanted["business"]["authority"]:
                mismatches.append(_mismatch("authority_drift", owner, identity, f"Correct {owner} authority metadata or revise the manifest."))

    expected_lineage = {(edge.get("from"), edge.get("to")) for table in manifest["tables"] for edge in table["lineage"] if edge.get("from") and edge.get("to")}
    for owner, snapshot in snapshots.items():
        actual_lineage = {(edge.get("from"), edge.get("to")) for edge in snapshot.get("lineage", [])}
        for edge in sorted(expected_lineage - actual_lineage):
            mismatches.append(_mismatch("lineage_mismatch", owner, f"{edge[0]} -> {edge[1]}", f"Republish approved lineage to {owner}."))
        for edge in sorted(actual_lineage - expected_lineage):
            mismatches.append(_mismatch("extra_lineage", owner, f"{edge[0]} -> {edge[1]}", f"Remove unsupported lineage from {owner}."))

    return {"ok": not mismatches, "manifest_digest": manifest["digest"], "mismatches": mismatches}
