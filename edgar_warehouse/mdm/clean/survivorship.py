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
            key=lambda a: (a["revision"], a["publication_key"], a["assertion_id"]),
        ):
            if a["revision"] in seen and seen[a["revision"]] != a["assertion_id"]:
                raise Conflict("Source native revision has contradictory publications")
            seen[a["revision"]] = a["assertion_id"]
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
    candidates = defaultdict(list)
    profiles = {}
    profile_claims = defaultdict(dict)
    reviews = []
    for subject in subjects:
        record = claims.get(subject)
        if not record:
            continue
        for name, claim in record["fields"].items():
            candidates[name].append(claim)
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
    fields = {}
    for name, rule in policy.get("fields", {}).get(kind, {}).items():
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
            "conflicts": [
                c
                for c in eligible
                if canonical(c.get("value")) != canonical(chosen.get("value"))
            ],
        }
    for p in profiles.values():
        p["evidence"] = sorted(set(p["evidence"]))
        role_policy = {
            "fields": {p["role"]: policy.get("profile_fields", {}).get(p["role"], {})}
        }
        role_overrides = [
            {k: v for k, v in o.items() if k != "profile_id"}
            for o in overrides
            if o.get("profile_id") == p["profile_id"]
        ]
        values, _, problems = select_fields(
            p["role"],
            subjects,
            profile_claims[p["profile_id"]],
            role_policy,
            role_overrides,
            as_of=as_of,
            policy_digest=policy_digest,
        )
        p["fields"] = values
        reviews.extend({**r, "profile_id": p["profile_id"]} for r in problems)
    return fields, sorted(profiles.values(), key=lambda p: p["profile_id"]), reviews
