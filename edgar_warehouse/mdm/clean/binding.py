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
from datetime import timedelta
from typing import NamedTuple
from uuid import uuid4

from sqlalchemy import text

from .activation import NAMESPACES, activated, binding_namespaces
from .evidence import decision, instant
from .primitives import normalizer
from .store import rows


class _Match(NamedTuple):
    """One identifier of a record that points at a stored or new Company."""

    rule: dict
    namespace: str
    value: str  # normalized, for comparing
    raw: str  # as the store holds it, for the lookup


def publish_floor(conn, kind: str, as_of: str) -> str:
    """When a Company a rule creates now is published: never before another.

    The earliest-published Company survives a merge (`identity.replay`), and a
    merge joins Companies of one kind. So a rule's new Company is published at
    the batch's as_of, or one microsecond after the newest identity of its
    kind already stored, whichever is later (037 steps `valid_from` the same
    way). A batch delivered late then still creates its Company, and
    "earliest published" means earliest committed (ticket 04).
    """
    newest = conn.scalar(
        text("SELECT max(published_at) FROM mdm_v2.identity WHERE kind=:kind"),
        {"kind": kind},
    )
    if newest is None or instant(as_of) > newest:
        return as_of
    return (
        (newest + timedelta(microseconds=1))
        .astimezone(instant(as_of).tzinfo)
        .isoformat()
    )


def nothing() -> dict:
    """A fresh, empty set of proposals; never a shared one a caller could fill.

    `mints` and `joins` name the identifier each new Company or join to a
    stored Company rests on, so the Merge Stage can re-check it under its lock.
    """
    return {"identities": [], "decisions": [], "reviews": [], "mints": [], "joins": []}


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
        # The Stage row holds each record's latest reading and its binding.
        path = f"s.reading->'identifiers'->>'{namespace}'"
        found_rows = rows(
            conn,
            f"""SELECT {path} AS value, s.entity_id::text AS entity_id, i.kind
            FROM mdm_v2.stage_record s
            JOIN mdm_v2.identity i ON i.entity_id = s.entity_id
            WHERE {path} = ANY(:values) AND s.source_code = ANY(:sources)""",
            values=sorted(values),
            sources=_issuers(policy, namespace),
        )
        merged = survivors(conn, {r["entity_id"] for r in found_rows})
        for row in found_rows:
            key = (namespace, _normal(policy, namespace, row["value"]))
            found[key][merged.get(row["entity_id"], row["entity_id"])] = row["kind"]
    return found


def bound(conn, subjects) -> dict[str, str]:
    """The entity each stored record is bound to; shared with `matching.py`.

    The bind decision's own entity, not its survivor: a binding never moves.
    """
    if not subjects:
        return {}
    return {
        r["subject"]: r["entity_id"]
        for r in rows(
            conn,
            """SELECT subject, entity_id::text AS entity_id FROM mdm_v2.stage_record
            WHERE subject = ANY(:subjects) AND entity_id IS NOT NULL""",
            subjects=sorted(subjects),
        )
    }


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


def in_review(conn, entity_ids: set[str]) -> set[str]:
    """The Companies in review for an authoritative identifier or kind conflict.

    The Merge Stage gives a Company status `review` for those conflicts only.
    Q9: such a contradiction suspends the affected link, so its identifiers
    give no rule authority to join another record to it (ticket 04; a
    technical reading for the operator to confirm).
    """
    if not entity_ids:
        return set()
    return {
        r["object_id"]
        for r in rows(
            conn,
            """SELECT object_id FROM mdm_v2.projection
            WHERE object_type='entity' AND object_id=ANY(:ids)
              AND body->>'status'='review'""",
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
    taken = {d["subject"] for d in decisions if d["operation"] == "bind"}
    taken.update(bound(conn, subjects))
    # (subject, rule, namespace, normalized value) for every rule that applies.
    applicable = []
    wanted: dict[str, set[str]] = defaultdict(set)
    for subject in subjects:
        if subject in taken:
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
    # What the store says each value's holders are, before this batch's own
    # bindings join them: the only holdings the Merge Stage can re-check.
    stored = {key: set(held) for key, held in found.items()}
    floors: dict[str, str] = {}
    suspended = in_review(conn, {e for held in found.values() for e in held})
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
        matches: dict[str, list[_Match]] = defaultdict(list)
        problem = None
        for _, rule, namespace, value, raw in items:
            held = found.get((namespace, value), {})
            if len(held) > 1:
                # One value, several Companies: the forward claim is violated.
                problem = ("ambiguous_identifier", namespace)
                break
            for entity, kind in held.items():
                if kind != record["kind"]:
                    problem = ("incompatible_identifier_kind", namespace)
                    break
                if entity in suspended:
                    problem = ("suspended_identifier", namespace)
                    break
                matches[entity].append(_Match(rule, namespace, value, raw))
            if problem:
                break
        if problem is None and len(matches) > 1:
            problem = (
                "conflicting_identifiers",
                ",".join(
                    sorted(found_by[-1].namespace for found_by in matches.values())
                ),
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
            ((entity, found_by),) = matches.items()
            rule, namespace = found_by[-1].rule, found_by[-1].namespace
            # Every identifier that pointed here is re-checked under the lock.
            result["joins"].extend(
                {"entity_id": entity, "namespace": m.namespace, "raw": m.raw}
                for m in found_by
                if entity in stored.get((m.namespace, m.value), ())
            )
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
                        "published_at": floors.setdefault(
                            record["kind"], publish_floor(conn, record["kind"], as_of)
                        ),
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


def proposal_is_stale(conn, policy: dict, automatic: dict) -> bool:
    """Whether a rule's proposal no longer holds, re-checked under the lock.

    Run at apply, under the Merge Stage lock, since a concurrent run may have
    committed since the proposal was assessed. Stale, and re-assessed, when:
    - an identifier proposed for a new Company is now held;
    - an identifier a join rested on is no longer held by exactly that
      Company (another Company acquired it, or the Company was merged away);
    - an identity of a new Company's kind has since been published at or
      after the new Company's publish time (`publish_floor`).
    Changes to a target Company itself (a merge, or review) move the
    assessment's snapshot, which `assessment.check` already refuses. A join
    to a Company this batch's own caller binds is not in `joins`: it has no
    stored holding yet, and the caller's decision covers it.
    """
    mints = automatic.get("mints") or []
    joins = automatic.get("joins") or []
    wanted: dict[str, set[str]] = defaultdict(set)
    for m in [*mints, *joins]:
        wanted[m["namespace"]].add(m["raw"])
    found = holders(conn, policy, wanted)

    def held(m):
        return found.get(
            (m["namespace"], _normal(policy, m["namespace"], m["raw"])), {}
        )

    if any(held(m) for m in mints):
        return True
    if any(set(held(j)) != {j["entity_id"]} for j in joins):
        return True
    return any(
        conn.scalar(
            text(
                """SELECT EXISTS(SELECT 1 FROM mdm_v2.identity WHERE kind=:kind
                AND published_at >= CAST(:at AS timestamptz))"""
            ),
            {"kind": i["kind"], "at": i["published_at"]},
        )
        for i in automatic.get("identities") or []
    )
