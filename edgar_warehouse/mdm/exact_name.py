"""Join a record to the one master whose records carry its name id (ticket 01).

A rule of family `exact_name_binding` names a `source` and its `holder_sources`.
Both sides carry the same name id as a cross-reference (`name_id@1`: the name
folded the same way for every source). A source record that no master holds
joins the one master that records of the holder sources hold under that name id;
none holding it leaves the record waiting, several send it to review. It finds
and never creates or merges, so a name only ever attaches a record to a Company
some other source already made. Either side may arrive first.
"""

from __future__ import annotations

from collections import defaultdict

from . import correction
from .activation import activated
from .binding import in_review, nothing, survivors
from .evidence import decision
from .matching import EXACT_NAME_FAMILY, _bindings, _latest, _stored, candidate_value

PATH = ("cross_references", "name_id")
NAMESPACE = "name_id"


def active_rules(policy: dict) -> list[tuple[str, dict]]:
    return [
        (kind, rule)
        for kind, block in sorted((policy.get("kinds") or {}).items())
        for rule in block.get("rules") or []
        if rule.get("family") == EXACT_NAME_FAMILY and activated(policy, kind, rule, "bind")
    ]


def _review(result: dict, reason: str, record: dict) -> None:
    result["reviews"].append({"reason": reason, "namespace": NAMESPACE,
                              "subject": record["subject"], "assertion_id": record["assertion_id"]})


def propose(conn, policy: dict, *, assertions: list[dict], decisions: list[dict], as_of: str,
            released: set[str]) -> dict:
    """The bindings the active exact-name rules propose for this batch."""
    rules = active_rules(policy)
    result = nothing()
    if not rules or not assertions:
        return result
    batch = _latest(assertions)
    for _kind, rule in rules:
        source, holder_sources = rule["source"], set(rule["holder_sources"])
        here_candidates = [a for a in batch.values()
                           if a["source_code"] == source and a["kind"] == rule["applies_to_verdict"]]
        here_holders = [a for a in batch.values() if a["source_code"] in holder_sources]
        held_keys = {candidate_value(a, PATH) for a in here_holders} - {None}
        # A waiting record of the source is found again when a holder arrives.
        candidates = _latest(_stored(conn, source, PATH, sorted(held_keys)) + here_candidates)
        for subject in correction.quarantined(conn, set(candidates), decisions):
            del candidates[subject]
        keys = sorted({candidate_value(a, PATH) for a in candidates.values()} - {None})
        holders = _latest([r for h in sorted(holder_sources) for r in _stored(conn, h, PATH, keys)] + here_holders)
        holders_by_key = defaultdict(list)
        for holder in holders.values():
            if key := candidate_value(holder, PATH):
                holders_by_key[key].append(holder)
        bindings = _bindings(conn, set(candidates) | set(holders), decisions + result["decisions"], released)
        refused = correction.refused(conn, set(candidates), decisions)
        found = {}
        for candidate in candidates.values():
            if bindings.get(candidate["subject"]):
                continue  # held already, by an identifier rule or an earlier batch
            entities = {e for h in holders_by_key.get(candidate_value(candidate, PATH), [])
                        for e in bindings.get(h["subject"], ())}
            if entities:
                found[candidate["subject"]] = (candidate, entities)
        merged = survivors(conn, {e for _, entities in found.values() for e in entities})
        suspended = in_review(conn, set(merged.values()) | {e for _, es in found.values() for e in es})
        for candidate, entities in found.values():
            entities = {merged.get(e, e) for e in entities}
            if len(entities) > 1:
                _review(result, "ambiguous_name_match", candidate)
                continue
            (entity,) = entities
            if entity in suspended:
                _review(result, "suspended_identifier", candidate)
                continue
            if (candidate["subject"], rule["rule_id"], rule["version"]) in refused:
                continue
            result["decisions"].append(decision(
                "bind", actor=f"rule:{rule['rule_id']}@{rule['version']}",
                reason=f"exact_name {NAMESPACE} held by one master", at=as_of,
                subject=candidate["subject"], entity_id=entity, evidence=[candidate["assertion_id"]],
                rule_id=rule["rule_id"], rule_version=rule["version"]))
    return result
