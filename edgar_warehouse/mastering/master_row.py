"""A golden record as the store keeps it, and back (skills/mdm-engineering/MASTER-FIELDS.md).

Survivorship gives one body per master. The store keeps what a reader selects by as columns, each profile as a row, the
identifiers and member records in their own tables, and only the rest as text: the field values with their attribution.
`split` and `assemble` are each other's inverse; the store calls them, and no reader sees the split.
"""
from __future__ import annotations

import hashlib
import json

COLUMNS = ("kind", "status", "canonical_id", "policy_digest", "kind_version")
STAMPS = ("policy_digest", "kind_version")  # the same on every field of a master: kept once
HELD_ELSEWHERE = ("entity_id", "identifiers", "subjects", "profiles")  # the key, and the rows of other tables


def split(body: dict) -> tuple[dict, list[dict], str]:
    """(columns, profiles in order, text). The text holds every key the columns and the tables do not."""
    fields = body.get("fields")
    stamps = {}
    if isinstance(fields, dict):
        for value in fields.values():
            for stamp in STAMPS:
                if isinstance(value, dict) and stamp in value:
                    if stamps.setdefault(stamp, value[stamp]) != value[stamp]:
                        raise ValueError(f"A master's fields carry two {stamp}s: survivorship stamps a master once")
        values = [value for value in fields.values() if isinstance(value, dict)]
        for stamp in stamps:
            if sum(stamp in value for value in values) != len(values):
                raise ValueError(f"Some of a master's fields carry no {stamp}: survivorship stamps every field")
    columns = {"kind": body.get("kind"), "status": body.get("status"), "canonical_id": body.get("canonical_id"),
               "policy_digest": stamps.get("policy_digest"), "kind_version": stamps.get("kind_version")}
    rest = {key: value for key, value in body.items() if key not in HELD_ELSEWHERE and key not in ("kind", "status", "canonical_id")}
    if isinstance(fields, dict):
        rest["fields"] = {name: ({k: v for k, v in value.items() if k not in STAMPS} if isinstance(value, dict) else value)
                          for name, value in fields.items()}
    rest["_held"] = sorted(key for key in HELD_ELSEWHERE if key in body)  # which of them the body had, so none is invented
    # What moved to the other tables still changes the text (so the master's change number moves) and is checked on assembly.
    rest["_held_sha256"] = held_digest(body)
    return columns, list(body.get("profiles") or []), json.dumps(rest, sort_keys=True, separators=(",", ":"))


def assemble(entity_id: str, columns: dict, text: str, identifiers: dict[str, list[str]], subjects: list[str],
             profiles: list[dict]) -> dict:
    """The body survivorship gave, from the columns, the text and the rows of the other tables."""
    rest = json.loads(text)
    held = set(rest.pop("_held", []))
    expected = rest.pop("_held_sha256", None)
    body = {"kind": columns["kind"], "status": columns["status"], "canonical_id": columns["canonical_id"], **rest}
    if isinstance(body.get("fields"), dict):
        stamps = {stamp: columns[stamp] for stamp in STAMPS if columns.get(stamp) is not None}
        body["fields"] = {name: ({**value, **stamps} if isinstance(value, dict) else value) for name, value in body["fields"].items()}
    for key, value in (("entity_id", entity_id), ("identifiers", {ns: sorted(values) for ns, values in sorted(identifiers.items())}),
                       ("subjects", sorted(subjects)), ("profiles", profiles)):
        if key in held:
            body[key] = value
    for key in ("kind", "status", "canonical_id"):
        if body[key] is None:
            del body[key]
    if expected is not None and held_digest(body) != expected:
        raise ValueError(f"Master {entity_id}: its identifier, member or profile rows differ from what was written")
    return body


def held_digest(body: dict) -> str:
    """The digest of what a master keeps in other tables: its identifiers, members and profiles."""
    held = {key: body[key] for key in HELD_ELSEWHERE if key in body and key != "entity_id"}
    return hashlib.sha256(json.dumps(held, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
