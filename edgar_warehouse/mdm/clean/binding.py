"""Identifier-only source binding, proposed inside the Merge Stage.

Company mastering ticket 04, Company Q14. An unbound source record whose
identifier resolves to exactly one compatible Company binds to it. When none
holds it, the rule's own `on_no_match` decides: `mint` creates a new Company
(ADR 0013: the Merge Stage allocates an internal ID independent of source
identifiers), `wait` leaves the record in the Stage. An identifier held by
several Companies, or two identifiers pointing at two different Companies,
defers: it never binds.

This module only **proposes**. The Merge Stage assesses every proposal before
it commits (Q13), and re-checks each new Company under its lock at apply, so
two concurrent runs cannot mint two Companies for one identifier.

A binding is looked up by the identifier the record carries. A record already
bound (by its source and key) is never re-proposed: a later version of the
same record keeps its Company without any lookup.
"""

from __future__ import annotations

from collections import defaultdict
from uuid import uuid4

from .activation import activated, binding_namespaces
from .evidence import decision
from .primitives import normalizer
from .store import rows

NOTHING = {"identities": [], "decisions": [], "reviews": [], "mints": []}


def active_rules(policy: dict) -> list[tuple[str, dict]]:
    return [
        (kind, rule)
        for kind, block in sorted((policy.get("kinds") or {}).items())
        for rule in block.get("rules") or []
        if rule.get("family") == "binding" and activated(policy, kind, rule, "bind")
    ]


def holders(conn, policy: dict, wanted: dict[str, set[str]]) -> dict:
    """Which Companies hold each identifier value, in one query per namespace.

    Keyed by the contract's normalized value, so a stored and an incoming form
    of one identifier cannot miss each other.
    """
    found: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    for namespace, values in sorted(wanted.items()):
        if not values:
            continue
        for row in rows(
            conn,
            """SELECT DISTINCT a.body->'identifiers'->>:ns AS value,
                   d.body->>'entity_id' AS entity_id, i.kind
            FROM mdm_v2.assertion a
            JOIN mdm_v2.decision d
              ON d.operation='bind' AND d.body->>'subject'=a.body->>'subject'
            JOIN mdm_v2.identity i ON i.entity_id::text=d.body->>'entity_id'
            WHERE a.body->'identifiers'->>:ns = ANY(:values)""",
            ns=namespace,
            values=sorted(values),
        ):
            key = (namespace, _normal(policy, namespace, row["value"]))
            found[key][row["entity_id"]] = row["kind"]
    return found


def _normal(policy: dict, namespace: str, value: str) -> str:
    for block in (policy.get("kinds") or {}).values():
        contract = (block.get("identifiers") or {}).get(namespace)
        if contract:
            return normalizer(contract["normalizer"], block)(value)
    return value


def propose(
    conn,
    policy: dict,
    *,
    assertions: list[dict],
    decisions: list[dict],
    identities: list[dict],
    as_of: str,
) -> dict:
    """The bindings and new Companies the active identifier rules propose."""
    rules = active_rules(policy)
    if not rules or not assertions:
        return NOTHING
    # The latest version per subject speaks for it within one batch.
    latest: dict[str, dict] = {}
    for a in sorted(
        assertions, key=lambda a: (a["revision"], a.get("mapping_version", 1))
    ):
        latest[a["subject"]] = a
    subjects = sorted(latest)
    bound = {d["subject"] for d in decisions if d["operation"] == "bind"}
    bound.update(
        r["subject"]
        for r in rows(
            conn,
            """SELECT DISTINCT body->>'subject' AS subject FROM mdm_v2.decision
            WHERE operation='bind' AND body->>'subject'=ANY(:subjects)""",
            subjects=subjects,
        )
    )
    # (subject, rule, namespace, normalized value) for every rule that applies.
    applicable = []
    wanted: dict[str, set[str]] = defaultdict(set)
    for subject in subjects:
        if subject in bound:
            continue
        record = latest[subject]
        for kind, rule in rules:
            if rule["applies_to_verdict"] != record["kind"] or rule.get(
                "source"
            ) not in (None, record["source_code"]):
                continue
            (namespace,) = binding_namespaces(rule)
            raw = (record.get("identifiers") or {}).get(namespace)
            if raw is None:
                continue
            wanted[namespace].add(raw)
            applicable.append(
                (subject, rule, namespace, _normal(policy, namespace, raw), raw)
            )
    found = holders(conn, policy, wanted)
    # A Company this batch's own caller binds counts as a holder too.
    caller = {
        d["subject"]: d["entity_id"] for d in decisions if d["operation"] == "bind"
    }
    kinds = {i["entity_id"]: i["kind"] for i in identities}
    for a in assertions:
        if a["subject"] in caller:
            for namespace, raw in (a.get("identifiers") or {}).items():
                entity = caller[a["subject"]]
                key = (namespace, _normal(policy, namespace, raw))
                found[key][entity] = kinds.get(entity, a["kind"])

    by_subject = defaultdict(list)
    for item in applicable:
        by_subject[item[0]].append(item)
    result = {"identities": [], "decisions": [], "reviews": [], "mints": []}
    minted: dict[tuple[str, str], str] = {}
    for subject, items in sorted(by_subject.items()):
        record = latest[subject]
        matches = {}
        problem = None
        for _, rule, namespace, value, _raw in items:
            held = found.get((namespace, value), {})
            if len(held) > 1:
                # One value, several Companies: the forward claim is violated.
                problem = ("ambiguous_identifier", namespace)
                break
            for entity, kind in held.items():
                if kind != record["kind"]:
                    problem = ("incompatible_identifier_kind", namespace)
                matches[entity] = (rule, namespace)
        if problem is None and len(matches) > 1:
            problem = (
                "conflicting_identifiers",
                ",".join(sorted(ns for _, ns in matches.values())),
            )
        if problem:
            result["reviews"].append(
                {
                    "reason": problem[0],
                    "namespace": problem[1],
                    "subject": subject,
                    "assertion_id": record["assertion_id"],
                }
            )
            continue
        if matches:
            ((entity, (rule, namespace)),) = matches.items()
        else:
            minting = [i for i in items if i[1]["on_no_match"] == "mint"]
            if not minting:
                continue  # `wait`: the record stays in the Stage, unbound
            _, rule, namespace, value, raw = minting[0]
            key = (namespace, value)
            if key not in minted:
                minted[key] = str(uuid4())
                result["identities"].append(
                    {
                        "entity_id": minted[key],
                        "kind": record["kind"],
                        "published_at": as_of,
                    }
                )
                # The raw form is what the store holds and what the lookup
                # queries; the normalized form is only for comparing.
                result["mints"].append(
                    {"entity_id": minted[key], "namespace": namespace, "raw": raw}
                )
            entity = minted[key]
        result["decisions"].append(
            decision(
                "bind",
                actor=f"rule:{rule['rule_id']}@{rule['version']}",
                reason=f"identifier_match {namespace}",
                at=as_of,
                subject=subject,
                entity_id=entity,
                evidence=[record["assertion_id"]],
                rule_id=rule["rule_id"],
                rule_version=rule["version"],
            )
        )
    return result


def mint_is_stale(conn, policy: dict, mints: list[dict]) -> bool:
    """Whether a Company proposed as new now already holds its identifier.

    Run at apply, under the Merge Stage lock: a concurrent run may have bound
    the identifier since this proposal was assessed.
    """
    wanted: dict[str, set[str]] = defaultdict(set)
    for m in mints:
        wanted[m["namespace"]].add(m["raw"])
    found = holders(conn, policy, wanted)
    return any(
        found.get((m["namespace"], _normal(policy, m["namespace"], m["raw"])))
        for m in mints
    )
