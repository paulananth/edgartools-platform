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

from .store import Conflict


def _revoking(conn, decisions: list[dict], operation: str) -> set[str]:
    """The subjects of this batch's revocations whose target, in this batch
    or stored, is a decision of `operation`."""
    targets = {d["target"] for d in decisions if d["operation"] == "revoke"}
    if not targets:
        return set()
    found = {d["decision_id"] for d in decisions if d["operation"] == operation}
    stored = [
        body
        for body in conn.inputs(
            (("decision", target) for target in targets), required=False
        ).values()
        if body["operation"] == operation
    ]
    found.update(r["decision_id"] for r in stored)
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
    candidates = [
        body
        for body in conn.related_decisions(subjects)
        if body.get("subject") in subjects and body["operation"] == "quarantine"
    ]
    revoked = {
        body["target"]
        for body in conn.related_decisions({body["decision_id"] for body in candidates})
        if body["operation"] == "revoke"
    }
    held.update(
        (body["decision_id"], body["subject"])
        for body in candidates
        if body["decision_id"] not in revoked
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
    return list(conn.readings(subjects).values())


def refused(conn, subjects: set[str], decisions: list[dict]) -> set[tuple]:
    """(subject, rule, version) that never binds again: every revocation,
    stored or in this batch, of a bind a rule made. Not keyed by Company, so
    a later merge of that Company cannot bring the pair back."""
    found = [d for d in decisions if d["operation"] == "revoke"]
    if subjects:
        found += [
            body
            for body in conn.related_decisions(subjects)
            if body["operation"] == "revoke" and body.get("subject") in subjects
        ]
    return {
        (d["subject"], d["rule_id"], d["rule_version"])
        for d in found
        if d.get("subject") and d.get("rule_id")
    }
