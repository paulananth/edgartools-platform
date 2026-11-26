"""Short words for the field-value policy.

A pasted policy may use the words below where a stored key goes. The full policy
is the same text with each word replaced by its stored key. A stored key from the
list, typed bare, is refused, since its name does not say whether it is the
order for every field or for one field. The words rank sources for a field value;
none of them says that two masters are the same subject.
"""

import json
from collections.abc import Mapping

from edgar_warehouse.mdm.survivorship import select_fields

# Words for the kind's own block: they set the default for every field of the kind.
KIND_WORDS = {
    "source order": "sources",
    "may blank the field": "clear_sources",
    "ignore older than": "max_age_days",
}
# Words inside `fields.<name>`: they set the rule for that one field.
FIELD_WORDS = {
    "this field's order": "sources",
    "may blank the field": "clear_sources",
    "ignore older than": "max_age_days",
}
STORED = ("sources", "clear_sources", "max_age_days")
LISTS = ("sources", "clear_sources")

words = [
    {"word": "source order", "stored": "defaults.sources"},
    {"word": "this field's order", "stored": "fields.<name>.sources"},
    {"word": "may blank the field", "stored": "clear_sources"},
    {"word": "ignore older than", "stored": "max_age_days"},
]

# The engine reads no claims here; the time only has to be an instant.
CHECKED_AT = "2000-01-01T00:00:00+00:00"


class _Refused(Exception):
    pass


def explain(rule):
    try:
        short = json.loads(rule)
    except (TypeError, ValueError):
        return {"refused": "The short rule is not JSON."}
    if not isinstance(short, dict) or not isinstance(short.get("kinds"), Mapping) or not short["kinds"]:
        return {"refused": "The short rule is not a policy: it has no kinds block."}
    used = []
    try:
        document = {**short, "kinds": {name: _kind(name, block, used) for name, block in short["kinds"].items()}}
        for name in document["kinds"]:
            select_fields(name, [], {}, document, [], as_of=CHECKED_AT, policy_digest="explain")
    except _Refused as error:
        return {"refused": f"{error} Words this file accepts: {', '.join(item['word'] for item in words)}."}
    except (TypeError, ValueError) as error:
        return {"refused": str(error)}
    return {"lines": used, "document": document}


def _kind(name, block, used):
    if not isinstance(block, Mapping):
        raise _Refused(f"The entity type '{name}' is not a block of rules.")
    defaults = {}
    out = {}
    for key, value in block.items():
        if key in KIND_WORDS:
            _put(defaults, KIND_WORDS[key], key, value, "defaults", used)
        elif key == "defaults" and isinstance(value, Mapping):
            _settings(defaults, value, "defaults", KIND_WORDS, used)
        elif key == "fields" and isinstance(value, Mapping):
            out[key] = {field: _field(field, rule, used) for field, rule in value.items()}
        else:
            _guard(key, "defaults")
            out[key] = value
    return {**({"defaults": defaults} if defaults else {}), **out}


def _field(name, rule, used):
    if not isinstance(rule, Mapping):
        return rule
    out = {}
    _settings(out, rule, f"fields.{name}", FIELD_WORDS, used)
    return out


def _settings(out, rule, where, table, used):
    for key, value in rule.items():
        if key in table:
            _put(out, table[key], key, value, where, used)
        else:
            _guard(key, where)
            out[key] = value


def _put(out, stored, word, value, where, used):
    if stored in out:
        raise _Refused(f"'{word}' is set twice in {where}.")
    if stored in LISTS:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise _Refused(f"'{word}' is a list of source names.")
    elif isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Refused(f"'{word}' is a number of days.")
    out[stored] = value
    line = {"word": word, "stored": f"{where}.{stored}"}
    if line not in used:
        used.append(line)


def _guard(key, where):
    """Refuse a stored key typed bare, and a word typed where it means something else."""
    if key in STORED:
        typed = " or ".join(f"'{word}'" for word in dict.fromkeys([*KIND_WORDS, *FIELD_WORDS])
                            if (KIND_WORDS.get(word) or FIELD_WORDS.get(word)) == key)
        raise _Refused(f"'{key}' is a stored key. It does not say whether it is for every field or one field. "
                       f"Type {typed} instead.")
    if where == "defaults" and key in FIELD_WORDS and key not in KIND_WORDS:
        raise _Refused(f"'{key}' is for one field. Type it under 'fields', or type 'source order' for every field.")
    if where != "defaults" and key in KIND_WORDS and key not in FIELD_WORDS:
        raise _Refused(f"'{key}' is for every field of the entity type. Type 'this field's order' for one field.")
