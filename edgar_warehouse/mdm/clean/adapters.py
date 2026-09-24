"""Configuration-selected normalization; identity and field selection stay shared."""

from __future__ import annotations

import re
from typing import Any

from .activation import activated
from .classification import fired, resolve_rule
from .evidence import KINDS, assertion, subject_key
from .store import Conflict, canonical


class UnsupportedRecord(ValueError):
    """A source defect or unsupported domain, not an adapter programming error.

    `detail` is what the deferred record keeps beside its reason, so a record
    set aside by a classification rule still names the rule, version, step and
    verdict that set it aside.
    """

    def __init__(self, reason: str, detail: dict | None = None):
        self.reason = reason
        self.detail = detail or {}
        super().__init__(reason)


def _sec_cik(item) -> str:
    value = str(item).strip()
    if not value.isascii() or not value.isdigit() or len(value) > 10 or int(value) == 0:
        raise UnsupportedRecord("invalid_cik")
    return value.zfill(10)


def _lei(item) -> str:
    value = str(item).strip()
    if not re.fullmatch(r"[A-Z0-9]{18}[0-9]{2}", value):
        raise UnsupportedRecord("invalid_lei")
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in value)
    if int(digits) % 97 != 1:
        raise UnsupportedRecord("invalid_lei_checksum")
    return value


# EDGAR's two-letter codes for US states, DC and the inhabited territories are
# their USPS codes, which ISO 3166-2:US reuses behind "US-". Every other EDGAR
# code (Canadian provinces A0-B0, foreign countries such as E9 or X0) is not
# converted: it raises, and a field then records the value as unknown rather
# than guessing a country.
US_CODES = frozenset(
    ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC", "PR", "VI", "GU", "AS", "MP"]
)


def _edgar_state_iso3166(item) -> str:
    value = str(item).strip().upper()
    if value not in US_CODES:
        raise UnsupportedRecord("unconverted_jurisdiction")
    return f"US-{value}"


# One table of named formats, read by identifiers, record keys, fields and
# registration alike, so adding one is one entry here (GoF consult,
# 2026-09-24: the names were listed in two places and a third was coming).
FORMATS = {
    "sec_cik": _sec_cik,
    "lei": _lei,
    "edgar_state_iso3166": _edgar_state_iso3166,
}


def format_value(item, format_name=None):
    if format_name is None:
        return str(item).strip()
    if format_name not in FORMATS:
        raise ValueError("Unconfigured identifier format")
    return FORMATS[format_name](item)


def field_value(row: dict, path: str, format_name: str | None):
    """A field's value, converted by its declared format when it has one.

    A value the format cannot convert becomes unknown for this field rather
    than setting the whole record aside: the rest of the record is still good
    evidence, and the raw value stays under whatever other field maps it.
    """
    item = value(row, path)
    if format_name is None or item is None:
        return item
    if isinstance(item, str) and not item.strip():
        return None
    try:
        return format_value(item, format_name)
    except UnsupportedRecord:
        return None


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


def classify_record(
    row: dict, named: dict, policy: dict | None, source_code: str
) -> tuple[str, dict]:
    """Run the classification rule a Dataset Contract names, at read time.

    The decided kind is hashed into the assertion id, so it is settled here and
    never afterwards (company mastering ticket 03, decision 4). A verdict that
    decides no kind, or one the policy has not activated, sets the record aside
    for a Steward with the rule that decided it; it never becomes a kind by
    default (`policy-language.md` §6, §9).
    """
    if policy is None:
        raise Conflict(
            "A Dataset Contract naming a classification rule requires its pinned "
            "Mastering Policy"
        )
    rule = resolve_rule(policy, named)
    if rule.get("source") not in (None, source_code):
        # A rule reads the field paths of the source it was written for; run
        # against another source it would test fields that are not there.
        raise Conflict(
            f"Classification rule {rule['rule_id']} is written for "
            f"{rule['source']}, not {source_code}"
        )
    verdict, step = fired(rule, row, policy["kinds"][named["kind"]])
    labelled = {
        "rule_id": rule["rule_id"],
        "version": rule["version"],
        "step": step,
    }
    if verdict not in KINDS:
        raise UnsupportedRecord(
            f"classification_{verdict}",
            {"classification": {**labelled, "verdict": verdict}},
        )
    if not activated(policy, named["kind"], rule, verdict):
        raise UnsupportedRecord(
            "classification_not_activated",
            {"classification": {**labelled, "verdict": verdict}},
        )
    return verdict, labelled


def normalize(
    row: dict,
    *,
    source_code: str,
    contract: dict,
    publication: dict,
    mapping_version: int = 1,
    policy: dict | None = None,
) -> dict:
    """Consume approved mapping metadata and a pinned source publication.

    No name-based kind inference, role creation from 13F manager status, or
    automatic attachment to an existing master. Conditional domains retain
    their source artifact until a registered adapter contract supports them.

    The kind comes from the contract when every record of the source is one
    kind, and from the Mastering Policy rule the contract names when a record
    may be one of several. `policy` is needed only for the second.
    """
    mapping = contract["adapter"]
    if not isinstance(row, dict):
        raise UnsupportedRecord("invalid_record_shape")
    labelled = None
    kind = mapping.get("kind")
    if mapping.get("classification"):
        kind, labelled = classify_record(
            row, mapping["classification"], policy, source_code
        )
    elif "kind_field" in mapping:
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
    field_formats = mapping.get("field_formats", {})
    fields = {
        name: field_value(row, path, field_formats.get(name))
        for name, path in mapping.get("fields", {}).items()
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
    if labelled is not None:
        # Inside the hashed body, so the record explains what labelled it with
        # no lookup elsewhere. Absent means the contract's own table decided,
        # before governed rules existed (ticket 03, decision 6).
        provenance["classification"] = labelled
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
        # Which registered reading of this contract produced the record. A
        # re-read under a corrected mapping states its own version, so it sits
        # beside its predecessor rather than colliding with it.
        mapping_version=mapping_version,
        provenance=provenance,
    )
