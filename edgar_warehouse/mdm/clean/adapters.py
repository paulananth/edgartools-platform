"""Configuration-selected normalization; identity and field selection stay shared."""

from __future__ import annotations

import re
from typing import Any

from .evidence import assertion, subject_key
from .store import canonical


class UnsupportedRecord(ValueError):
    """A source defect or unsupported domain, not an adapter programming error."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def format_value(item, format_name=None):
    if format_name is None:
        return str(item).strip()
    if format_name == "sec_cik":
        value = str(item).strip()
        if (
            not value.isascii()
            or not value.isdigit()
            or len(value) > 10
            or int(value) == 0
        ):
            raise UnsupportedRecord("invalid_cik")
        return value.zfill(10)
    if format_name == "gleif_lei":
        value = str(item).strip()
        if not re.fullmatch(r"[A-Z0-9]{18}[0-9]{2}", value):
            raise UnsupportedRecord("invalid_lei")
        digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in value)
        if int(digits) % 97 != 1:
            raise UnsupportedRecord("invalid_lei_checksum")
        return value
    raise ValueError("Unconfigured identifier format")


def value(row: dict, path: str):
    result: Any = row
    for part in path.split("."):
        if not isinstance(result, dict):
            return None
        result = result.get(part)
    return result


def record_key(row: dict, paths: list[str]) -> str:
    parts = [value(row, p) for p in paths]
    if not parts or any(v is None or v == "" for v in parts):
        raise UnsupportedRecord("missing_record_identity")
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
    if not isinstance(row, dict):
        raise UnsupportedRecord("invalid_record_shape")
    kind = mapping.get("kind")
    if "kind_field" in mapping:
        source_kind = value(row, mapping["kind_field"])
        if source_kind is not None and not isinstance(source_kind, str):
            raise UnsupportedRecord("invalid_identity_kind")
        kind = mapping["kind_values"].get(source_kind)
    if not kind:
        raise UnsupportedRecord("unsupported_identity_kind")
    key = record_key(row, mapping["record_key"])
    key = format_value(key, mapping.get("record_key_format"))
    identifiers = {}
    for namespace, path in mapping.get("identifiers", {}).items():
        item = value(row, path)
        if item is not None and str(item).strip():
            identifiers[namespace] = format_value(
                item, mapping.get("identifier_formats", {}).get(namespace)
            )
    fields = {
        name: value(row, path) for name, path in mapping.get("fields", {}).items()
    }
    if mapping.get("field_shape") == "nullable_text" and any(
        v is not None and not isinstance(v, str) for v in fields.values()
    ):
        raise UnsupportedRecord("invalid_field_shape")
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
        relationship_type = spec.get("type")
        if "type_field" in spec:
            relationship_type = spec["type_values"].get(value(row, spec["type_field"]))
            if not relationship_type:
                raise UnsupportedRecord("unsupported_relationship_type")
        try:
            target = record_key(row, spec["target_key"])
        except ValueError:
            continue
        relationships.append(
            {
                "type": relationship_type,
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
    provenance = {
        "artifact_sha256": publication["artifact_sha256"],
        "member": publication["member"],
        "record_key": key,
        "adapter_version": mapping["version"],
    }
    if publication.get("record_locator"):
        provenance["record_locator"] = publication["record_locator"]
    if mapping.get("source_record_provenance"):
        # Delivery member paths, hashes and line positions describe occurrences,
        # not source assertions. They remain pinned in the input manifest.
        provenance = {"record_key": key, "adapter_version": mapping["version"]}
    if mapping.get("provenance"):
        provenance["source"] = {
            name: value(row, path) for name, path in mapping["provenance"].items()
        }
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
        provenance=provenance,
    )
