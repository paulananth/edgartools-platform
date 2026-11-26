"""Short words for the read document.

A pasted read document may use the words below where a stored key goes. The full
document is the same text with each word replaced by its stored key. A stored key
from the list, typed bare, is refused, since its name does not say what it does.
`format` and the size limits come from the paste; the engine's ceilings apply.
"""

import json
from collections.abc import Mapping

from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected

CALLS = {
    "exact decimal": "value",
    "keep JSON": "value",
    "fixed": "const",
    "if": "choose",
    "first that counts": "coalesce",
    "join text": "join",
    "keep the last": "steps",
    "read inside": "project",
    "row number": "ordinal",
    "supplied fact": "context",
    "in the list": "member",
    "one value for the key": "member_value",
    "code table": "lookup",
    "shape": "test",
    "key exists": "test",
    "floating-point": "number",
}
# What a word adds to the call it names.
ADDS = {
    "exact decimal": {"decimals": "text", "big_numbers": "text"},
    "key exists": {"kind": "present"},
}
ITERATIONS = {
    "which list": "choose",
    "no rows": "empty",
    "zip arrays": "parallel",
    "headers and cells": "matrix",
    "child rows": "nest",
}
CHECKS = {
    "text is there": "required",
    "in the caller's list": "in_lookup",
    "in this fixed list": "in_set",
    "how many at this path": "count",
    "start is earlier": "before",
}
OUTCOMES = {"skip the row": "defer", "refuse the file": "reject"}

words = [{"word": word, "stored": stored}
         for table in (CALLS, ITERATIONS, CHECKS, OUTCOMES) for word, stored in table.items()]


class _Refused(Exception):
    pass


def explain(rule):
    try:
        short = json.loads(rule)
    except (TypeError, ValueError):
        return {"refused": "The short rule is not JSON."}
    if not isinstance(short, dict) or not isinstance(short.get("read"), Mapping):
        return {"refused": "The short rule is not a read document: it has no read block."}
    used = []
    try:
        document = {**short, "read": _read(short["read"], used)}
        SourceEngine(document)
    except _Refused as error:
        return {"refused": f"{error} Words this file accepts: {', '.join(item['word'] for item in words)}."}
    except (SourceRejected, TypeError, ValueError) as error:
        return {"refused": str(error)}
    return {"lines": used, "document": document}


def _read(read, used):
    out = dict(read)
    if isinstance(read.get("tables"), Mapping):
        out["tables"] = {name: _table(table, used) for name, table in read["tables"].items()}
    if isinstance(read.get("assertions"), list):
        out["assertions"] = [{**item, "test": _call(item["test"], used)}
                             if isinstance(item, Mapping) and "test" in item else item
                             for item in read["assertions"]]
    return out


def _table(table, used):
    if not isinstance(table, Mapping):
        return table
    out = dict(table)
    if "each" in table:
        out["each"] = _iteration(table["each"], used)
    if isinstance(table.get("columns"), Mapping):
        out["columns"] = {name: _call(expression, used) for name, expression in table["columns"].items()}
    if "select" in table:
        out["select"] = _call(table["select"], used)
    if isinstance(table.get("checks"), list):
        out["checks"] = [_check(item, used) for item in table["checks"]]
    return out


def _check(item, used):
    if not isinstance(item, Mapping):
        return item
    out = dict(item)
    if "check" in item:
        out["check"] = _name(item["check"], CHECKS, used)
    if "on_fail" in item:
        out["on_fail"] = _name(item["on_fail"], OUTCOMES, used)
    return out


def _name(value, short, used):
    if value in short:
        _use(used, value, short[value])
        return short[value]
    _refuse_bare(value, short)
    return value


def _iteration(node, used):
    if isinstance(node, list):
        return [_iteration(item, used) for item in node]
    if not isinstance(node, Mapping):
        return node
    out = {}
    for key, value in node.items():
        key = _name(key, ITERATIONS, used)
        out[key] = _arguments(value, used, iteration=True)
    return out


def _call(node, used):
    if isinstance(node, list):
        return [_call(item, used) for item in node]
    if not isinstance(node, Mapping):
        return node
    out = {}
    for key, value in node.items():
        stored = _name(key, CALLS, used)
        arguments = _arguments(value, used)
        if isinstance(arguments, dict) and key in ADDS:
            arguments = {**arguments, **ADDS[key]}
        out[stored] = arguments
    return out


def _arguments(value, used, iteration=False):
    if isinstance(value, list):
        return [_call(item, used) if isinstance(item, (Mapping, list)) else item for item in value]
    if not isinstance(value, Mapping):
        return value
    out = {}
    for key, item in value.items():
        if key == "fields" and isinstance(item, Mapping):
            out[key] = {name: _call(expression, used) for name, expression in item.items()}
        elif iteration and key in ("then", "else", "each"):
            out[key] = _iteration(item, used)
        elif key != "transforms" and isinstance(item, (Mapping, list)):
            out[key] = _call(item, used)
        else:
            out[key] = item
    return out


def _use(used, word, stored):
    if not any(item["word"] == word for item in used):
        used.append({"word": word, "stored": stored})


def _refuse_bare(value, short):
    if isinstance(value, str) and value in short.values():
        typed = " or ".join(f"'{word}'" for word, stored in short.items() if stored == value)
        raise _Refused(f"'{value}' is a stored key. Type {typed} instead.")
