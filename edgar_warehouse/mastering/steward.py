"""A steward splits a consolidation a matching rule made: both masters return, and the pair becomes a Match Exclusion.

`split` names the merge by its decision id, records who split it and why, and writes it as one transaction.
Without `confirm` it reports what it would do and writes nothing."""

from __future__ import annotations

import json

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
