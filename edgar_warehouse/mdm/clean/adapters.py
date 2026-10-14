"""Configuration-selected normalization; identity and field selection stay shared."""

from __future__ import annotations

import hashlib
import re
import unicodedata
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


class MappingError(Exception):
    """A mapping that cannot run as written. Not a ValueError, so it stops the
    run instead of setting records aside as source defects."""


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


def _name_id(item) -> str:
    """An id made from a name, for a record with no id another source shares
    (operator, 2026-10-06: "no id exists you just need to create a id using
    name", kept in the cross-reference table). NFKC, case fold, split on every
    run of characters that is not a letter or a digit; every token kept, so
    "class a" and "class c" stay apart; the sha256 of the tokens. One recipe
    for every source, so two sources' records with one name share it. The
    profiling skill's `name_matching.name_id` computes the same value."""
    folded = unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", str(item)).casefold())
    tokens = [t for t in re.split(r"[^\w]+|_", folded) if t]
    if not tokens:
        raise UnsupportedRecord("invalid_name")
    return hashlib.sha256(("name_id@1\x1f" + " ".join(tokens)).encode("utf-8")).hexdigest()


# One table of named formats, read by identifiers, record keys and
# registration alike, so adding one is one entry here (GoF consult,
# 2026-09-24: the names were listed in two places and a third was coming).
FORMATS = {
    "sec_cik": _sec_cik,
    "lei": _lei,
    "name_id@1": _name_id,
}


def format_value(item, format_name=None):
    if format_name is None:
        return str(item).strip()
    if format_name not in FORMATS:
        raise ValueError(f"Unconfigured format: {format_name}")
    return FORMATS[format_name](item)


def value(row: dict, path: str):
    if path == ".":  # the whole record, as a provenance path names it
        return row
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


def _configured_values(row: dict, mapping: dict, column: str) -> dict:
    from edgar_warehouse.rules.source_engine import SourceRejected
    from edgar_warehouse.workers.source_mapping import project_record

    try:
        return project_record(row, _reading(mapping), column=column)
    except SourceRejected as error:
        if error.code in {"value_type", "join_shape"}:
            raise UnsupportedRecord("invalid_field_shape") from None
        # Configuration and execution failures stop the run, not a record.
        raise


def _reading(mapping: dict) -> dict:
    """The contract's reading: its one statement of a record's fields and
    matching values. A contract without one cannot run (Issue 20 L7)."""
    if not isinstance(mapping.get("reading"), dict):
        raise MappingError("A Dataset Contract states its fields and matching values in adapter.reading")
    return mapping["reading"]


def _fields(row: dict, mapping: dict) -> dict:
    """A row's mapped fields, as the contract's reading states them. Blank
    text is unknown, never a value: a source that sends "" has said nothing,
    and a blank must not win a field or show in the master (operator,
    2026-09-24); the reading says so with `null_if_blank`."""
    return _configured_values(row, mapping, "fields")


def _matching_values(row: dict, mapping: dict) -> dict:
    """What a matching rule compares, kept with the record and out of its
    fields, so reading it grants no field a value (ticket 08): the reading's
    `matching` column."""
    return _configured_values(row, mapping, "matching")


def _refuse(row: dict, mapping: dict) -> None:
    """The contract's own record checks come first: a record they set aside
    defers with their reason, before its kind, key or fields are read.

    After the reading's checks, `every_in` rules test each value of a list
    (the engine's checks test one value): `{path, item, values, missing,
    reason}` sets the record aside with `missing` when the path holds no
    value and with `reason` when one is not in `values`. `retained_as` names
    the reason every remaining record waits with: a source whose records are
    evidence only, never an identity."""
    from edgar_warehouse.workers.source_mapping import record_refusal

    if reason := record_refusal(row, _reading(mapping)):
        raise UnsupportedRecord(reason)
    for rule in mapping.get("every_in", []):
        node = value(row, rule["path"])
        found = _as_list(node) if node else []  # empty text, list or object: none
        if not found:
            raise UnsupportedRecord(rule["missing"])
        if any(not isinstance(item, dict) or not isinstance(item.get(rule["item"]), str)
               or item[rule["item"]] not in rule["values"] for item in found):
            raise UnsupportedRecord(rule["reason"])
    if mapping.get("retained_as"):
        raise UnsupportedRecord(mapping["retained_as"])


def mapped_values(row: dict, contract: dict) -> tuple[dict, dict, dict | None]:
    """A row's mapped fields and matching values, after the feed's data
    quality rule: what `normalize` puts on a record, read by the same parts,
    and what the cascade's census reads for every filer and entity, a Company
    or not (ticket 21), so the two cannot differ."""
    _refuse(row, contract["adapter"])
    fields = _fields(row, contract["adapter"])
    matching = _matching_values(row, contract["adapter"])
    return fields, matching, _quality(contract, fields, matching)


def _quality(contract: dict, fields: dict, matching: dict) -> dict | None:
    """Ticket 22: the feed's fixes and checks, on the mapped values, before
    the record's fingerprint. Inside the hashed body, so the record says
    which quality version fixed or withheld what."""
    if not contract.get("quality"):
        return None
    from .quality import apply

    return apply(contract["quality"], fields, matching)


def _named_values(row: dict, paths: dict, formats: dict) -> dict[str, str]:
    """namespace → path into namespace → formatted value; an empty value is left out."""
    found = {}
    for namespace, path in paths.items():
        item = value(row, path)
        if item is not None and str(item).strip():
            found[namespace] = format_value(item, formats.get(namespace))
    return found


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
    _refuse(row, mapping)
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
    identifiers = _named_values(row, mapping.get("identifiers", {}), mapping.get("identifier_formats", {}))
    # Lookup-only ids (profiling ticket 03): kept with the record, never bound.
    cross_references = _named_values(
        row, mapping.get("cross_references", {}), mapping.get("cross_reference_formats", {})
    )
    fields = _fields(row, mapping)
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
        for scope in _scopes(row, spec):
            link = _link(scope, spec)
            if link:
                relationships.append(link)
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
    # Matching values and quality are read after the relationships, as
    # before, so a record set aside for another reason keeps that reason.
    matching = _matching_values(row, mapping)
    quality = _quality(contract, fields, matching)
    if matching:
        provenance["matching"] = matching
    if quality is not None:
        provenance["quality"] = quality
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
        # A contract may name where each record states its own time (GLEIF's
        # LastUpdateDate); otherwise the publication states one for all.
        effective_at=value(row, mapping["effective_at"]) if mapping.get("effective_at") else publication.get("effective_at"),
        kind=kind,
        fields=fields,
        identifiers=identifiers,
        cross_references=cross_references,
        profiles=profiles,
        relationships=relationships,
        schema_version=contract["schema_version"],
        # Which registered reading of this contract produced the record. A
        # re-read under a corrected mapping states its own version, so it sits
        # beside its predecessor rather than colliding with it.
        mapping_version=mapping_version,
        provenance=provenance,
    )


def _as_list(node) -> list:
    """A source list as a list: a lone item is a list of one, nothing is none."""
    if node is None:
        return []
    return node if isinstance(node, list) else [node]


def _reached(node, parts: list[str]):
    """Every value a path reaches, stepping into each element of a list."""
    if isinstance(node, list):
        for element in node:
            yield from _reached(element, parts)
    elif not parts:
        yield node
    elif isinstance(node, dict):
        yield from _reached(node.get(parts[0]), parts[1:])


def _scopes(row: dict, spec: dict):
    """What one relationship mapping's paths read (profiling ticket 04c).

    With `each`, one scope per item of that list, the item under `item.`; with
    none, the record alone. Each `find` adds, under its name, the first item of
    another list whose `where` paths all match: a constant, or `{path: ...}`
    read from the scope; a list of constants matches any of them. A `where`
    path through a nested list matches when any element does. No match leaves
    the name empty, so its paths read nothing; with `one: <reason>`, anything
    but exactly one match sets the record aside with that reason.
    """
    names = ({"item"} if "each" in spec else set()) | set(spec.get("find", {}))
    if names & set(row):
        raise MappingError(f"A relationship mapping's names {sorted(names & set(row))} hide the record's own fields")
    for name, lookup in spec.get("find", {}).items():
        if not isinstance(lookup, dict) or not lookup.get("in") or not lookup.get("where"):
            raise MappingError(f"A relationship mapping's find {name!r} names its list (in) and conditions (where)")
    for item in _as_list(value(row, spec["each"])) if "each" in spec else [None]:
        scope = {**row, "item": item} if "each" in spec else dict(row)
        for name, lookup in spec.get("find", {}).items():
            accepted = {}
            for path, condition in lookup["where"].items():
                if isinstance(condition, dict):
                    condition = value(scope, condition["path"])
                accepted[path] = set(condition) if isinstance(condition, list) else {condition} - {None}
            found = [
                candidate
                for candidate in _as_list(value(scope, lookup["in"]))
                if all(
                    accepted[path].intersection(
                        v for v in _reached(candidate, path.split(".")) if not isinstance(v, (dict, list))
                    )
                    for path in accepted
                )
            ]
            if lookup.get("one") and len(found) != 1:
                raise UnsupportedRecord(lookup["one"])
            scope[name] = found[0] if found else None
        yield scope


def _time(item, spec: dict):
    """A link's time as the mapping writes it: as read, `time_format: instant` as
    an ISO 8601 instant, or `time_format: date` a calendar date (YYYY-MM-DD) as
    the instant its day starts in UTC (a Form 4's event date has no time or zone);
    a time that is not one sets the record aside."""
    form = spec.get("time_format")
    if item is None or form not in ("instant", "date"):
        return item
    from datetime import date

    from .evidence import instant

    try:
        if form == "date":
            day = date.fromisoformat(item).isoformat()
            if day != item:  # fromisoformat also takes 20260105 and week dates
                raise ValueError(item)
            return f"{day}T00:00:00+00:00"
        return instant(item).isoformat()
    except (TypeError, ValueError):
        raise UnsupportedRecord("invalid_time") from None


# A link's own rules, each naming the reason it sets the record aside with
# (the Mapping Document describes each: `mapdoc.LINK_RULES`).
LINK_RULE_NAMES = ("ends", "interval", "status")


def _refuse_link(scope: dict, spec: dict) -> None:
    """A link's own rules, each with the reason it sets the record aside with:
    `interval` (a start, before any end) and `status` (one of `values`, and an
    end for each status in `need_end`). `ends` (a link that names no end) is
    enforced in `_link`, where the ends are read."""
    if not (spec.get("interval") or spec.get("status")):
        return
    start = _time(value(scope, spec["on"] if "capacity" in spec else spec["valid_from"]), spec)
    end = _time(value(scope, spec["valid_to"]), spec) if spec.get("valid_to") else None
    if rule := spec.get("interval"):
        from .evidence import instant

        try:
            if not start or (end and instant(start) >= instant(end)):
                raise UnsupportedRecord(rule["reason"])
        except (TypeError, ValueError) as error:
            if isinstance(error, UnsupportedRecord):
                raise
            raise UnsupportedRecord("invalid_time") from None
    if rule := spec.get("status"):
        status = value(scope, rule["path"])
        if status not in rule["values"] or (status in rule.get("need_end", []) and not end):
            raise UnsupportedRecord(rule["reason"])


def _link(scope: dict, spec: dict) -> dict | None:
    """One link a mapping states, read from its scope; none without its ends."""
    if "ends" in spec and not (isinstance(spec["ends"], dict) and spec["ends"].get("reason")):
        raise MappingError("A link's ends rule names its reason")
    _refuse_link(scope, spec)
    relationship_type = spec.get("type")
    if "type_field" in spec:
        relationship_type = spec["type_values"].get(value(scope, spec["type_field"]))
        if not relationship_type:
            raise UnsupportedRecord("unsupported_relationship_type")
    try:
        target = record_key(scope, spec["target_key"])
        # A link may start at another record (a GLEIF relationship record
        # starts at its child's Level 1 record), as it ends at one.
        start = (
            {"source_subject": subject_key(spec["source_source"], record_key(scope, spec["source_key"]))}
            if spec.get("source_key")
            else {}
        )
    except ValueError:
        # With `ends`, a record that names no end sets itself aside; without
        # it, a list item with no end is simply no link.
        if "ends" not in spec:
            return None
        raise UnsupportedRecord(spec["ends"]["reason"]) from None
    link = {
        **start,
        "type": relationship_type,
        "target_subject": subject_key(spec["target_source"], target),
        "scope": spec.get("scope", ""),
        "valid_to": _time(value(scope, spec["valid_to"]), spec) if spec.get("valid_to") else None,
        "properties": {name: value(scope, path) for name, path in spec.get("properties", {}).items()},
    }
    if "capacity" not in spec:
        return {**link, "valid_from": _time(value(scope, spec["valid_from"]), spec)}
    # A link in a capacity (a Person's: director, officer, ten-percent owner) is
    # a dated sighting that the Merge Stage folds into periods
    # (relationships.fold_sightings): the capacity held, or dropped, on the
    # record's event date `on`. A filing restates its capacities, so a flag that
    # is not true (false or absent) is a drop; `title` is the period's dated detail.
    if "on" not in spec or "held" not in spec:
        raise MappingError("A link in a capacity names its date (on) and its flag (held)")
    held = value(scope, spec["held"])
    if held not in (True, False, None):  # a flag read as text, say, is not one
        raise UnsupportedRecord("invalid_field_shape")
    on = _time(value(scope, spec["on"]), spec)
    return {
        **link,
        "valid_from": on,
        "capacity": spec["capacity"],
        "on": on,
        "held": held is True,
        "title": value(scope, spec["title"]) if spec.get("title") else None,
    }
