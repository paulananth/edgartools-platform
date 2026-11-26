"""Short words for the link rule.

A pasted link may use the words below where a stored key goes. The full link is
the same text with each word replaced by its stored key. `scope` keeps its
stored key. The words add nothing: a missing end stays what the engine makes of
it (a wait), and no end is made up.
"""

import json

from edgar_warehouse.rules.bench_families.link_masters import KEYS, link_of

STORED = {
    "link type": "type",
    "other master's key": "target_key",
    "link starts": "valid_from",
    "link ends": "valid_to",
}

words = [{"word": word, "stored": stored} for word, stored in STORED.items()]


def explain(rule):
    try:
        short = json.loads(rule)
    except (TypeError, ValueError):
        return {"refused": "The short link is not JSON."}
    if not isinstance(short, dict):
        return {"refused": "The short link is not one JSON object."}
    document, used = {}, []
    for key, value in short.items():
        stored = STORED.get(key, key)
        if stored not in KEYS:
            return {"refused": f"'{key}' is not a word or a key of a link. "
                               f"Words this file accepts: {', '.join(STORED)}, and the key scope."}
        if stored in document:
            return {"refused": f"The link names {stored} twice: a word and its stored key."}
        document[stored] = value
        if key in STORED:
            used.append({"word": key, "stored": stored})
    checked = link_of(json.dumps(document))
    if "refused" in checked:
        return checked
    return {"lines": used, "document": document}
