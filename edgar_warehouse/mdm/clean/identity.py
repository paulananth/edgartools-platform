"""Replay accepted identity decisions, never infer a merge from a field winner."""

from __future__ import annotations

from dataclasses import dataclass, field

from .evidence import instant
from .store import Conflict


@dataclass
class IdentityState:
    canonical: dict[str, str]
    bindings: dict[str, str]
    exclusions: list[tuple[str, str]]
    overrides: list[dict]
    retired_sources: set[str]
    # A record the rules could not decide (ticket 13): subject -> the Company
    # it was linked to, which readers see flagged. Left out of matching.
    quarantined: dict[str, str] = field(default_factory=dict)


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
    revoked_at: dict[str, object] = {}
    # A revoked bind (ticket 13): its subject, and when it was bound and
    # unbound. Between the two the subject is still bound there.
    unbound: dict[str, list[tuple]] = {}
    for d in ordered:
        if d["operation"] in {"reverse", "revoke"}:
            target = by_id.get(d.get("target"))
            if not target or instant(target["at"]) >= instant(d["at"]):
                raise Conflict("Reversal/revocation must reference an earlier decision")
            expected = (
                {"merge"}
                if d["operation"] == "reverse"
                else {"override", "exclude", "reverse", "bind", "quarantine"}
            )
            if target["operation"] not in expected:
                raise Conflict("Invalid reversal/revocation target")
            if target["operation"] == "bind":
                if d["target"] in revoked:
                    # Once only: a second revocation would unbind whatever
                    # the record was bound to since (ticket 13).
                    raise Conflict("This bind is already revoked")
                if (d.get("subject"), d.get("entity_id")) != (target["subject"], target["entity_id"]):
                    raise Conflict("A revocation names the bind it revokes: its subject and entity")
                unbound.setdefault(target["subject"], []).append(
                    (instant(target["at"]), instant(d["at"]), str(target["entity_id"]))
                )
            revoked.add(d["target"])
            revoked_at[d["target"]] = instant(d["at"])
    # A quarantine holds from its time until its lifting revocation, if any.
    held: dict[str, list[tuple]] = {}
    for d in ordered:
        if d["operation"] == "quarantine":
            held.setdefault(d["subject"], []).append(
                (instant(d["at"]), revoked_at.get(d["decision_id"]))
            )
    quarantined = {}

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
            if key in revoked:
                continue  # corrected: the subject is unbound (ticket 13)
            if any(
                bound_at <= instant(d["at"]) < unbound_at and other != entity
                for bound_at, unbound_at, other in unbound.get(subject, [])
            ):
                raise Conflict(
                    "Moving an established source binding requires a correction contract"
                )
            if subject in bindings and bindings[subject] != entity:
                raise Conflict(
                    "Moving an established source binding requires a correction contract"
                )
            if any(
                start <= instant(d["at"]) and (end is None or instant(d["at"]) < end)
                for start, end in held.get(subject, [])
            ):
                raise Conflict("A quarantined record is left out of matching")
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
        elif op == "quarantine":
            subject = d.get("subject")
            if not subject or not d.get("entity_id"):
                raise Conflict("A quarantine names its record and the Company it was linked to")
            root(str(d["entity_id"]))
            at = instant(d["at"])
            if subject in bindings or any(
                bound_at <= at < unbound_at for bound_at, unbound_at, _ in unbound.get(subject, [])
            ):
                raise Conflict("Revoke the record's bind before quarantining it")
            if key not in revoked:
                quarantined[subject] = str(d["entity_id"])
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
    return IdentityState(canonical, bindings, exclusions, overrides, retired, quarantined)
