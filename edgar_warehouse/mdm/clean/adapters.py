"""Configuration-selected normalization; identity and field selection stay shared."""

from __future__ import annotations

import re
from typing import Any

from .activation import activated
from .classification import fired, probable_kind, resolve_rule
from .evidence import KINDS, assertion, subject_key
from .store import Conflict, canonical


class UnsupportedRecord(ValueError):
    """A source defect or unsupported domain, not an adapter programming error.

    `detail` is what the deferred record keeps beside its reason, so a record
    set aside by a classification rule still names the rule, version, step and
    verdict that set it aside.
    """

    def __init__(
        self,
        reason: str,
        detail: dict | None = None,
        probable_kind: str | None = None,
    ):
        self.reason = reason
        self.detail = detail or {}
        # The kind the record probably is, when a rule step or the contract
        # says (CONTEXT.md, Probable Kind); the deferred record keeps it.
        self.probable_kind = probable_kind
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


# One table of named formats, read by identifiers, record keys and
# registration alike, so adding one is one entry here (GoF consult,
# 2026-09-24: the names were listed in two places and a third was coming).
FORMATS = {
    "sec_cik": _sec_cik,
    "lei": _lei,
}


def format_value(item, format_name=None):
    if format_name is None:
        return str(item).strip()
    if format_name not in FORMATS:
        raise ValueError(f"Unconfigured format: {format_name}")
    return FORMATS[format_name](item)


def _blank(item) -> bool:
    return isinstance(item, str) and not item.strip()


ADDRESS_COMPONENTS = frozenset(
    {"street", "street2", "city", "region", "postcode", "country"}
)


def mapped_field(row: dict, name: str, spec: str | dict):
    """Read one coherent field, including a source's complete address group."""
    if isinstance(spec, str):
        item = value(row, spec)
        return None if _blank(item) else item
    components = spec.get("components") if isinstance(spec, dict) else None
    if name != "address" or not isinstance(components, dict) or not components:
        raise UnsupportedRecord("invalid_field_mapping")
    if set(components) - ADDRESS_COMPONENTS:
        raise UnsupportedRecord("invalid_field_mapping")
    address = {}
    for part, path in components.items():
        if isinstance(path, str) and path:
            item = value(row, path)
        elif (
            part == "street2"
            and isinstance(path, dict)
            and set(path) == {"lines"}
            and isinstance(path["lines"], str)
            and path["lines"]
        ):
            lines = value(row, path["lines"])
            if lines is not None and not isinstance(lines, list):
                raise UnsupportedRecord("invalid_field_shape")
            if lines is not None and any(
                not isinstance(line, dict) or not isinstance(line.get("$"), str)
                for line in lines
            ):
                raise UnsupportedRecord("invalid_field_shape")
            item = "\n".join(line["$"].strip() for line in lines if line["$"].strip()) if lines else None
        else:
            raise UnsupportedRecord("invalid_field_mapping")
        if item is None or _blank(item):
            continue
        if not isinstance(item, str):
            raise UnsupportedRecord("invalid_field_shape")
        address[part] = item.strip()
    return address or None


def value(row: dict, path: str):
    result: Any = row
    for part in path.split("."):
        if not isinstance(result, dict):
            return None
        result = result.get(part)
    return result


def category_kind(row: dict, mapping: dict) -> str | None:
    """The kind a `kind_field` contract names for a record's category.

    The kind it accepts, else the category's Probable Kind (CONTEXT.md), else
    None: a category the contract does not name says nothing.
    """
    source_kind = value(row, mapping["kind_field"])
    if not isinstance(source_kind, str):
        return None
    return mapping["kind_values"].get(source_kind) or mapping.get(
        "probable_kind_values", {}
    ).get(source_kind)


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
    probable = probable_kind(rule, step, verdict)
    if verdict not in KINDS:
        raise UnsupportedRecord(
            f"classification_{verdict}",
            {"classification": {**labelled, "verdict": verdict}},
            probable,
        )
    if not activated(policy, named["kind"], rule, verdict):
        raise UnsupportedRecord(
            "classification_not_activated",
            {"classification": {**labelled, "verdict": verdict}},
            probable,
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
            # A category the contract does not accept may still say what the
            # record probably is (GLEIF FUND, BRANCH), so the Stage can sort it.
            raise UnsupportedRecord(
                "unsupported_identity_kind", probable_kind=category_kind(row, mapping)
            )
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
    # Blank text is unknown, never a value: a source that sends "" has said
    # nothing, and a blank must not win a field or show in the master
    # (operator, 2026-09-24).
    fields = {
        name: mapped_field(row, name, spec)
        for name, spec in mapping.get("fields", {}).items()
    }
    if mapping.get("field_shape") == "nullable_text" and any(
        v is not None
        and not isinstance(v, str)
        and not (name == "address" and isinstance(v, dict))
        for name, v in fields.items()
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
    if mapping.get("matching"):
        # What a matching rule compares, kept with the record and out of its
        # fields, so reading it grants no field a value (ticket 08).
        provenance["matching"] = {
            name: value(row, path) for name, path in mapping["matching"].items()
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
