"""Try: choose the field value from the claims that disagree.

The rule box holds the policy as JSON. The inputs are the entity type (the
engine's `kind`), the subjects, the claims, the steward overrides, the as-of time
and the policy digest. The answer is what `select_fields` returns: the chosen
fields, the profiles and the reviews. Source priority only picks a value for a
field; it never decides that two masters are one subject.
"""

import json

from edgar_warehouse.mdm.survivorship import select_fields

title = "Choose the field value"
inputs = [
    {"name": "kind", "label": "Entity type"},
    {"name": "subjects", "label": "Subjects, as a JSON list of subject keys"},
    {"name": "claims", "label": "Claims, as JSON: a subject key and its fields"},
    {"name": "overrides", "label": "Steward overrides, as a JSON list (leave empty for none)"},
    {"name": "as_of", "label": "As-of time, with a time zone, for example 2026-09-22T00:00:00+00:00"},
    {"name": "policy_digest", "label": "Policy digest"},
]


def run(inputs, rule):
    try:
        policy = json.loads(rule)
    except (TypeError, ValueError):
        return {"refused": "The policy is not JSON."}
    if not isinstance(policy, dict):
        return {"refused": "The policy is not one JSON object."}
    kind = inputs.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        return {"refused": "The entity type is not there."}
    subjects = _json(inputs.get("subjects"), "subjects", list, "a JSON list of subject keys")
    claims = _json(inputs.get("claims"), "claims", dict, "a JSON object of subject key to claim")
    overrides = _json(inputs.get("overrides"), "overrides", list, "a JSON list", empty=[])
    for pasted in (subjects, claims, overrides):
        if isinstance(pasted, str):
            return {"refused": pasted}
    if not all(isinstance(subject, str) for subject in subjects):
        return {"refused": "The subjects are not a JSON list of texts."}
    as_of = inputs.get("as_of")
    if not isinstance(as_of, str) or not as_of.strip():
        return {"refused": "The as-of time is not there."}
    digest = inputs.get("policy_digest")
    if not isinstance(digest, str) or not digest.strip():
        return {"refused": "The policy digest is not there."}
    try:
        fields, profiles, reviews = select_fields(
            kind.strip(), subjects, claims, policy, overrides,
            as_of=as_of.strip(), policy_digest=digest.strip())
    except (TypeError, ValueError) as error:
        return {"refused": str(error)}
    return {"fields": fields, "profiles": profiles, "reviews": reviews}


def _json(text, name, shape, described, empty=None):
    """The pasted value, or the refusal text when it is not JSON of the shape."""
    if text is None or (isinstance(text, str) and not text.strip()):
        if empty is not None:
            return empty
        return f"The {name} are not there."
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return f"The {name} are not JSON."
    if not isinstance(value, shape):
        return f"The {name} are not {described}."
    return value
