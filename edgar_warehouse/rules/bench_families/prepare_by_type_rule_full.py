"""Short words for the contract whose entity type comes from a rule.

A pasted contract may use the words below where a stored key goes in its
`adapter`. The full contract is the same text with each word replaced by its
stored key. A stored key from the list, typed bare, is refused, since its name
does not say what it does. "entity type rule" is accepted only here: it is the
stored key `classification`, and the block it names holds the entity type's
block in the policy (`entity type`), the rule id and the rule version.
"""

import json
from collections.abc import Mapping

WORDS = {
    "entity type": "kind",
    "record key": "record_key",
    "identifier": "identifiers",
    "lookup only": "cross_references",
    "entity type rule": "classification",
}
# Inside the entity type rule, the entity type is the policy's block that holds the rule.
RULE_WORDS = {"entity type": "kind"}
FIXED_PAGE = "Prepare the MDM record"

words = [{"word": word, "stored": stored} for word, stored in WORDS.items()]


class _Refused(Exception):
    pass


def explain(rule):
    try:
        short = json.loads(rule)
    except (TypeError, ValueError):
        return {"refused": "The short rule is not JSON."}
    if not isinstance(short, Mapping) or not isinstance(short.get("adapter"), Mapping):
        return {"refused": "The short rule is not a contract: it has no adapter block."}
    used = []
    try:
        document = {**short, "adapter": _adapter(short["adapter"], used)}
        adapter = document["adapter"]
        if "classification" in adapter and ("kind" in adapter or "kind_field" in adapter):
            raise _Refused("A contract states an entity type or names an entity type rule, not both.")
    except _Refused as error:
        return {"refused": f"{error} Words this file accepts: {', '.join(item['word'] for item in words)}."}
    return {"lines": used, "document": document}


def _adapter(adapter, used):
    out = {}
    for key, value in adapter.items():
        stored = _name(key, WORDS, used)
        if stored == "classification" and isinstance(value, Mapping):
            value = _rule(value, used)
        out[stored] = value
    return out


def _rule(block, used):
    return {_name(key, RULE_WORDS, used): value for key, value in block.items()}


def _name(key, short, used):
    if key in short:
        if not any(item["word"] == key for item in used):
            used.append({"word": key, "stored": short[key]})
        return short[key]
    if key in WORDS.values():
        typed = " or ".join(f"'{word}'" for word, stored in WORDS.items() if stored == key)
        raise _Refused(f"'{key}' is a stored key. Type {typed} instead.")
    return key
