"""Deterministic field selection over retained source assertions."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from .evidence import PROFILE_KINDS, instant
from .store import Conflict, canonical, digest


def profile_key(profile):
    return digest(
        [
            profile.get(k)
            for k in ("role", "authority", "registration", "jurisdiction", "valid_from")
        ]
    )


def current_claims(
    assertions: list[dict], as_of: str, retired: set[str]
) -> dict[str, dict]:
    groups = defaultdict(list)
    for a in assertions:
        if a["source_code"] not in retired and (
            a["effective_at"] is None or instant(a["effective_at"]) <= instant(as_of)
        ):
            groups[a["subject"]].append(a)
    result = {}
    for subject, versions in groups.items():
        claims = {}
        ids = {}
        profiles = []
        profile_fields = {}
        relationships = []
        kind = None
        seen = {}
        for a in sorted(
            versions,
            key=lambda a: (
                a["revision"],
                a.get("mapping_version", 1),
                a["publication_key"],
                a["assertion_id"],
            ),
        ):
            # One source native revision read once must produce one assertion;
            # two contradictory bodies there are a defect in the source. A
            # second *reading* of that revision is not that defect, so the key
            # carries the mapping version (ticket 01, amendment 8).
            reading = (a["revision"], a.get("mapping_version", 1))
            if reading in seen and seen[reading] != a["assertion_id"]:
                raise Conflict("Source native revision has contradictory publications")
            seen[reading] = a["assertion_id"]
            kind = a["kind"]
            for field, item in a["fields"].items():
                if item["op"] == "unknown":
                    continue
                if item["op"] == "retract":
                    claims.pop(field, None)
                else:
                    claims[field] = {
                        **item,
                        "assertion_id": a["assertion_id"],
                        "source_code": a["source_code"],
                        "record_key": a["record_key"],
                        "effective_at": a["effective_at"],
                    }
            # Identifier/profile/edge collections are explicit snapshot fields;
            # adapters must materialize them, including on patch datasets.
            ids = a["identifiers"]
            profiles = a["profiles"]
            continuing = {}
            for profile in profiles:
                key = profile_key(profile)
                values = dict(profile_fields.get(key, {}))
                for field, value in profile.get("fields", {}).items():
                    item = (
                        value
                        if isinstance(value, dict) and "op" in value
                        else (
                            {"op": "unknown"}
                            if value is None
                            else {"op": "value", "value": value}
                        )
                    )
                    if item["op"] == "unknown":
                        continue
                    if item["op"] == "retract":
                        values.pop(field, None)
                    elif item["op"] in {"value", "clear"}:
                        if item["op"] == "value" and item.get("value") is None:
                            raise Conflict("Use unknown for null profile evidence")
                        values[field] = {
                            **item,
                            **{
                                k: a[k]
                                for k in (
                                    "assertion_id",
                                    "source_code",
                                    "record_key",
                                    "effective_at",
                                )
                            },
                        }
                    else:
                        raise Conflict("Unknown profile field operation")
                continuing[key] = values
            profile_fields = continuing
            relationships = a["relationships"]
        result[subject] = {
            "kind": kind,
            "fields": claims,
            "identifiers": ids,
            "profiles": profiles,
            "profile_fields": profile_fields,
            "relationships": relationships,
            "assertion_id": a["assertion_id"],
            "source_meta": {
                k: a[k] for k in ("source_code", "record_key", "effective_at")
            },
        }
    return result


def select_fields(
    kind: str,
    subjects: list[str],
    claims: dict,
    policy: dict,
    overrides: list[dict],
    *,
    as_of: str,
    policy_digest: str,
    entity_id: str = "",
) -> tuple[dict, list[dict], list[dict]]:
    profiles = {}
    profile_claims = defaultdict(dict)
    reviews = []
    for subject in subjects:
        record = claims.get(subject)
        if not record:
            continue
        for profile in record["profiles"]:
            role = profile["role"]
            if kind not in PROFILE_KINDS.get(role, set()):
                reviews.append(
                    {
                        "reason": "incompatible_profile",
                        "subject": subject,
                        "profile": profile,
                    }
                )
                continue
            if not profile.get("authority") or not profile.get("registration"):
                reviews.append(
                    {
                        "reason": "unproven_profile",
                        "subject": subject,
                        "profile": profile,
                    }
                )
                continue
            if not profile.get("valid_from"):
                reviews.append(
                    {
                        "reason": "undated_profile",
                        "subject": subject,
                        "profile": profile,
                    }
                )
                continue
            if profile.get("valid_to") and instant(profile["valid_from"]) >= instant(
                profile["valid_to"]
            ):
                reviews.append(
                    {
                        "reason": "invalid_profile_interval",
                        "subject": subject,
                        "profile": profile,
                    }
                )
                continue
            profile_id = digest(
                [
                    entity_id,
                    role,
                    profile["authority"],
                    profile["registration"],
                    profile.get("jurisdiction"),
                    profile["valid_from"],
                ]
            )
            current = profiles.setdefault(
                profile_id, {**profile, "profile_id": profile_id, "evidence": []}
            )
            current["evidence"].append(record["assertion_id"])
            # Profile values use their own role/field authority policy. Keep raw
            # disagreement in source assertions rather than copying first arrival.
            profile_claims[profile_id][subject] = {
                "fields": record["profile_fields"].get(profile_key(profile), {}),
                "profiles": [],
            }
            current.pop("fields", None)
    recorded_digest, kind_version = _kind_authority(policy, kind, policy_digest)
    fields, field_reviews = _select_values(
        _rules_for(policy, kind),
        subjects,
        claims,
        overrides,
        as_of=as_of,
        policy_digest=recorded_digest,
        kind_version=kind_version,
    )
    reviews.extend(field_reviews)
    for p in profiles.values():
        p["evidence"] = sorted(set(p["evidence"]))
        # Profile values use their own role/field authority policy. Keep raw
        # disagreement in source assertions rather than copying first arrival.
        role_digest, role_name = _role_authority(policy, p["role"], policy_digest)
        values, problems = _select_values(
            policy.get("profile_fields", {}).get(p["role"], {}),
            subjects,
            profile_claims[p["profile_id"]],
            [
                {k: v for k, v in o.items() if k != "profile_id"}
                for o in overrides
                if o.get("profile_id") == p["profile_id"]
            ],
            as_of=as_of,
            policy_digest=role_digest,
            kind_version=role_name,
        )
        p["fields"] = values
        reviews.extend({**r, "profile_id": p["profile_id"]} for r in problems)
    return fields, sorted(profiles.values(), key=lambda p: p["profile_id"]), reviews


def _rules_for(policy: dict, kind: str) -> dict:
    """The field rules a kind selects under.

    One resolver, so that a profile role's rules never have to be wrapped in a
    fabricated policy body to be read, and so that the two body shapes below
    are distinguished in exactly one place.

    Ticket 02 decision 1 moves a kind's field rules under `kinds.<kind>`, so
    that the kind's own version covers all of it. Bodies registered under the
    old top-level `fields` block are immutable and keep working; a body
    carrying both is refused rather than silently preferring one.
    """
    kinds = policy.get("kinds")
    if not kinds:
        return policy.get("fields", {}).get(kind, {})
    if policy.get("fields"):
        raise Conflict("A kind's field rules belong in one place, not two")
    return kinds.get(kind, {}).get("fields", {})


# Which sections of a kind's block decide the winner of a field, and which do
# not. Written down rather than inferred from what the block happens to hold,
# so that adding a section is a decision someone makes once, here, and not a
# silent change to every field's recorded authority. A section in neither list
# is refused by name.
AUTHORITY_SECTIONS = ("fields", "field_group", "field_groups")
NON_AUTHORITY_SECTIONS = (
    "version",  # travels beside the digest, not inside it
    "rules",  # classification and binding: they decide a kind or an identity
    "bars",
    "lists",
    "normalizers",
    "identifiers",
    "projection",
)


def _role_authority(
    policy: dict, role: str, policy_digest: str
) -> tuple[str, str | None]:
    """The digest a selected profile field records, and the role behind it.

    A profile role is not an identity kind. It attaches to several of them —
    `adviser` to a company and a person, `fund` to a company and a fund
    structure (`evidence.PROFILE_KINDS`) — so its rules live in one top-level
    `profile_fields` block rather than being written once per kind and left to
    drift apart.

    Its values therefore record the **role's** digest. Recording the enclosing
    kind's made an edit to a role's rules invisible: it moved no recorded
    digest anywhere, which is the mirror image of the churn `_kind_authority`
    exists to stop (company mastering, decided 2026-09-23).

    A body with no `kinds` block is an old registered body with no per-kind
    digest to record, and keeps recording the body's here too, so the two
    halves of one policy never disagree about which era they are in.
    """
    if not policy.get("kinds"):
        return policy_digest, None
    rules = (policy.get("profile_fields") or {}).get(role)
    if not rules:
        return policy_digest, None
    return digest({"role": role, "fields": rules}), role


def _kind_authority(
    policy: dict, kind: str, policy_digest: str
) -> tuple[str, str | None]:
    """The digest a selected field records, and the kind version behind it.

    Ticket 02 decision 3: a field records its *kind's* digest, so that a
    Person-only edit leaves every Company value's recorded digest unchanged.
    The whole-body digest stays on the batch. A body with no `kinds` block has
    no per-kind digest to record, and keeps recording the body's, with no kind
    version to carry.

    The version travels beside the digest because a digest alone tells a reader
    only that something differs, never which authored document it came from.

    The digest covers the sections that decide **which claim wins**, named in
    `AUTHORITY_SECTIONS`, not the whole block. Ticket 02's own build list puts
    classification, binding, bars and projection in that same block, and none
    of them change a field's winner; digesting the block whole would move every
    field's recorded digest on a classification edit, which is the churn the
    per-kind digest exists to stop, reappearing inside one kind.

    An absent or empty section is omitted rather than digested as empty: the
    two describe the same rules, the way an absent mapping version and 1 do. A
    populated section is meant to move the digest.
    """
    block = (policy.get("kinds") or {}).get(kind)
    if not block:
        return policy_digest, None
    unknown = set(block) - set(AUTHORITY_SECTIONS) - set(NON_AUTHORITY_SECTIONS)
    if unknown:
        raise Conflict(
            "A kind section must be declared authority-bearing or not: "
            + ", ".join(sorted(unknown))
        )
    covered = {
        "kind": kind,
        **{name: block[name] for name in AUTHORITY_SECTIONS if block.get(name)},
    }
    return digest(covered), block.get("version")


def _select_values(
    rules: dict,
    subjects: list[str],
    claims: dict,
    overrides: list[dict],
    *,
    as_of: str,
    policy_digest: str,
    kind_version: str | None = None,
) -> tuple[dict, list[dict]]:
    """Clean MDM's five-step order over one set of field rules."""
    candidates = defaultdict(list)
    for subject in subjects:
        record = claims.get(subject)
        if not record:
            continue
        for name, claim in record["fields"].items():
            candidates[name].append(claim)
    fields = {}
    reviews = []
    for name, rule in rules.items():
        eligible = []
        for c in candidates.get(name, []):
            if c["source_code"] not in rule["sources"]:
                continue
            if c["op"] == "clear" and c["source_code"] not in rule.get(
                "clear_sources", []
            ):
                reviews.append(
                    {
                        "reason": "unauthorized_clear",
                        "field": name,
                        "assertion_id": c["assertion_id"],
                    }
                )
                continue
            if c["effective_at"] is None and not rule.get(
                "allow_unknown_effective", False
            ):
                continue
            if (
                c["effective_at"] is not None
                and rule.get("max_age_days") is not None
                and instant(c["effective_at"]) + timedelta(days=rule["max_age_days"])
                < instant(as_of)
            ):
                continue
            eligible.append(c)
        active = [
            o
            for o in overrides
            if o.get("subject") in subjects
            and o["field"] == name
            and not o.get("profile_id")
        ]
        # Multiple concurrent overrides need explicit revocation, not accidental
        # last-writer-wins. Do not use ingest time to resolve steward intent.
        if len(active) > 1:
            raise Conflict("Conflicting active steward overrides")
        eligible.sort(
            key=lambda c: (
                rule["sources"].index(c["source_code"]),
                -instant(c["effective_at"]).timestamp()
                if c["effective_at"] is not None
                else float("inf"),
                c["source_code"],
                c["record_key"],
                c["assertion_id"],
            )
        )
        if active:
            chosen = {
                "op": "value",
                "value": active[0]["value"],
                "assertion_id": active[0]["decision_id"],
                "source_code": "steward",
                "reason": active[0]["reason"],
            }
            if any(c.get("value") != chosen["value"] for c in eligible):
                reviews.append(
                    {
                        "reason": "override_source_disagreement",
                        "field": name,
                        "override": active[0]["decision_id"],
                    }
                )
        elif eligible:
            chosen = eligible.pop(0)
        else:
            continue
        fields[name] = {
            "value": chosen.get("value"),
            "cleared": chosen["op"] == "clear",
            "winner": chosen,
            "policy_digest": policy_digest,
            **({"kind_version": kind_version} if kind_version else {}),
            "conflicts": [
                c
                for c in eligible
                if canonical(c.get("value")) != canonical(chosen.get("value"))
            ],
        }
    return fields, reviews
