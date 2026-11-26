"""Try: link two masters with one link rule.

The rule box holds the link one stating record makes, as JSON: `type`, `target_key`
(the key the other master's record is bound under), `valid_from`, `valid_to` and
`scope`. The inputs are the claims (the stating records, keyed by subject), the
state (`bindings` and `canonical`), the entities, the as-of time and the link
types. The answer is what `mdm.relationships.project` returns: the links and the
reviews. A link does not create a master, and a claim that cannot be linked yet
stays a review.
"""

import json
from types import SimpleNamespace

from edgar_warehouse.mdm import relationships

title = "Link two masters"
inputs = [
    {"name": "claims", "label": "Claims, as JSON: each stating record's subject key and its assertion id"},
    {"name": "state", "label": "State, as JSON: bindings (subject key to binding) and canonical (binding to master)"},
    {"name": "entities", "label": "Masters, as JSON: each master's kind and status"},
    {"name": "as_of", "label": "As-of time, with its time zone"},
    {"name": "types", "label": "Link types, as JSON: a type code and the kinds it joins"},
]

KEYS = ("type", "target_key", "valid_from", "valid_to", "scope")


def link_of(rule):
    """The link the rule box states, as the claim's relationship entry, or a refusal."""
    try:
        link = json.loads(rule)
    except (TypeError, ValueError):
        return {"refused": "The link is not JSON."}
    if not isinstance(link, dict):
        return {"refused": "The link is not one JSON object."}
    unknown = sorted(set(link) - set(KEYS))
    if unknown:
        return {"refused": f"The link has no key {', '.join(repr(key) for key in unknown)}. "
                           f"Keys it takes: {', '.join(KEYS)}."}
    for key, value in link.items():
        if value is not None and not isinstance(value, str):
            return {"refused": f"The link's {key} is not text."}
    entry = {key: value for key, value in link.items() if key != "target_key" and value is not None}
    if link.get("target_key") is not None:
        entry["target_subject"] = link["target_key"]
    return {"entry": entry}


def run(inputs, rule):
    link = link_of(rule)
    if "refused" in link:
        return link
    claims = _object(inputs.get("claims"), "claims", of=dict)
    state = _object(inputs.get("state"), "state")
    entities = _object(inputs.get("entities"), "entities", of=dict)
    types = _object(inputs.get("types"), "types", of=dict, empty_ok=True)
    for pasted in (claims, state, entities, types):
        if "refused" in pasted:
            return pasted
    claims, state, entities, types = (pasted["value"] for pasted in (claims, state, entities, types))
    as_of = inputs.get("as_of")
    if not isinstance(as_of, str) or not as_of.strip():
        return {"refused": "The as-of time is not there."}
    if any("relationships" in claim for claim in claims.values()):
        return {"refused": "A claim holds no relationships: the link comes from the rule box."}
    maps = _maps(state)
    if "refused" in maps:
        return maps
    claims = {subject: {**claim, "relationships": [link["entry"]]} for subject, claim in claims.items()}
    try:
        links, reviews = relationships.project(claims, SimpleNamespace(**maps), entities, as_of.strip(), types)
    except (ValueError, TypeError) as error:
        return {"refused": str(error)}
    return {"links": links, "reviews": reviews}


def _object(text, name, of=None, empty_ok=False):
    if empty_ok and (text is None or (isinstance(text, str) and not text.strip())):
        return {"value": {}}
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return {"refused": f"The {name} are not JSON."}
    if not isinstance(value, dict) or (of and not all(isinstance(item, of) for item in value.values())):
        return {"refused": f"The {name} are not a JSON object of objects." if of
                else f"The {name} are not one JSON object."}
    return {"value": value}


def _maps(state):
    maps = {}
    for name in ("bindings", "canonical"):
        pairs = state.get(name)
        if not isinstance(pairs, dict) or not all(isinstance(v, str) for v in pairs.values()):
            return {"refused": f"The state has no {name}: a JSON object of texts."}
        maps[name] = pairs
    return maps
