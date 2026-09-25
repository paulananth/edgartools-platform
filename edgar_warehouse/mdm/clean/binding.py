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

from .activation import NAMESPACES, activated, binding_namespaces
from .evidence import decision
from .primitives import normalizer
from .store import rows


def nothing() -> dict:
    """A fresh, empty set of proposals; never a shared one a caller could fill."""
    return {"identities": [], "decisions": [], "reviews": [], "mints": []}


def active_rules(policy: dict) -> list[tuple[str, dict]]:
    return [
        (kind, rule)
        for kind, block in sorted((policy.get("kinds") or {}).items())
        for rule in block.get("rules") or []
        if rule.get("family") == "binding" and activated(policy, kind, rule, "bind")
    ]


def holders(conn, policy: dict, wanted: dict[str, set[str]]) -> dict:
    """Which Companies hold each identifier value: one bounded query per namespace.

    A Company holds a value only through the **latest** version of a bound
    record from that namespace's **issuing source** (the contract's
    `sources`): an LEI is held through a GLEIF record, a CIK through an SEC
    record. A record that merely carries both values establishes nothing
    (Q14: "an LEI does not establish a CIK crosswalk merely because both
    values exist"), and a value an old revision carried no longer counts.
    A merged-away Company resolves to its survivor, so a consolidation that
    fixed a duplicate does not leave its identifier looking ambiguous.

    Keyed by the contract's normalized value, so a stored and an incoming form
    of one identifier cannot miss each other.
    """
    found: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    for namespace, values in sorted(wanted.items()):
        if not values:
            continue
        # A literal from a fixed set, so the per-namespace index can be used.
        if namespace not in NAMESPACES:
            raise ValueError(f"Unsupported identifier namespace: {namespace}")
        path = f"body->'identifiers'->>'{namespace}'"
        found_rows = rows(
            conn,
            f"""WITH latest AS (
                SELECT DISTINCT ON (a.source_code, a.record_key)
                       a.body->>'subject' AS subject, {path.replace("body", "a.body")} AS value
                FROM mdm_v2.assertion a
                WHERE (a.source_code, a.record_key) IN (
                    SELECT source_code, record_key FROM mdm_v2.assertion
                    WHERE {path} = ANY(:values) AND source_code = ANY(:sources))
                ORDER BY a.source_code, a.record_key, a.revision DESC,
                         a.mapping_version DESC)
            SELECT l.value, d.body->>'entity_id' AS entity_id, i.kind
            FROM latest l
            JOIN mdm_v2.decision d
              ON d.operation='bind' AND d.body->>'subject'=l.subject
            JOIN mdm_v2.identity i ON i.entity_id=(d.body->>'entity_id')::uuid
            WHERE l.value = ANY(:values)""",
            values=sorted(values),
            sources=_issuers(policy, namespace),
        )
        merged = survivors(conn, {r["entity_id"] for r in found_rows})
        for row in found_rows:
            key = (namespace, _normal(policy, namespace, row["value"]))
            found[key][merged.get(row["entity_id"], row["entity_id"])] = row["kind"]
    return found


def survivors(conn, entity_ids: set[str]) -> dict[str, str]:
    """Each merged-away Company's survivor; shared with `matching.py`."""
    if not entity_ids:
        return {}
    return {
        r["object_id"]: r["canonical_id"]
        for r in rows(
            conn,
            """SELECT object_id, body->>'canonical_id' AS canonical_id
            FROM mdm_v2.projection WHERE object_type='entity' AND object_id=ANY(:ids)
            AND body->>'canonical_id' IS NOT NULL""",
            ids=sorted(entity_ids),
        )
    }


def _contract(policy: dict, namespace: str) -> tuple[dict, dict] | None:
    """The namespace's Identifier Contract and the kind block declaring it."""
    for block in (policy.get("kinds") or {}).values():
        contract = (block.get("identifiers") or {}).get(namespace)
        if contract:
            return contract, block
    return None


def _issuers(policy: dict, namespace: str) -> list[str]:
    declared = _contract(policy, namespace)
    return list(declared[0]["sources"]) if declared else []


def _normal(policy: dict, namespace: str, value: str) -> str:
    declared = _contract(policy, namespace)
    if declared is None:
        return value
    contract, block = declared
    return normalizer(contract["normalizer"], block)(value)


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
        return nothing()
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
    # A Company this batch's own caller binds counts as a holder too, but only
    # of the identifiers the bound record's own source issues (Q14, as the
    # stored lookup above: an SEC record carrying an LEI holds no LEI).
    caller = {
        d["subject"]: d["entity_id"] for d in decisions if d["operation"] == "bind"
    }
    kinds = {i["entity_id"]: i["kind"] for i in identities}
    issuers = {namespace: _issuers(policy, namespace) for namespace in NAMESPACES}
    for a in assertions:
        if a["subject"] in caller:
            for namespace, raw in (a.get("identifiers") or {}).items():
                if a["source_code"] not in issuers.get(namespace, ()):
                    continue
                entity = caller[a["subject"]]
                key = (namespace, _normal(policy, namespace, raw))
                found[key][entity] = kinds.get(entity, a["kind"])

    by_subject = defaultdict(list)
    for item in applicable:
        by_subject[item[0]].append(item)
    result = nothing()
    minted: dict[tuple[str, str], str] = {}

    def may_mint(entry):
        return any(i[1]["on_no_match"] == "mint" for i in entry[1])

    # Records that may create a Company go first, so a record in the same
    # batch that may only join finds the Company its issuer's record just
    # created: one Company per identifier within a batch (ticket 03,
    # decision 3), and still only through the issuer's own record (Q14).
    for subject, items in sorted(
        by_subject.items(), key=lambda entry: (not may_mint(entry), entry[0])
    ):
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
                    break
                matches[entity] = (rule, namespace)
            if problem:
                break
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
                found[key][minted[key]] = record["kind"]
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
