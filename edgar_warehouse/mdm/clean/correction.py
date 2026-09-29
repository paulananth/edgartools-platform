"""Correcting a wrong link (company mastering ticket 13).

Operator, 2026-09-24: a wrong merge is a rule defect: fix the rule, give it
a new tested version, and re-run the merge on the current Stage rows. A
wrong SEC-to-GLEIF link is a bind, and a bind never moves, so the correction
is a revocation of that bind, in the journal (`identity.replay`), with the
Stage following in the same transaction (migration 041).

A revocation is the receipt: the bind it revokes (`target`), that bind's
subject, entity, rule and version, its evidence, the Stage row's bronze
object, the policy in force, and why. In the batch that carries it, the
active rules reconsider the released record: it binds again under an
approved version, to the same Company or another, or it waits. A rule never
proposes the exact pair a revocation named under the version it named.
"""

from __future__ import annotations

from .activation import activated
from .evidence import decision
from .store import rows


def released(conn, decisions: list[dict]) -> set[str]:
    """The records this batch unbinds: the subjects of its revocations whose
    target is a bind, in this batch or stored. A revoked override or
    quarantine names a subject too, but unbinds nothing."""
    targets = {d["target"] for d in decisions if d["operation"] == "revoke"}
    if not targets:
        return set()
    binds = {d["decision_id"] for d in decisions if d["operation"] == "bind"}
    binds.update(
        r["decision_id"]
        for r in rows(
            conn,
            """SELECT decision_id FROM mdm_v2.decision
            WHERE operation = 'bind' AND decision_id = ANY(:targets)""",
            targets=sorted(targets),
        )
    )
    return {
        d["subject"]
        for d in decisions
        if d["operation"] == "revoke" and d["target"] in binds and d.get("subject")
    }


def reconsidered(conn, decisions: list[dict]) -> list[dict]:
    """The released records' current Stage readings, for the rules to see."""
    subjects = released(conn, decisions)
    if not subjects:
        return []
    return [
        r["reading"]
        for r in rows(
            conn,
            "SELECT reading FROM mdm_v2.stage_record WHERE subject = ANY(:subjects) ORDER BY subject",
            subjects=sorted(subjects),
        )
    ]


def refused(conn, subjects: set[str], decisions: list[dict]) -> set[tuple]:
    """(subject, entity, rule, version) no rule may propose again: every
    revocation, stored or in this batch, of a bind a rule made."""
    found = [d for d in decisions if d["operation"] == "revoke"]
    if subjects:
        found += [
            r["body"]
            for r in rows(
                conn,
                """SELECT body FROM mdm_v2.decision
                WHERE operation = 'revoke' AND body->>'subject' = ANY(:subjects)""",
                subjects=sorted(subjects),
            )
        ]
    return {
        (d["subject"], d["entity_id"], d["rule_id"], d["rule_version"])
        for d in found
        if d.get("subject") and d.get("rule_id")
    }


def stale_bindings(conn, policy: dict, *, limit: int) -> list[dict]:
    """The standing binds a rule made whose version is no longer switched on,
    oldest first, at most `limit`: what a rerun reassesses."""
    rules = {
        (rule["rule_id"], rule["version"]): (kind, rule)
        for kind, block in (policy.get("kinds") or {}).items()
        for rule in block.get("rules") or []
    }
    stale = []
    for body in (
        r["body"]
        for r in rows(
            conn,
            """SELECT d.body FROM mdm_v2.decision d
            WHERE d.operation = 'bind' AND d.body ? 'rule_id'
              AND NOT EXISTS (SELECT 1 FROM mdm_v2.decision v
                              WHERE v.operation = 'revoke' AND v.body->>'target' = d.decision_id)
            ORDER BY d.body->>'at', d.decision_id""",
        )
    ):
        found = rules.get((body["rule_id"], body["rule_version"]))
        if found is None or not activated(policy, found[0], found[1], "bind"):
            stale.append(body)
            if len(stale) == limit:
                break
    return stale


def revocation(conn, bind: dict, *, policy_digest: str, actor: str, reason: str, at: str) -> dict:
    """The receipt that revokes one bind: what it revokes, what that bind was
    made on, and the policy in force now."""
    stage = rows(
        conn,
        "SELECT bronze FROM mdm_v2.stage_record WHERE subject = :subject",
        subject=bind["subject"],
    )
    return decision(
        "revoke",
        actor=actor,
        reason=reason,
        at=at,
        target=bind["decision_id"],
        subject=bind["subject"],
        entity_id=bind["entity_id"],
        rule_id=bind["rule_id"],
        rule_version=bind["rule_version"],
        evidence=list(bind.get("evidence") or []),
        bronze=stage[0]["bronze"] if stage else None,
        policy=policy_digest,
    )
