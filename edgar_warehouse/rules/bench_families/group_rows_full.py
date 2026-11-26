"""Short words for grouping rows and attaching the groups.

A pasted combination contract may use the words below where a stored key goes: a
group's `mode`, and the table key that holds its joins. A reduction contract may
use the three whole-set words as a group's `mode`. The full document is the same
text with each word replaced by its stored key. A stored key from the list,
typed bare, is refused, since its name does not say what it does. A word that
belongs to another family is refused and names that family. "attach" here means
grouped rows are joined to a row; it never means a source record is bound.
"""

import json
from collections.abc import Mapping

from edgar_warehouse.rules.source_engine import ReductionEngine
from edgar_warehouse.workers import source_combine

GROUP_MODES = {
    "list the values": "collect",
    "one flat list": "collect_flat",
    "first row": "first",
    "last row": "last",
    "exactly one row": "one",
}
REDUCE_MODES = {
    "how many rows": "count",
    "distinct values": "members",
    "most frequent": "most",
}
JOIN_KEYS = {"attach": "joins"}
# Words that other families own, with the family that accepts each.
OTHER_FAMILIES = {
    "how many at this path": "Read the file",
    "same identifier": "Attach a source record",
    "how many that identifier allows": "Attach a source record",
    "create a master": "Attach a source record",
    "send to review": "Attach a source record",
}

words = [{"word": word, "stored": stored}
         for table in (GROUP_MODES, REDUCE_MODES, JOIN_KEYS) for word, stored in table.items()]


class _Refused(Exception):
    pass


def explain(rule):
    try:
        short = json.loads(rule)
    except (TypeError, ValueError):
        return {"refused": "The short rule is not JSON."}
    if not isinstance(short, dict):
        return {"refused": "The short rule is not one JSON object."}
    used = []
    try:
        document = _document(short, used)
    except _Refused as error:
        return {"refused": f"{error} Words this file accepts: {', '.join(item['word'] for item in words)}."}
    except (TypeError, ValueError) as error:
        return {"refused": str(error)}
    return {"lines": used, "document": document}


def _document(short, used):
    if ("combine" in short) == ("reduce" in short):
        raise _Refused("The short rule is not a combination contract: it has no combine block, "
                       "or it has a reduce block as well.")
    if "combine" in short:
        document = {**short, "combine": _combine(short["combine"], used)}
        source_combine._contract(document, _readings(document["combine"]))
    else:
        document = {**short, "reduce": _reduce(short["reduce"], used)}
        _check_reduction(document)
    return document


def _combine(block, used):
    if not isinstance(block, Mapping):
        return block
    out = dict(block)
    if isinstance(block.get("groups"), Mapping):
        out["groups"] = {name: _group(spec, GROUP_MODES, REDUCE_MODES, "a reduction", used)
                         for name, spec in block["groups"].items()}
    if isinstance(block.get("tables"), Mapping):
        out["tables"] = {name: _table(spec, used) for name, spec in block["tables"].items()}
    return out


def _reduce(block, used):
    if not isinstance(block, Mapping):
        return block
    out = dict(block)
    if isinstance(block.get("groups"), Mapping):
        out["groups"] = {name: _group(spec, REDUCE_MODES, GROUP_MODES, "a combination", used)
                         for name, spec in block["groups"].items()}
    return out


def _group(spec, own, other, other_block, used):
    if not isinstance(spec, Mapping):
        return spec
    for key in spec:
        _refuse_other_family(key)
    if "mode" not in spec:
        return spec
    mode = spec["mode"]
    _refuse_other_family(mode)
    if mode in own:
        _use(used, mode, own[mode])
        return {**spec, "mode": own[mode]}
    if mode in other:
        raise _Refused(f"'{mode}' is for {other_block}, not for this one.")
    if isinstance(mode, str) and mode in (*own.values(), *other.values()):
        _refuse_bare(mode, {**own, **other})
    raise _Refused(f"'{mode}' is not a word this file knows.")


def _table(spec, used):
    if not isinstance(spec, Mapping):
        return spec
    out = {}
    for key, value in spec.items():
        _refuse_other_family(key)
        if key in JOIN_KEYS:
            _use(used, key, JOIN_KEYS[key])
            key = JOIN_KEYS[key]
        else:
            _refuse_bare(key, JOIN_KEYS)
        out[key] = value
    return out


def _readings(block):
    """The reading names the contract selects, as the contract check takes them."""
    names = set()
    if not isinstance(block, Mapping):
        return {}
    for part in ("groups", "tables"):
        specs = block.get(part)
        for spec in specs.values() if isinstance(specs, Mapping) else ():
            source = spec.get("source") if isinstance(spec, Mapping) else None
            names.update(name for name in (source if isinstance(source, list) else [source])
                         if isinstance(name, str))
    return dict.fromkeys(names, {})


def _check_reduction(document):
    if set(document) != {"execution", "reduce"} or document["execution"] != {"profile": "source.combine"}:
        raise ValueError("Reduction requires source.combine execution and reduce only")
    ReductionEngine(document["reduce"])


def _use(used, word, stored):
    if not any(item["word"] == word for item in used):
        used.append({"word": word, "stored": stored})


def _refuse_other_family(value):
    family = OTHER_FAMILIES.get(value) if isinstance(value, str) else None
    if family:
        raise _Refused(f"'{value}' is a word of {family}, not of Group and attach rows.")


def _refuse_bare(value, short):
    if isinstance(value, str) and value in short.values():
        typed = " or ".join(f"'{word}'" for word, stored in short.items() if stored == value)
        raise _Refused(f"'{value}' is a stored key. Type {typed} instead.")
