"""Try: decide the entity type with one classification rule.

The rule box holds the classification rule as JSON. The inputs are the record
(a JSON object of field to value) and the doc (a JSON object of the lists and
normalizers the rule names). The answer is what `classification.classify`
returns: an entity type, or "held back" beside the stored verdict.
"""

import json

from edgar_warehouse.mdm.classification import classify
from edgar_warehouse.mdm.evidence import KINDS

title = "Decide the entity type"
inputs = [
    {"name": "record", "label": "The record, as JSON: each field and its value"},
    {"name": "doc", "label": "The lists and normalizers the rule names, as JSON (leave empty for none)"},
]


def run(inputs, rule):
    try:
        policy = json.loads(rule)
    except (TypeError, ValueError):
        return {"refused": "The rule is not JSON."}
    if not isinstance(policy, dict):
        return {"refused": "The rule is not one JSON object."}
    if not _steps_ok(policy.get("steps")):
        return {"refused": "The rule's steps are not a list of steps, each with a list of tests."}
    record = _object(inputs.get("record"), "record", required=True)
    if "refused" in record:
        return record
    doc = _object(inputs.get("doc"), "doc", required=False)
    if "refused" in doc:
        return doc
    try:
        verdict = classify(policy, record["value"], doc["value"])
    except (TypeError, ValueError) as error:
        return {"refused": str(error)}
    if verdict in KINDS:
        return {"entity type": verdict}
    return {"held back": verdict}


def _steps_ok(steps):
    if steps is None:
        return True
    if not isinstance(steps, list):
        return False
    for step in steps:
        if not isinstance(step, dict):
            return False
        tests = step.get("when")
        if tests is not None and not (isinstance(tests, list) and all(isinstance(test, dict) for test in tests)):
            return False
    return True


def _object(text, name, required):
    if text is None or (isinstance(text, str) and not text.strip()):
        if required:
            return {"refused": f"The {name} is not there."}
        return {"value": {}}
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return {"refused": f"The {name} is not JSON."}
    if not isinstance(value, dict):
        return {"refused": f"The {name} is not one JSON object."}
    return {"value": value}
