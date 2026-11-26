"""Short words for the reduce plan.

A pasted rule may use the words below where a group's `mode` goes. The full rule
is the same text with each word replaced by its stored mode. A stored mode from
the list, typed bare, is refused: `count` does not say it counts rows, and
`members` and `most` do not say what they keep. The bounds and the group columns
come from the paste; the engine's ceilings apply.
"""

import json
from collections.abc import Mapping

from edgar_warehouse.rules.source_engine import ReductionEngine

MODES = {
    "how many rows": "count",
    "distinct values": "members",
    "most frequent": "most",
}
# Words from other families, refused by name.
OTHER_FAMILIES = {
    "how many at this path": "It counts at a path inside one record, as a read-file check.",
}

words = [{"word": word, "stored": stored} for word, stored in MODES.items()]


class _Refused(Exception):
    pass


def explain(rule):
    try:
        short = json.loads(rule)
    except (TypeError, ValueError):
        return {"refused": "The short rule is not JSON."}
    if not isinstance(short, Mapping) or not isinstance(short.get("reduce"), Mapping):
        return {"refused": "The short rule is not a reduce plan: it has no reduce block."}
    used = []
    try:
        document = {**short, "reduce": _reduce(short["reduce"], used)}
        ReductionEngine(document["reduce"])
    except _Refused as error:
        return {"refused": f"{error} Words this file accepts: {', '.join(item['word'] for item in words)}."}
    except (TypeError, ValueError) as error:
        return {"refused": str(error)}
    return {"lines": used, "document": document}


def _reduce(plan, used):
    out = dict(plan)
    if isinstance(plan.get("groups"), Mapping):
        out["groups"] = {name: _group(group, used) for name, group in plan["groups"].items()}
    return out


def _group(group, used):
    if not isinstance(group, Mapping) or "mode" not in group:
        return group
    return {**group, "mode": _mode(group["mode"], used)}


def _mode(value, used):
    if isinstance(value, str) and value in MODES:
        if not any(item["word"] == value for item in used):
            used.append({"word": value, "stored": MODES[value]})
        return MODES[value]
    if isinstance(value, str) and value in MODES.values():
        typed = " or ".join(f"'{word}'" for word, stored in MODES.items() if stored == value)
        raise _Refused(f"'{value}' is a stored key. Type {typed} instead.")
    if isinstance(value, str) and value in OTHER_FAMILIES:
        raise _Refused(f"'{value}' is not a summary of rows. {OTHER_FAMILIES[value]} "
                       "Type 'how many rows' to count the rows of a group.")
    raise _Refused(f"{json.dumps(value)} is not a word this file accepts.")
