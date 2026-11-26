"""Try: fold dated sightings into the periods a relationship held.

The rule box holds the sightings as JSON: one object with a `sightings` list. The
fold has no other setting, so the page has no other input. Each sighting is the
capacity held, or dropped, on a date (`on`), with its `basis` (observed or stated),
a `held` flag (a flag that is not true is a drop), an optional `title`, and the
`assertion_id` and `subject` of the filing. The answer is what
`edgar_warehouse.mdm.relationships.fold_sightings` returns: the periods, and the
sightings left for a steward. A period ends only on a dropping sighting; a later
file that is missing never ends it.
"""

import json

from edgar_warehouse.mdm.relationships import fold_sightings

title = "Fold sightings into periods (the rule box holds the sightings)"
inputs = []

BASES = ("observed", "stated")


def run(inputs, rule):
    try:
        document = json.loads(rule)
    except (TypeError, ValueError):
        return {"refused": "The sightings are not JSON."}
    if not isinstance(document, dict):
        return {"refused": "The sightings are not one JSON object."}
    sightings = document.get("sightings")
    if not isinstance(sightings, list):
        return {"refused": "The sightings object has no `sightings` list."}
    for sighting in sightings:
        refusal = _refusal(sighting)
        if refusal:
            return {"refused": refusal}
    try:
        periods, contradictions = fold_sightings(sightings)
    except (TypeError, ValueError) as error:
        return {"refused": str(error)}
    return {"periods": periods, "contradictions": contradictions}


def _refusal(sighting):
    if not isinstance(sighting, dict):
        return "Each sighting is one JSON object."
    if sighting.get("basis") not in BASES:
        return f"A sighting's basis is one of: {', '.join(BASES)}."
    if not (sighting.get("held") is None or isinstance(sighting["held"], bool)):
        return "A sighting's held flag is true, false or null."
    return None
