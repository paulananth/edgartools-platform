"""Replay accepted identity decisions, never infer a merge from a field winner."""

from __future__ import annotations

from dataclasses import dataclass

from .evidence import instant
from .store import Conflict


@dataclass
class IdentityState:
    canonical: dict[str, str]
    bindings: dict[str, str]
    exclusions: list[tuple[str, str]]
    overrides: list[dict]
    retired_sources: set[str]


def replay(identities: list[dict], decisions: list[dict], as_of: str) -> IdentityState:
    ids = {str(i["entity_id"]): i for i in identities}
    parent = {key: key for key in ids}
    bindings = {}
    exclusions = []
    overrides = []
    retired = set()
    used = {}
    merge_components = {}
    clock = instant(as_of)
    ordered = sorted(
        (d for d in decisions if instant(d["at"]) <= clock),
        key=lambda d: (instant(d["at"]), d["decision_id"]),
    )
    by_id = {d["decision_id"]: d for d in ordered}
    revoked = set()
    for d in ordered:
        if d["operation"] in {"reverse", "revoke"}:
            target = by_id.get(d.get("target"))
            if not target or instant(target["at"]) >= instant(d["at"]):
                raise Conflict("Reversal/revocation must reference an earlier decision")
            expected = (
                {"merge"}
                if d["operation"] == "reverse"
                else {"override", "exclude", "reverse"}
            )
            if target["operation"] not in expected:
                raise Conflict("Invalid reversal/revocation target")
            revoked.add(d["target"])

    def root(key):
        if key not in parent:
            raise Conflict("Unknown identity")
        while parent[key] != key:
            key = parent[key]
        return key

    # Dependency lists are retained when a merge is accepted. Never silently
    # reinterpret a later merge against a partition it was not reviewed for.
    for d in ordered:
        if (
            d["operation"] == "merge"
            and d["decision_id"] not in revoked
            and set(d.get("depends_on", [])) & revoked
        ):
            raise Conflict("Dependent merge requires review before reversal")
    for d in ordered:
        op = d["operation"]
        key = d["decision_id"]
        if op == "bind":
            subject = d["subject"]
            entity = str(d["entity_id"])
            root(entity)
            if subject in bindings and bindings[subject] != entity:
                raise Conflict(
                    "Moving an established source binding requires a correction contract"
                )
            if not d.get("evidence"):
                raise Conflict("Binding requires source assertion evidence")
            bindings[subject] = entity
        elif op == "merge":
            if key in revoked:
                reversals = [
                    x
                    for x in ordered
                    if x["operation"] == "reverse" and x["target"] == key
                ]
                if any(x["decision_id"] not in revoked for x in reversals):
                    exclusions.append((str(d["left"]), str(d["right"])))
                continue
            left = root(str(d["left"]))
            right = root(str(d["right"]))
            if left == right:
                raise Conflict("Already consolidated identities")
            if ids[left]["kind"] != ids[right]["kind"]:
                raise Conflict("Incompatible identity kinds")
            members = {i for i in ids if root(i) in {left, right}}
            actual_dependencies = {
                event
                for event, component in merge_components.items()
                if component & members
            }
            if not actual_dependencies.issubset(set(d.get("depends_on", []))):
                raise Conflict("Merge is missing dependency evidence")
            survivor = d.get("survivor") or min(
                [left, right], key=lambda i: (instant(str(ids[i]["published_at"])), i)
            )
            if survivor not in {left, right}:
                raise Conflict("Survivor must be a current identity")
            parent[right if survivor == left else left] = survivor
            merge_components[key] = members
            used[key] = d
        elif op == "exclude" and key not in revoked:
            exclusions.append((str(d["left"]), str(d["right"])))
        elif op == "override" and key not in revoked:
            if not d.get("evidence"):
                raise Conflict("Override requires evidence")
            if d.get("expires_at") and instant(d["expires_at"]) <= clock:
                continue
            overrides.append(d)
        elif op == "retire_source":
            if not d.get("evidence"):
                raise Conflict("Retirement requires evidence")
            retired.add(d["source_code"])
        elif op not in {"reverse", "revoke", "override", "exclude"}:
            raise Conflict("Unsupported decision operation")
    canonical = {key: root(key) for key in ids}
    for left, right in exclusions:
        if root(left) == root(right):
            raise Conflict("Match Exclusion blocks consolidation")
    return IdentityState(canonical, bindings, exclusions, overrides, retired)
