"""A steward splits a consolidation a matching rule made (ticket 142).

The Merge Stage already restores both masters when it replays a `reverse` decision that names a
`merge`, and a reversed merge is a Match Exclusion: a later record reaching the pair goes to review as
`excluded_consolidation` and proposes nothing. What was missing was the command that writes the decision.
`split` names the merge by its decision id (the id the agent context shows on a merged master), records
who split it and why, and runs it as one batch through the Merge Stage. Without `confirm` it previews the
batch and writes nothing."""

from __future__ import annotations

from uuid import uuid4

from .evidence import decision, instant
from .store import Conflict


def reversal(merge: dict, *, actor: str, reason: str, at: str) -> dict:
    """The decision that splits `merge`: a `reverse` naming it, signed and reasoned."""
    if merge.get("operation") != "merge":
        raise Conflict(f"Decision {merge.get('decision_id')} is a {merge.get('operation')}, not a merge: "
                       "only a merge can be split")
    if not actor.strip() or not reason.strip():
        raise ValueError("A split says who made it (--by) and why (--reason)")
    if instant(at) <= instant(merge["at"]):
        raise Conflict("A split is later than the merge it splits")
    return decision("reverse", actor=actor.strip(), reason=reason.strip(), at=at, target=merge["decision_id"])


def split(store, *, merge_id: str, actor: str, reason: str, at: str, confirm: bool = False,
          run_id: str | None = None) -> dict:
    """Preview or write the split of one merge. The report names the merge, the two masters, the decision,
    and what the Merge Stage did (or would do)."""
    from .merge import MergeStage
    from .prepared_registry import require_installed
    from .record_reads import RecordReader

    with store.engine.connect() as conn:
        adapter = require_installed(conn)
        reader = RecordReader(adapter, connection=conn)
        found = reader.inputs([("decision", merge_id)], required=False)
        if ("decision", merge_id) not in found:
            raise Conflict(f"MDM holds no decision {merge_id}")
        merge = found["decision", merge_id]
        # A reversal is anchored by the merge it names (scope.anchors), not by the masters.
        undone = [d for d in reader.related_decisions([merge_id])
                  if d.get("operation") == "reverse" and d.get("target") == merge_id]
        if undone:
            raise Conflict(f"Merge {merge_id} was already split by decision {undone[0]['decision_id']}")
        generation = adapter.generation(connection=conn)
        policy = adapter.batch_metadata(generation, limit=1, path=("effects", "policy_digest"), connection=conn)
        if not generation or not policy:
            raise Conflict("MDM holds no batch yet: there is no policy to split under")
        policy_digest = policy[0]["scalar"]
    verdict = reversal(merge, actor=actor, reason=reason, at=at)
    command = {"batch_id": f"steward-split:{verdict['decision_id']}", "run_id": run_id or str(uuid4()),
               "policy_digest": policy_digest, "consumer": f"steward/{merge_id[:32]}", "expected_checkpoint": 0,
               "checkpoint": 1, "as_of": at, "decisions": [verdict]}
    report = {"merge": merge_id, "left": merge["left"], "right": merge["right"], "decision": verdict["decision_id"],
              "by": verdict["actor"], "reason": verdict["reason"], "at": verdict["at"], "written": bool(confirm),
              "effect": "Both masters return, with their listings and links; the pair becomes a Match Exclusion: "
                        "a later record reaching both goes to review."}
    stage = MergeStage(store)
    result = stage.apply(**command) if confirm else stage.apply(**command, preview=True)
    report["stage"] = {key: result[key] for key in sorted(result) if isinstance(result[key], (str, int, bool))}
    return report


def splits_of(reader, entity_id: str) -> list[dict]:
    """The splits a master came out of: each merge that consolidated it with another master and was later
    reversed, with who split it and why. Each is also a Match Exclusion of the pair."""
    found = []
    for merge in reader.related_decisions([entity_id]):
        if merge.get("operation") != "merge" or entity_id not in (merge.get("left"), merge.get("right")):
            continue
        for later in reader.related_decisions([merge["decision_id"]]):
            if later.get("operation") == "reverse" and later.get("target") == merge["decision_id"]:
                other = merge["right"] if merge["left"] == entity_id else merge["left"]
                found.append({"merge": merge["decision_id"], "split_from": other, "by": later["actor"],
                              "reason": later["reason"], "at": later["at"], "excluded": True})
    return sorted(found, key=lambda item: (item["at"], item["merge"]))
