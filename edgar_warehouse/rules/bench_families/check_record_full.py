"""Short words for the quality block.

A pasted quality block may use the words below where a check's `test` or `on_fail`
goes. The full block is the same text with each word replaced by its stored key.
A stored key from the list, typed bare, is refused, since its name does not say what
it does. `version`, the ids, the paths and the arguments come from the paste.
"""

import json
from collections.abc import Mapping

from edgar_warehouse.mdm.quality import QualityError, check_quality

TESTS = {
    "is present": "present@1",
    "in the pinned code set": "in_reference@1",
}
OUTCOMES = {
    "hold the record out": "exception",
    "keep off matching": "withhold",
    "count the failure": "flag",
}

words = [{"word": word, "stored": stored} for table in (TESTS, OUTCOMES) for word, stored in table.items()]


class _Refused(Exception):
    pass


def explain(rule):
    try:
        short = json.loads(rule)
    except (TypeError, ValueError):
        return {"refused": "The short rule is not JSON."}
    if not isinstance(short, Mapping):
        return {"refused": "The short rule is not a quality block."}
    used = []
    try:
        document = dict(short)
        if isinstance(short.get("checks"), list):
            document["checks"] = [_check(item, used) for item in short["checks"]]
        check_quality(document)
    except _Refused as error:
        return {"refused": f"{error} Words this file accepts: {', '.join(item['word'] for item in words)}."}
    except (QualityError, TypeError, ValueError) as error:
        return {"refused": str(error)}
    return {"lines": used, "document": document}


def _check(item, used):
    if not isinstance(item, Mapping):
        return item
    out = dict(item)
    if "test" in item:
        out["test"] = _name(item["test"], TESTS, used)
    if "on_fail" in item:
        out["on_fail"] = _name(item["on_fail"], OUTCOMES, used)
    return out


def _name(value, short, used):
    if isinstance(value, str) and value in short:
        stored = short[value]
        if not any(line["word"] == value for line in used):
            used.append({"word": value, "stored": stored})
        return stored
    if isinstance(value, str) and value in short.values():
        typed = " or ".join(f"'{word}'" for word, stored in short.items() if stored == value)
        raise _Refused(f"'{value}' is a stored key. Type {typed} instead.")
    return value
