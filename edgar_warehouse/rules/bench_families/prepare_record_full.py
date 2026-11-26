"""Short words for the contract that prepares the MDM record.

A pasted contract may use the words below where a stored key goes in its
`adapter`. The full contract is the same text with each word replaced by its
stored key. A stored key from the list, typed bare, is refused, since its name
does not say what it does. "entity type rule" is not a word here: this contract
fixes the entity type, and a rule-decided entity type has its own page.
"""

import json
from collections.abc import Mapping

WORDS = {
    "entity type": "kind",
    "record key": "record_key",
    "identifier": "identifiers",
    "lookup only": "cross_references",
}
# The page where a rule decides the entity type; its word and stored key are refused here.
OTHER_PAGE = "Prepare a record whose entity type comes from a rule"
RULE_WORD = "entity type rule"
RULE_STORED = "classification"

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
        if RULE_STORED in short:
            raise _Refused(_rule_refusal(RULE_STORED))
        document = {**short, "adapter": _adapter(short["adapter"], used)}
    except _Refused as error:
        return {"refused": f"{error} Words this file accepts: {', '.join(item['word'] for item in words)}."}
    return {"lines": used, "document": document}


def _adapter(adapter, used):
    out = {}
    for key, value in adapter.items():
        if key in (RULE_WORD, RULE_STORED):
            raise _Refused(_rule_refusal(key))
        if key in WORDS:
            stored = WORDS[key]
            if not any(item["word"] == key for item in used):
                used.append({"word": key, "stored": stored})
            key = stored
        elif key in WORDS.values():
            typed = " or ".join(f"'{word}'" for word, stored in WORDS.items() if stored == key)
            raise _Refused(f"'{key}' is a stored key. Type {typed} instead.")
        out[key] = value
    return out


def _rule_refusal(key):
    return (f"'{key}' is not accepted here: this contract fixes the entity type. "
            f"The page '{OTHER_PAGE}' accepts a rule-decided entity type.")
