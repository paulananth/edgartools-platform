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
from .store import Conflict, rows


def _revoking(conn, decisions: list[dict], operation: str) -> set[str]:
    """The subjects of this batch's revocations whose target, in this batch
    or stored, is a decision of `operation`."""
    targets = {d["target"] for d in decisions if d["operation"] == "revoke"}
    if not targets:
        return set()
    found = {d["decision_id"] for d in decisions if d["operation"] == operation}
    found.update(
        r["decision_id"]
        for r in rows(
            conn,
            """SELECT decision_id FROM mdm.decision
            WHERE operation = :operation AND decision_id = ANY(:targets)""",
            operation=operation,
            targets=sorted(targets),
        )
    )
    return {
        d["subject"]
        for d in decisions
        if d["operation"] == "revoke" and d["target"] in found and d.get("subject")
    }


def released(conn, decisions: list[dict]) -> set[str]:
    """The records this batch unbinds: the subjects of its revocations whose
    target is a bind. A revoked override or quarantine names a subject too,
    but unbinds nothing."""
    return _revoking(conn, decisions, "bind")


def lifted(conn, decisions: list[dict]) -> set[str]:
    """The records this batch lifts from quarantine."""
    return _revoking(conn, decisions, "quarantine")


def quarantined(conn, subjects: set[str], decisions: list[dict]) -> set[str]:
    """Which of `subjects` are left out of matching after this batch: held by
    a quarantine, stored or in this batch, that no revocation lifts."""
    if not subjects:
        return set()
    lifting = {d["target"] for d in decisions if d["operation"] == "revoke"}
    held = {
        d["decision_id"]: d["subject"]
        for d in decisions
        if d["operation"] == "quarantine" and d["subject"] in subjects
    }
    held.update(
        (r["decision_id"], r["subject"])
        for r in rows(
            conn,
            """SELECT q.decision_id, q.body->>'subject' AS subject FROM mdm.decision q
            WHERE q.body->>'subject' = ANY(:subjects) AND q.operation = 'quarantine'
              AND NOT EXISTS (SELECT 1 FROM mdm.decision v
                              WHERE v.operation = 'revoke' AND v.body->>'target' = q.decision_id)""",
            subjects=sorted(subjects),
        )
    )
    return {subject for key, subject in held.items() if key not in lifting}


def check_lifts(journal: dict[str, dict], decisions: list[dict], policy_digest: str) -> None:
    """Only an operator-approved rule change lifts a quarantine (operator,
    2026-09-24). A quarantine names the policy it was made under; a lift
    names the policy this batch runs, which the Merge Stage only runs once
    registered through the governed path, and which must differ."""
    for d in decisions:
        if d["operation"] == "quarantine" and d.get("policy") != policy_digest:
            raise Conflict("A quarantine names the policy it is made under")
        target = journal.get(d.get("target")) if d["operation"] == "revoke" else None
        if target and target["operation"] == "quarantine":
            if d.get("policy") != policy_digest or target.get("policy") == policy_digest:
                raise Conflict("Only an approved rule change lifts a quarantine")


def readings(conn, subjects: set[str]) -> list[dict]:
    """The current Stage readings of `subjects`, for the rules to reconsider."""
    if not subjects:
        return []
    return [
        r["reading"]
        for r in rows(
            conn,
            "SELECT reading FROM mdm.stage_record WHERE subject = ANY(:subjects) ORDER BY subject",
            subjects=sorted(subjects),
        )
    ]


def refused(conn, subjects: set[str], decisions: list[dict]) -> set[tuple]:
    """(subject, rule, version) that never binds again: every revocation,
    stored or in this batch, of a bind a rule made. Not keyed by Company, so
    a later merge of that Company cannot bring the pair back."""
    found = [d for d in decisions if d["operation"] == "revoke"]
    if subjects:
        found += [
            r["body"]
            for r in rows(
                conn,
                """SELECT body FROM mdm.decision
                WHERE operation = 'revoke' AND body->>'subject' = ANY(:subjects)""",
                subjects=sorted(subjects),
            )
        ]
    return {
        (d["subject"], d["rule_id"], d["rule_version"])
        for d in found
        if d.get("subject") and d.get("rule_id")
    }


def stale_bindings(conn, policy: dict, *, limit: int) -> list[dict]:
    """The standing binds a rule made whose version is no longer switched on,
    oldest first, at most `limit`: what a rerun reassesses. One bounded query."""
    active = sorted(
        f"{rule['rule_id']}@{rule['version']}"
        for kind, block in (policy.get("kinds") or {}).items()
        for rule in block.get("rules") or []
        if activated(policy, kind, rule, "bind")
    )
    return [
        r["body"]
        for r in rows(
            conn,
            """SELECT d.body FROM mdm.decision d
            WHERE d.operation = 'bind' AND d.body ? 'rule_id'
              AND NOT (d.body->>'rule_id') || '@' || (d.body->>'rule_version') = ANY(:active)
              AND NOT EXISTS (SELECT 1 FROM mdm.decision v
                              WHERE v.operation = 'revoke' AND v.body->>'target' = d.decision_id)
            ORDER BY d.body->>'at', d.decision_id
            LIMIT :limit""",
            active=active,
            limit=limit,
        )
    ]


def revocations(
    conn, binds: list[dict], *, policy_digest: str, actor: str, reason: str, at: str
) -> list[dict]:
    """The receipts that revoke `binds`: what each revokes, what that bind was
    made on, the Stage row's bronze object, and the policy in force now."""
    bronze = {
        r["subject"]: r["bronze"]
        for r in rows(
            conn,
            "SELECT subject, bronze FROM mdm.stage_record WHERE subject = ANY(:subjects)",
            subjects=sorted({b["subject"] for b in binds}),
        )
    }
    return [
        decision(
            "revoke",
            actor=actor,
            reason=reason,
            at=at,
            target=b["decision_id"],
            subject=b["subject"],
            entity_id=b["entity_id"],
            rule_id=b["rule_id"],
            rule_version=b["rule_version"],
            evidence=list(b.get("evidence") or []),
            bronze=bronze.get(b["subject"]),
            policy=policy_digest,
        )
        for b in binds
    ]


def correction_batch(
    conn,
    policy: dict,
    policy_digest: str,
    *,
    actor: str,
    reason: str,
    at: str,
    limit: int,
    quarantine: tuple[str, ...] = (),
    lift: tuple[str, ...] = (),
) -> list[dict]:
    """The decisions of one correction batch, under the policy it runs:

    - revoke every standing bind whose rule version is no longer switched on
      (at most `limit`); the active rules reconsider those records in the
      same batch;
    - `quarantine`: records no rule can decide. Each one's standing bind is
      revoked too, and the quarantine names the Company it was linked to;
    - `lift`: records whose quarantine an approved rule change now lifts.
    """
    stale = stale_bindings(conn, policy, limit=limit)
    if quarantine:
        stale += [
            r["body"]
            for r in rows(
                conn,
                """SELECT d.body FROM mdm.decision d
                WHERE d.body->>'subject' = ANY(:subjects) AND d.operation = 'bind'
                  AND d.body ? 'rule_id'
                  AND NOT EXISTS (SELECT 1 FROM mdm.decision v
                                  WHERE v.operation = 'revoke' AND v.body->>'target' = d.decision_id)""",
                subjects=sorted(quarantine),
            )
            if r["body"]["decision_id"] not in {b["decision_id"] for b in stale}
        ]
    revoked = revocations(conn, stale, policy_digest=policy_digest, actor=actor, reason=reason, at=at)
    linked = {r["subject"]: r for r in revoked}
    missing = sorted(set(quarantine) - set(linked))
    if missing:
        raise Conflict(f"No standing rule link to quarantine for {missing}")
    held = [
        decision(
            "quarantine",
            actor=actor,
            reason=reason,
            at=at,
            subject=subject,
            entity_id=linked[subject]["entity_id"],
            evidence=linked[subject]["evidence"],
            policy=policy_digest,
        )
        for subject in sorted(quarantine)
    ]
    lifts = []
    if lift:
        found = rows(
            conn,
            """SELECT q.decision_id, q.body->>'subject' AS subject FROM mdm.decision q
            WHERE q.body->>'subject' = ANY(:subjects) AND q.operation = 'quarantine'
              AND NOT EXISTS (SELECT 1 FROM mdm.decision v
                              WHERE v.operation = 'revoke' AND v.body->>'target' = q.decision_id)""",
            subjects=sorted(lift),
        )
        missing = sorted(set(lift) - {r["subject"] for r in found})
        if missing:
            raise Conflict(f"No quarantine to lift for {missing}")
        lifts = [
            decision("revoke", actor=actor, reason=reason, at=at, target=r["decision_id"],
                     subject=r["subject"], policy=policy_digest)
            for r in found
        ]
    return revoked + held + lifts

