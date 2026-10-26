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

from sqlalchemy import text

from . import correction
from .activation import declared_namespaces
from .evidence import instant
from .primitives import normalizer
from .store import Conflict, containment_docs, identifier_values, rows
from .record_reads import RecordReader


def nothing() -> dict:
    """A fresh, empty set of proposals; never a shared one a caller could fill.

    `mints` and `joins` name the identifier each new Company or join to a
    stored Company rests on, so the Merge Stage can re-check it under its lock.
    """
    return {"identities": [], "decisions": [], "reviews": [], "mints": [], "joins": []}


def holders(conn, policy: dict, wanted: dict[str, set[str]], released: set[str] = frozenset()) -> dict:
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
    of one identifier cannot miss each other. A record whose bind the batch
    revokes (`released`, ticket 13) holds nothing for it.
    """
    found: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    declared = declared_namespaces(policy.get("kinds") or {})
    for namespace, values in sorted(wanted.items()):
        if not values:
            continue
        # Only a namespace an Identifier Contract declares.
        if namespace not in declared:
            raise ValueError(f"Unsupported identifier namespace: {namespace}")
        # The Stage row holds each record's latest reading and its binding.
        # Containment, one value at a time, so the GIN index on identifiers
        # (`stage_record_identifiers`) serves every namespace alike; `OFFSET 0`
        # keeps each value its own probe (ticket 77: 1.3 s a call before).
        found_rows = (conn.holders(namespace, values, _issuers(policy, namespace), released)
                      if isinstance(conn, RecordReader) else rows(
            conn,
            """SELECT DISTINCT s.reading->'identifiers'->:namespace AS value,
                      s.entity_id::text AS entity_id, i.kind
            FROM unnest(CAST(:wanted AS jsonb[])) AS w(doc) CROSS JOIN LATERAL (
                SELECT reading, entity_id, subject, source_code FROM mdm.stage_record
                WHERE (reading->'identifiers') @> w.doc OFFSET 0) s
            JOIN mdm.master_entity i ON i.entity_id = s.entity_id
            WHERE s.source_code = ANY(:sources) AND NOT s.subject = ANY(:released)""",
            namespace=namespace,
            wanted=[doc for v in sorted(values) for doc in containment_docs(namespace, v)],
            sources=_issuers(policy, namespace),
            released=sorted(released),
        ))
        merged = survivors(conn, {r["entity_id"] for r in found_rows})
        portable = isinstance(conn, RecordReader)
        normals = {_normal(policy, namespace, v) for v in values}
        for row in found_rows:
            # A Stage row returns its whole list; only the values asked count.
            for raw in [row["value"]] if portable else identifier_values(row["value"]):
                key = (namespace, _normal(policy, namespace, raw))
                if portable and key[1] not in values:
                    raise Conflict("Identifier reference differs from retained reading")
                if key[1] in normals:
                    found[key][merged.get(row["entity_id"], row["entity_id"])] = row["kind"]
    return found


def bound(conn, subjects) -> dict[str, str]:
    """The entity each stored record is bound to; shared with `matching.py`.

    The bind decision's own entity, not its survivor: a binding never moves.
    """
    if not subjects:
        return {}
    if isinstance(conn, RecordReader):
        return conn.bindings(subjects)
    return {
        r["subject"]: r["entity_id"]
        for r in rows(
            conn,
            """SELECT subject, entity_id::text AS entity_id FROM mdm.stage_record
            WHERE subject = ANY(:subjects) AND entity_id IS NOT NULL""",
            subjects=sorted(subjects),
        )
    }


def survivors(conn, entity_ids: set[str]) -> dict[str, str]:
    """Each merged-away Company's survivor; shared with `matching.py`."""
    if not entity_ids:
        return {}
    if isinstance(conn, RecordReader):
        return {identity:body["canonical_id"] for identity,body in conn.masters(entity_ids).items()
                if body.get("canonical_id")}
    return {
        r["object_id"]: r["canonical_id"]
        for r in rows(
            conn,
            """SELECT object_id, canonical_id FROM mdm.current_entity
            WHERE object_id=ANY(:ids) AND canonical_id IS NOT NULL""",
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
    if isinstance(conn, RecordReader):
        return {identity for identity,body in conn.masters(entity_ids).items() if body.get("status") == "review"}
    return {
        r["object_id"]
        for r in rows(
            conn,
            """SELECT object_id FROM mdm.current_entity
            WHERE object_id=ANY(:ids) AND status='review'""",
            ids=sorted(entity_ids),
        )
    }


def consolidations(conn, entities: set[str]) -> list[dict]:
    """The stored merges and Match Exclusions about `entities`, through every
    merge they rest on, with the reversals and revocations of each (ticket
    138 part A2a): what a rule's merge must name, and which pairs a steward
    keeps apart. One indexed read per round of new keys."""
    found: dict[str, dict] = {}
    keys, asked = set(entities), set()
    while want := keys - asked:
        asked |= want
        bodies = (conn.related_decisions(want) if isinstance(conn, RecordReader) else [r["body"] for r in rows(
            conn,
            """SELECT body FROM mdm.decision
            WHERE decision_id IN (SELECT id FROM mdm.decisions_naming(CAST(:keys AS text[])) id)""",
            keys=sorted(want),
        )])
        for body in bodies:
            operation = body["operation"]
            if operation in ("merge", "exclude"):
                keys |= {body["left"], body["right"]}
            elif operation not in ("reverse", "revoke"):
                continue
            found[body["decision_id"]] = body
            keys.add(body["decision_id"])
    return sorted(found.values(), key=lambda d: d["decision_id"])


def _merged(automatic: dict) -> set[str]:
    """The masters a rule's proposal merges."""
    return {e for d in automatic.get("decisions") or [] if d["operation"] == "merge" for e in (d["left"], d["right"])}


def _contracts(policy: dict, namespace: str) -> list[tuple[dict, dict]]:
    """Every kind's Identifier Contract for the namespace, with its kind block.

    One authority issues each value once, whichever kind reads it: SEC gives a
    CIK to a Company or a Person, never both (platform validation 05a).
    `check_policy` refuses contracts that disagree on authority or normalizer.
    """
    return [
        (contract, block)
        for block in (policy.get("kinds") or {}).values()
        if (contract := (block.get("identifiers") or {}).get(namespace))
    ]


def _issuers(policy: dict, namespace: str) -> list[str]:
    """The sources whose records hold the namespace, across every kind. A CIK
    one kind holds therefore sends another kind's record to review
    (`incompatible_identifier_kind`) instead of creating a second entity."""
    return sorted({s for contract, _ in _contracts(policy, namespace) for s in contract["sources"]})


def _normal(policy: dict, namespace: str, value: str) -> str:
    declared = _contracts(policy, namespace)
    if not declared:
        return value
    # Any kind's contract will do: `check_policy` holds them to one normalizer.
    contract, block = declared[0]
    return normalizer(contract["normalizer"], block)(value)


def propose(
    conn,
    policy: dict,
    *,
    assertions: list[dict],
    decisions: list[dict],
    identities: list[dict],
    as_of: str,
    released: set[str],
) -> dict:
    """The bindings and new Companies the active identifier rules propose.
    `released`: the records this batch unbinds (ticket 13)."""
    from edgar_warehouse.rules.source_engine import plan_record_matches, link_matching_records
    from .identifier_types import TYPES

    subjects = sorted({record["subject"] for record in assertions})
    try:
        held = bound(conn, subjects)
        merged = survivors(conn, set(held.values()))
        plan = plan_record_matches({
            "policy": policy, "assertions": assertions, "decisions": decisions,
            "identities": identities, "bound": list(held),
            # A re-delivered record's values are its master's (its survivor's).
            "bound_entities": {subject: merged.get(entity, entity) for subject, entity in held.items()},
            "released": sorted(released),
            "normalizers": {kind.normalizer_name: kind.upper for kind in TYPES.values()},
        })
        if not plan["applicable"]:
            return nothing()
        found = holders(conn, policy, {name: set(values) for name, values in plan["wanted"].items()}, released)
        suspended = in_review(conn, {entity for held in found.values() for entity in held})
        # A record reaching two or more masters may merge them (part A2a):
        # what those masters already rest on, read once for the batch.
        reaching: set[str] = set()
        for items in plan["applicable"].values():
            entities = {e for i in items for e in found.get((i["namespace"], i["value"]), {})}
            if len(entities) > 1:
                reaching |= entities
        merges = consolidations(conn, reaching) if reaching else []
        newest = conn.newest(plan["kinds"]) if isinstance(conn,RecordReader) else {}
        if not isinstance(conn,RecordReader):
            for kind in plan["kinds"]:
                at=conn.scalar(text("SELECT max(published_at) FROM mdm.master_entity WHERE kind=:kind"), {"kind": kind})
                newest[kind]=str(at) if at is not None else None
        proposed = link_matching_records({
            "plan": plan,
            "found": [{"namespace": name, "value": value, "records": held} for (name, value), held in found.items()],
            "suspended": sorted(suspended), "newest": newest,
            "new_ids": [str(uuid4()) for _ in plan["applicable"]],
            "refused": sorted(correction.refused(conn, set(subjects), decisions)), "as_of": as_of,
            "consolidations": merges,
        })
        if merged := _merged(proposed):
            # Re-checked under the lock by the same read: a merge or exclusion
            # stored since makes it stale.
            proposed["consolidations"] = [d["decision_id"] for d in consolidations(conn, merged)]
        return proposed
    except ValueError as error:
        raise Conflict(str(error)) from None


def proposal_is_stale(conn, policy: dict, automatic: dict, released: set[str] = frozenset()) -> bool:
    """Whether a rule's proposal no longer holds, re-checked under the lock.

    Run at apply, under the Merge Stage lock, since a concurrent run may have
    committed since the proposal was assessed. Stale, and re-assessed, when:
    - an identifier proposed for a master (a new one, or one a record joins
      or re-delivers with a value no master held) is now held by another;
    - an identifier a join rested on is no longer held by exactly that
      Company (another Company acquired it, or the Company was merged away);
    - an identity of a new Company's kind has since been published at or
      after the new Company's publish time (`publish_floor`).
    - a Company a join rests on has since gone into review.
    A join to a Company this batch's own caller binds is not in `joins`: it
    has no stored holding yet, and the caller's decision covers it.
    """
    mints = automatic.get("mints") or []
    joins = automatic.get("joins") or []
    wanted: dict[str, set[str]] = defaultdict(set)
    for m in [*mints, *joins]:
        wanted[m["namespace"]].add(m["raw"])
    found = holders(conn, policy, wanted, released)

    def held(m):
        return found.get(
            (m["namespace"], _normal(policy, m["namespace"], m["raw"])), {}
        )

    # A merge rests on the consolidations its masters had (part A2a): one
    # stored since (a merge it must name, a Match Exclusion) makes it stale.
    merged = _merged(automatic)
    if merged and [d["decision_id"] for d in consolidations(conn, merged)] != automatic.get("consolidations", []):
        return True
    # A value proposed for a master is stale once another master holds it;
    # held by that master already, it is consistent.
    if any(set(held(m)) - {m["entity_id"]} for m in mints):
        return True
    if any(set(held(j)) != {j["entity_id"]} for j in joins):
        return True
    if in_review(conn, {j["entity_id"] for j in joins}):
        return True
    # One read per kind: every new Company of a kind in a batch shares the
    # earliest publish time among them.
    earliest: dict[str, str] = {}
    for i in automatic.get("identities") or []:
        at = earliest.get(i["kind"])
        if at is None or instant(i["published_at"]) < instant(at):
            earliest[i["kind"]] = i["published_at"]
    if isinstance(conn,RecordReader):
        newest=conn.newest(earliest)
        return any(newest[kind] is not None and instant(newest[kind])>=instant(at)
                   for kind,at in earliest.items())
    return any(
        conn.scalar(
            text(
                """SELECT EXISTS(SELECT 1 FROM mdm.master_entity WHERE kind=:kind
                AND published_at >= CAST(:at AS timestamptz))"""
            ),
            {"kind": kind, "at": at},
        )
        for kind, at in sorted(earliest.items())
    )
