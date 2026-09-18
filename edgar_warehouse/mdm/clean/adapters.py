"""Configuration-selected normalization; identity and field selection stay shared."""

from __future__ import annotations

from .evidence import assertion, subject_key
from .store import canonical


def value(row: dict, path: str):
    result = row
    for part in path.split("."):
        if not isinstance(result, dict):
            return None
        result = result.get(part)
    return result


def record_key(row: dict, paths: list[str]) -> str:
    parts = [value(row, p) for p in paths]
    if not parts or any(v is None or v == "" for v in parts):
        raise ValueError("Missing source-record identity")
    return str(parts[0]) if len(parts) == 1 else canonical(parts)


def normalize(
    row: dict, *, source_code: str, contract: dict, publication: dict
) -> dict:
    """Consume approved mapping metadata and a pinned source publication.

    No name-based kind inference, role creation from 13F manager status, or
    automatic attachment to an existing master. Conditional domains retain
    their source artifact until a registered adapter contract supports them.
    """
    mapping = contract["adapter"]
    kind = mapping.get("kind")
    if "kind_field" in mapping:
        kind = mapping["kind_values"].get(value(row, mapping["kind_field"]))
    if not kind:
        raise ValueError(
            "Unresolved source identity kind; retain source artifact for review"
        )
    key = record_key(row, mapping["record_key"])
    identifiers = {}
    for namespace, path in mapping.get("identifiers", {}).items():
        item = value(row, path)
        if item is not None and str(item).strip():
            identifiers[namespace] = str(item).strip()
    fields = {
        name: value(row, path) for name, path in mapping.get("fields", {}).items()
    }
    profiles = []
    for spec in mapping.get("profiles", []):
        registration = value(row, spec["registration"])
        if registration is None:
            continue
        profiles.append(
            {
                "role": spec["role"],
                "authority": spec["authority"],
                "registration": str(registration),
                "jurisdiction": value(row, spec["jurisdiction"])
                if spec.get("jurisdiction")
                else None,
                "valid_from": value(row, spec["valid_from"]),
                "valid_to": value(row, spec["valid_to"])
                if spec.get("valid_to")
                else None,
                "fields": {
                    name: value(row, path)
                    for name, path in spec.get("fields", {}).items()
                },
            }
        )
    relationships = []
    for spec in mapping.get("relationships", []):
        try:
            target = record_key(row, spec["target_key"])
        except ValueError:
            continue
        relationships.append(
            {
                "type": spec["type"],
                "target_subject": subject_key(spec["target_source"], target),
                "scope": spec.get("scope", ""),
                "valid_from": value(row, spec["valid_from"]),
                "valid_to": value(row, spec["valid_to"])
                if spec.get("valid_to")
                else None,
                "properties": {
                    name: value(row, path)
                    for name, path in spec.get("properties", {}).items()
                },
            }
        )
    return assertion(
        source_code=source_code,
        record_key=key,
        publication_key=publication["publication_key"],
        revision=publication["revision"],
        effective_at=publication.get("effective_at"),
        kind=kind,
        fields=fields,
        identifiers=identifiers,
        profiles=profiles,
        relationships=relationships,
        schema_version=contract["schema_version"],
        provenance={
            "artifact_sha256": publication["artifact_sha256"],
            "member": publication["member"],
            "record_key": key,
            "adapter_version": mapping["version"],
        },
    )
