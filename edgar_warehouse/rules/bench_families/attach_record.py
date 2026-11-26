"""Try: attach a source record to a master (source record binding).

The rule box holds the policy as JSON. The inputs are the records (assertions), the masters
that exist (identities, each with the identifier values it holds) and the records already
attached (the bound list). `plan_record_matches` reads which values to look up; the pasted
masters answer that lookup; `link_matching_records`, the call that follows the plan in the
same module, names what each record does: attach (stored `bind`), create a master (stored
`mint`) or send to review. No database is opened and `propose` is not called.

Combining two existing masters is not decided here: a rule whose `on_several` is `merge`
is refused, and that decision stays on `rules test`.
"""

import json

from edgar_warehouse.mdm.identifier_types import TYPES
from edgar_warehouse.rules.source_engine import SourceRejected, link_matching_records, plan_record_matches

title = "Attach a source record"
inputs = [
    {"name": "assertions", "label": "Records, as JSON: a list of records, each with subject, assertion_id, "
                                   "source_code, kind, revision and identifiers"},
    {"name": "identities", "label": "Masters that exist, as JSON: a list of entity_id, kind and holds "
                                    "(a namespace and the values the master holds); leave empty for none"},
    {"name": "bound", "label": "Records already attached, as JSON: a list of subjects (leave empty for none)"},
]

NORMALIZERS = {kind.normalizer_name: kind.upper for kind in TYPES.values()}
# The engine stamps each decision with a time; none is shown, so one fixed time serves.
TRY_TIME = "2000-01-01T00:00:00+00:00"
ATTACH, CREATE, REVIEW = "attach", "create a master", "send to review"


def run(inputs, rule):
    try:
        policy = json.loads(rule)
    except (TypeError, ValueError):
        return {"refused": "The policy is not JSON."}
    if not isinstance(policy, dict):
        return {"refused": "The policy is not one JSON object."}
    for key, kind in (("kinds", dict), ("automatic_rules", list)):
        if not isinstance(policy.get(key), kind):
            return {"refused": f"The policy has no {key} block."}
    if _merges(policy):
        return {"refused": "A rule that merges two masters is not tried here. "
                           "Combining existing masters is decided on `rules test`."}
    records = _paste(inputs, "assertions", list, "a list of records")
    masters = _paste(inputs, "identities", list, "a list of masters")
    bound = _paste(inputs, "bound", list, "a list of subjects")
    for pasted in (records, masters, bound):
        if isinstance(pasted, dict):
            return pasted
    if not all(isinstance(item, dict) and isinstance(item.get("subject"), str) for item in records):
        return {"refused": "Each record needs a subject."}
    held = _holds(masters)
    if "refused" in held:
        return held
    if not all(isinstance(item, str) for item in bound):
        return {"refused": "The bound list is not a list of subjects."}
    try:
        plan = plan_record_matches({
            "policy": policy, "assertions": records, "decisions": [], "identities": held["masters"],
            "bound": bound, "bound_entities": {}, "released": [], "normalizers": NORMALIZERS})
        linked = link_matching_records({
            "plan": plan, "found": _found(plan, held["values"]), "suspended": [], "newest": {},
            "new_ids": [f"new-master-{number}" for number in range(1, len(plan["applicable"]) + 1)],
            "refused": [], "as_of": TRY_TIME, "consolidations": [], "name_paired": []})
    except (SourceRejected, TypeError, ValueError) as error:
        return {"refused": str(error)}
    return _outcomes(records, bound, plan, linked)


def _paste(inputs, name, kind, what):
    text = inputs.get(name)
    if text is None or (isinstance(text, str) and not text.strip()):
        return kind()
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return {"refused": f"The {name} paste is not JSON."}
    if not isinstance(value, kind):
        return {"refused": f"The {name} paste is not {what}."}
    return value


def _merges(policy):
    for block in policy["kinds"].values():
        rules = block.get("rules") if isinstance(block, dict) else None
        for rule in rules if isinstance(rules, list) else []:
            if isinstance(rule, dict) and rule.get("on_several") == "merge":
                return True
    return False


def _holds(masters):
    """The masters as the plan reads them, and what each holds."""
    plain, values = [], []
    for master in masters:
        ok = (isinstance(master, dict) and isinstance(master.get("entity_id"), str)
              and isinstance(master.get("kind"), str) and isinstance(master.get("holds", {}), dict)
              and all(isinstance(held, list) and all(isinstance(value, str) for value in held)
                      for held in master.get("holds", {}).values()))
        if not ok:
            return {"refused": "Each master needs an entity_id, a kind, and holds: a namespace and a list of values."}
        plain.append({"entity_id": master["entity_id"], "kind": master["kind"]})
        values.extend((namespace, value, master["entity_id"], master["kind"])
                      for namespace, held in master.get("holds", {}).items() for value in held)
    return {"masters": plain, "values": values}


def _found(plan, values):
    """The lookup's answer: each pasted value, in the form the plan looks it up by."""
    forms = {(item["namespace"], item["raw"]): item["value"]
             for items in plan["applicable"].values() for item in items}
    forms.update({(item["namespace"], item["value"]): item["value"]
                  for items in plan["applicable"].values() for item in items})
    found = {}
    for namespace, value, entity, kind in values:
        found.setdefault((namespace, forms.get((namespace, value), value)), {})[entity] = kind
    return [{"namespace": namespace, "value": value, "records": records}
            for (namespace, value), records in found.items()]


def _outcomes(records, bound, plan, linked):
    created = {identity["entity_id"] for identity in linked["identities"]}
    attached = {decision["subject"]: decision["entity_id"] for decision in linked["decisions"]
                if decision["operation"] == "bind"}
    reviewed = {review["subject"]: review["reason"] for review in linked["reviews"]}
    outcomes, waiting, seen = [], [], set()
    for record in records:
        subject = record["subject"]
        if subject in seen:
            continue
        seen.add(subject)
        if subject in attached and attached[subject] in created:
            outcomes.append({"subject": subject, "outcome": CREATE, "stored": "mint", "master": attached[subject]})
        elif subject in attached:
            outcomes.append({"subject": subject, "outcome": ATTACH, "stored": "bind", "master": attached[subject]})
        elif subject in reviewed:
            outcomes.append({"subject": subject, "outcome": REVIEW, "stored": "review", "reason": reviewed[subject]})
        elif subject in bound:
            waiting.append({"subject": subject, "why": "already attached"})
        elif subject in plan["applicable"]:
            waiting.append({"subject": subject, "why": "waits for a master"})
        else:
            waiting.append({"subject": subject, "why": "no rule applies"})
    return {"looked_up": plan["wanted"], "outcomes": outcomes, "no_outcome": waiting}
