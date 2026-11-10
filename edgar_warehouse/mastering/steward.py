"""A steward splits a consolidation a matching rule made: both masters return, and the pair becomes a Match Exclusion.

`split` names the merge by its decision id, records who split it and why, and writes it as one transaction.
Without `confirm` it reports what it would do and writes nothing.

`resolve` closes a `conflicting_identifiers` review (step 4): the record reached golden records its identifiers
disagree on, so it joined none and waits. The steward says `merge` (they are one: the golden records it reached
become one, the older surviving, and the record joins it) or `exclude` (the record is not the same as any of them:
it gets a golden record of its own without the identifiers that reached the others, and each pair becomes a Match
Exclusion)."""

from __future__ import annotations

import json
import hashlib
from collections import Counter
from uuid import uuid4

from edgar_warehouse.mdm.evidence import decision, instant

from . import merge


def reversal(merge_decision: dict, *, actor: str, reason: str, at: str) -> dict:
    """The decision that splits a merge: a `reverse` naming it, signed and reasoned."""
    if not actor.strip() or not reason.strip():
        raise ValueError("A split says who made it (--by) and why (--reason)")
    if instant(at) <= instant(merge_decision["at"]):
        raise ValueError("A split is later than the merge it splits")
    return decision("reverse", actor=actor.strip(), reason=reason.strip(), at=at, target=merge_decision["decision_id"])


def split(store, settings_of, *, merge_id: str, actor: str, reason: str, at: str, confirm: bool = False) -> dict:
    """Preview or write the split of one merge. `settings_of(kind)` gives the merge settings of the masters' kind."""
    found = store.rows("select left_id,right_id,body from mastering_decision where decision_id=%s and operation='merge'",
                       [merge_id])
    store.rollback()
    if not found:
        raise ValueError(f"MDM holds no merge {merge_id}")
    keep, gone, body = found[0]
    merge.refuse_if_split(store, merge_id, keep, gone)
    store.rollback()
    verdict = reversal(json.loads(body), actor=actor, reason=reason, at=at)
    report = {"merge": merge_id, "left": keep, "right": gone, "decision": verdict["decision_id"], "by": verdict["actor"],
              "reason": verdict["reason"], "at": verdict["at"], "written": bool(confirm),
              "effect": "Both masters return, with their listings and links; the pair becomes a Match Exclusion: "
                        "a later record reaching both goes to review."}
    if confirm:
        kind = store.master_bodies([keep])[keep]["kind"]
        store.rollback()
        merge.split_merge(store, settings_of(kind), keep, gone, verdict)
    return report


RESULTS = ("merge", "exclude")
CONFLICT = "conflicting_identifiers"


def reached(store, settings, record: dict) -> dict:
    """The golden records of this kind that hold an identifier the record states, with what they hold of it."""
    wanted = {namespace: {str(v) for v in (values if isinstance(values, list) else [values]) if v}
              for namespace, values in (record.get("identifiers") or {}).items()}
    found = {}
    held = store.holders({n: v for n, v in wanted.items() if v})
    kinds = store.kinds({entity for _, _, entity in held})
    for namespace, value, entity in held:
        if kinds.get(entity) == settings.kind:
            found.setdefault(entity, {}).setdefault(namespace, set()).add(value)
    store.rollback()
    return found


def apart_from(record: dict, others: dict) -> dict:
    """The record as its own golden record holds it: without the identifier values the other golden records hold,
    which stay beside it as `<identifier>_held_by_another` evidence."""
    taken = {n: {v for held in others.values() for v in held.get(n, ())} for n in {n for held in others.values() for n in held}}
    own, apart = {}, {}
    for namespace, values in (record.get("identifiers") or {}).items():
        values = values if isinstance(values, list) else [values]
        kept = [v for v in values if v and v not in taken.get(namespace, ())]
        if kept:
            own[namespace] = kept
        if len(kept) < len([v for v in values if v]):
            apart[namespace] = values
    return {**record, "identifiers": own,
            "cross_references": {**(record.get("cross_references") or {}),
                                 **{f"{n}_held_by_another": v for n, v in apart.items()}}}


def _decision(operation: str, actor: str, reason: str, at: str, **values) -> dict:
    return decision(operation, actor=actor.strip(), reason=reason.strip(), at=at, **values)


def resolve(store, settings_of, *, subject: str, result: str, actor: str, reason: str, at: str,
            confirm: bool = False) -> dict:
    """Preview or write the resolution of one waiting record's `conflicting_identifiers` review."""
    if result not in RESULTS:
        raise ValueError(f"A resolution is one of {', '.join(RESULTS)}")
    if not actor.strip() or not reason.strip():
        raise ValueError("A resolution says who made it (--by) and why (--reason)")
    if not store.has_open_review(subject, CONFLICT):
        raise ValueError(f"MDM holds no open {CONFLICT} review for {subject}")
    record = store.waiting_record(subject)
    store.rollback()
    if record is None:
        raise ValueError(f"{subject} has a golden record already")
    settings = settings_of(record["kind"])
    others = reached(store, settings, record)
    if not others:
        raise ValueError(f"{subject} reaches no golden record: nothing to resolve")
    ordered = store.oldest(sorted(others)) or sorted(others)
    store.rollback()
    report = {"subject": subject, "result": result, "reached": ordered, "by": actor.strip(), "reason": reason.strip(),
              "written": bool(confirm),
              "effect": ("The golden records it reached become one, the older surviving, and the record joins it."
                         if result == "merge" else
                         "The record gets a golden record of its own, without the identifiers that reached the others; "
                         "each pair becomes a Match Exclusion.")}
    if not confirm:
        return report
    try:
        store.take_lock()
        file_no, counts = store.last_file() + 1, Counter()
        if result == "merge":
            keep = ordered[0]
            for gone in ordered[1:]:
                verdict = _decision("merge", actor, reason, at, left=keep, right=gone, subject=subject)
                merge.merge_masters(store, settings, verdict, keep, gone, file_no, True)
            store.bind_record(subject, keep)
            entity, touched = keep, [keep]
        else:
            entity = str(uuid4())
            changed = apart_from(record, others)
            store.bind_record(subject, entity, changed)
            for other in ordered:
                store.add_decision(_decision("exclude", actor, reason, at, left=entity, right=other), entity, other)
            touched = [entity]
        store.add_decision(_decision("bind", actor, reason, at, subject=subject, entity_id=entity), subject, entity)
        store.close_reviews(CONFLICT, [subject])
        merge._write_masters(store, settings, touched, file_no, counts)
        store.finish_file(hashlib.sha256(f"resolve:{subject}:{result}:{at}".encode()).hexdigest(), 1)
        store.commit()
    except BaseException:
        store.rollback()
        raise
    report["golden_record"] = entity
    return report
