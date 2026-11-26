"""Try: check one record with one quality block.

The rule box holds the quality block as JSON. The inputs are the record's fields and
its matching copy, each a JSON object. The answer is what `quality.apply` returns for
the record, or, when an `exception` check fails, the reason the record is held out
beside the stored word `exception`.
"""

import json

from edgar_warehouse.mdm.adapters import UnsupportedRecord
from edgar_warehouse.mdm.quality import QualityError, apply, check_quality

title = "Check one record"
inputs = [
    {"name": "fields", "label": "The record's fields, as a JSON object"},
    {"name": "matching", "label": "The record's matching input, as a JSON object (leave empty for none)"},
]


def run(inputs, rule):
    try:
        block = json.loads(rule)
    except (TypeError, ValueError):
        return {"refused": "The quality block is not JSON."}
    if not isinstance(block, dict):
        return {"refused": "The quality block is not one JSON object."}
    fields = _object(inputs.get("fields"), "fields", required=True)
    matching = _object(inputs.get("matching"), "matching input", required=False)
    for pasted in (fields, matching):
        if "refused" in pasted:
            return pasted
    try:
        check_quality(block)
        return apply(block, fields["object"], matching["object"])
    except UnsupportedRecord as held:
        failed = held.detail["quality"]["checks"][held.reason.removeprefix("quality_")]
        return {"held out": held.reason, "on_fail": failed["failure_action"]}
    except (QualityError, TypeError, ValueError) as error:
        return {"refused": str(error)}


def _object(text, name, required):
    if text is None or (isinstance(text, str) and not text.strip()):
        if required:
            return {"refused": f"The {name} are not there."}
        return {"object": None}
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return {"refused": f"The {name} are not JSON."}
    if not isinstance(value, dict):
        return {"refused": f"The {name} are not one JSON object."}
    return {"object": value}
