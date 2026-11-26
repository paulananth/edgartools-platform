"""Short words for the entity-type rule.

A pasted classification rule may use the words below where a stored key goes.
The full rule is the same text with each word replaced by its stored key. A
stored key from the list, typed bare, is refused, since its name does not say
what it does. Every other test (`evidence_present@1`, `values_overlap@1`,
`name_shape@1`), the `args` of each test and the kind names keep what you type.
"""

import json
from collections.abc import Mapping

from edgar_warehouse.mdm.classification import check_rule

TESTS = {
    "field is one of": "field_in_set@1",
    "these fields are empty": "fields_all_empty@1",
    "name tokens match": "token_match@2",
    "name tokens match with any ampersand": "token_match@1",
}
VERDICTS = {"held back": "deferred"}
STEP_KEYS = {"probable entity type": "probable_kind", "otherwise": "otherwise"}

words = [{"word": word, "stored": stored}
         for table in (TESTS, VERDICTS, STEP_KEYS) for word, stored in table.items()]


class _Refused(Exception):
    pass


def explain(rule):
    try:
        short = json.loads(rule)
    except (TypeError, ValueError):
        return {"refused": "The short rule is not JSON."}
    if not isinstance(short, Mapping) or not isinstance(short.get("steps"), list):
        return {"refused": "The short rule is not a classification rule: it has no list of steps."}
    used = []
    try:
        document = dict(short)
        if "emits" in short:
            document["emits"] = _emits(short["emits"], used)
        document["steps"] = [_step(step, used) for step in short["steps"]]
        check_rule(document)
    except _Refused as error:
        return {"refused": f"{error} Words this file accepts: {', '.join(item['word'] for item in words)}."}
    except (TypeError, ValueError) as error:
        return {"refused": str(error)}
    return {"lines": used, "document": document}


def _emits(emits, used):
    if not isinstance(emits, list):
        raise _Refused("The rule's emits is not a list.")
    return [_name(item, VERDICTS, used) for item in emits]


def _step(step, used):
    if not isinstance(step, Mapping):
        raise _Refused("A step is not an object.")
    out = {}
    for key, value in step.items():
        out[_name(key, STEP_KEYS, used)] = value
    if "verdict" in step:
        out["verdict"] = _name(step["verdict"], VERDICTS, used)
    if "when" in step:
        out["when"] = _when(step["when"], used)
    return out


def _when(tests, used):
    if not isinstance(tests, list) or not all(isinstance(test, Mapping) for test in tests):
        raise _Refused("A step's when is not a list of tests.")
    out = []
    for test in tests:
        item = dict(test)
        if "primitive" in test:
            item["primitive"] = _name(test["primitive"], TESTS, used)
        out.append(item)
    return out


def _name(value, short, used):
    if isinstance(value, str) and value in short:
        stored = short[value]
        if not any(item["word"] == value for item in used):
            used.append({"word": value, "stored": stored})
        return stored
    if isinstance(value, str) and value in short.values() and value not in short:
        typed = " or ".join(f"'{word}'" for word, stored in short.items() if stored == value)
        raise _Refused(f"'{value}' is a stored key. Type {typed} instead.")
    return value
