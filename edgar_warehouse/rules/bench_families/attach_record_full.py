"""Short words for binding a source record to a master.

A pasted policy may use the words below where a stored key goes: a rule's matching
tests, its verdicts, and what it does when no master holds the value or several do.
The full policy is the same text with each word replaced by its stored key. A stored
key from the list, typed bare, is refused, since its name does not say what it does.
`review` and `first` say what they do and stay as they are, as do `wait` and the other
record tests. "attach" here means a source record is bound to a master; it never means
grouped rows are joined. A word for combining two existing masters is refused: that
decision stays on `rules test`. A word that belongs to another family is refused and
names that family.
"""

import json
from collections.abc import Mapping

from edgar_warehouse.rules.source_engine import SourceRejected, plan_record_matches

PRIMITIVES = {
    "same identifier": "identifier_match@1",
    "how many that identifier allows": "identifier_cardinality@1",
}
VERDICTS = {"attach": "bind"}
NO_MATCH = {"create a master": "mint"}
SEVERAL = {"send to review": "review"}
# Stored keys that already say what they do.
PLAIN_NO_MATCH = ("wait",)
PLAIN_SEVERAL = ("review",)
PLAIN_CONFLICT = ("review", "first")

# Words for combining two existing masters. This family never offers them.
COMBINING = {
    "merge", "merge masters", "merge the masters", "merge two masters",
    "combine", "combine masters", "combine the masters", "combine two masters",
    "consolidate", "consolidate masters", "consolidate the masters", "same subject",
}
# Words that other families own, with the family that accepts each.
OTHER_FAMILIES = {
    "list the values": "Group and attach rows",
    "one flat list": "Group and attach rows",
    "first row": "Group and attach rows",
    "last row": "Group and attach rows",
    "exactly one row": "Group and attach rows",
    "how many rows": "Group and attach rows",
    "distinct values": "Group and attach rows",
    "most frequent": "Group and attach rows",
    "how many at this path": "Read the file",
}

words = [{"word": word, "stored": stored}
         for table in (VERDICTS, NO_MATCH, SEVERAL, PRIMITIVES) for word, stored in table.items()]


class _Refused(Exception):
    pass


def explain(rule):
    try:
        short = json.loads(rule)
    except (TypeError, ValueError):
        return {"refused": "The short rule is not JSON."}
    if (not isinstance(short, Mapping) or not isinstance(short.get("kinds"), Mapping)
            or not isinstance(short.get("automatic_rules"), list)):
        return {"refused": "The short rule is not a policy: it has no kinds block or no automatic_rules list."}
    used = []
    try:
        _scan(short)
        document = _policy(short, used)
        _check(document)
    except _Refused as error:
        return {"refused": f"{error} Words this file accepts: {', '.join(item['word'] for item in words)}."}
    except (SourceRejected, TypeError, ValueError) as error:
        return {"refused": str(error)}
    return {"lines": used, "document": document}


def _scan(node):
    """Refuse a word for combining masters, or one that belongs to another family, wherever it stands."""
    if isinstance(node, Mapping):
        for key, value in node.items():
            _refuse_foreign(key)
            _scan(value)
    elif isinstance(node, list):
        for item in node:
            _scan(item)
    else:
        _refuse_foreign(node)


def _refuse_foreign(value):
    if not isinstance(value, str):
        return
    text = value.strip().lower()
    if text in COMBINING:
        raise _Refused(f"'{value}' combines two existing masters. That decision stays on `rules test`; "
                       "this file has no word for it.")
    if text in OTHER_FAMILIES:
        raise _Refused(f"'{value}' is a word of {OTHER_FAMILIES[text]}, not of Attach a source record.")


def _policy(short, used):
    out = dict(short)
    out["automatic_rules"] = [
        {**item, "verdict": _strict(item["verdict"], VERDICTS, used)}
        if isinstance(item, Mapping) and "verdict" in item else item
        for item in short["automatic_rules"]]
    out["kinds"] = {name: _kind(block, used) for name, block in short["kinds"].items()}
    return out


def _kind(block, used):
    if not isinstance(block, Mapping) or not isinstance(block.get("rules"), list):
        return block
    return {**block, "rules": [_rule(rule, used) for rule in block["rules"]]}


def _rule(rule, used):
    if not isinstance(rule, Mapping):
        return rule
    out = dict(rule)
    if isinstance(rule.get("emits"), list):
        out["emits"] = [_strict(item, VERDICTS, used) for item in rule["emits"]]
    for key, table, plain in (("on_no_match", NO_MATCH, PLAIN_NO_MATCH), ("on_several", SEVERAL, PLAIN_SEVERAL),
                              ("on_conflict", SEVERAL, PLAIN_CONFLICT)):
        if key in rule:
            out[key] = _outcome(rule[key], table, plain, used)
    if isinstance(rule.get("when"), list):
        out["when"] = [{**test, "primitive": _primitive(test["primitive"], used)}
                       if isinstance(test, Mapping) and "primitive" in test else test
                       for test in rule["when"]]
    return out


def _strict(value, table, used):
    """A stored key that has a word is typed as the word; nothing else is accepted."""
    if not isinstance(value, str):
        return value
    if value in table:
        return _use(used, value, table[value])
    _refuse_bare(value, table)
    raise _Refused(f"'{value}' is not a word this file knows.")


def _outcome(value, table, plain, used):
    if not isinstance(value, str) or value in plain:
        return value
    return _strict(value, table, used)


def _primitive(value, used):
    """A record test with no word here keeps its stored key; the engine reads it."""
    if not isinstance(value, str):
        return value
    if value in PRIMITIVES:
        return _use(used, value, PRIMITIVES[value])
    _refuse_bare(value, PRIMITIVES)
    return value


def _use(used, word, stored):
    if not any(item["word"] == word for item in used):
        used.append({"word": word, "stored": stored})
    return stored


def _refuse_bare(value, table):
    if value in table.values():
        typed = " or ".join(f"'{word}'" for word, stored in table.items() if stored == value)
        raise _Refused(f"'{value}' is a stored key. Type {typed} instead.")


def _check(policy):
    """The engine reads the policy's rules; a shape it refuses is not shown as a full policy."""
    plan_record_matches({
        "policy": policy, "assertions": [], "decisions": [], "identities": [], "bound": [],
        "bound_entities": {}, "released": [], "normalizers": {}})
