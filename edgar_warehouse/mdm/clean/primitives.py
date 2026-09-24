"""The fixed vocabulary of named, versioned tests a Mastering Policy may call.

Structure and parameters live in the policy document: steps, order, verdicts,
thresholds, token lists, field paths and source ranks. Code provides the tests.
A document names one as `name@version` and the registry **refuses a pair it
does not hold**, at registration and again per batch, so a pinned digest can
never reach a test that is not in this build (`policy-language.md` §5).

A corrected primitive is a **new version**; the old one is never edited in
place, because an old batch replays against the implementation it named.

What the vocabulary deliberately cannot express: document-supplied regular
expressions or SQL, clock or network reads, loops, and `OR` inside a step.
Each would make a pinned digest fail to reproduce its result.

Behaviour is pinned against the prototype that reproduced research 18's
measured classification to the row (`policy-language.md` §12).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .store import Conflict


class UnknownPrimitive(Conflict):
    """A policy named a `name@version` this build does not hold."""


@dataclass(frozen=True)
class Primitive:
    fn: Callable[..., Any]
    family: str


def value(record: dict, path: str) -> Any:
    """Read a declared field path. A path is data; it never executes."""
    current: Any = record
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def is_empty(item: Any) -> bool:
    return item is None or item == "" or item == 0 or item == [] or item == {}


def declared(doc: dict, name: Any, what: str) -> list:
    """A list a document names must be a list the same document declares."""
    if isinstance(name, list):
        return name
    lists = doc.get("lists") or {}
    if name not in lists:
        raise Conflict(f"Policy names an undeclared {what}: {name}")
    return lists[name]


def _conformed(text: Any) -> str:
    # EDGAR conformed names: `&` carries meaning, so it becomes a word rather
    # than being deleted with the rest of the punctuation.
    result = str("" if text is None else text).upper().replace("&", " AND ")
    result = re.sub(r"[.,;:/()'\"\-]", " ", result)
    return re.sub(r"\s+", " ", result).strip()


NORMALIZERS: dict[str, Callable[[Any], str]] = {
    "normalize_text@edgar-conformed-v1": _conformed,
    "normalize_identifier@sec-cik-v1": lambda s: re.sub(
        r"\D", "", str("" if s is None else s)
    ).lstrip("0"),
    "normalize_identifier@crd-v1": lambda s: re.sub(
        r"\D", "", str("" if s is None else s)
    ),
    "normalize_identifier@lei-v1": lambda s: re.sub(
        r"[^A-Z0-9]", "", str("" if s is None else s).upper()
    ),
}


def normalizer(name: str, doc: dict) -> Callable[[Any], str]:
    """Resolve a normalizer, through the document's own alias table if it has one."""
    resolved = (doc.get("normalizers") or {}).get(name, name)
    if resolved not in NORMALIZERS:
        raise UnknownPrimitive(f"Policy names an unknown normalizer: {name}")
    return NORMALIZERS[resolved]


def _tokens_found(raw: Any, listed: list, normalize: Callable[[Any], str]) -> list[str]:
    """Which declared entries appear in a name as whole tokens, not substrings.

    Whole-token matching is the point: INC must not match INCORPORATED, and
    a surname containing a legal form is not a legal form.
    """
    text = normalize(raw)
    found = set()
    for entry in listed:
        if entry == "AND":
            continue
        token = re.sub(r"\s+", " ", entry)
        if re.search(rf"(?<![A-Z0-9]){re.escape(token)}(?![A-Z0-9])", text):
            found.add(entry)
    if "&" in str("" if raw is None else raw) and " AND " in f" {text} ":
        found.add("&")
    return sorted(found)


def _evidence_present(args: dict, record: dict, doc: dict) -> bool:
    return not is_empty(value(record, args["document"]))


def _field_in_set(args: dict, record: dict, doc: dict) -> bool:
    return value(record, args["field"]) in args["values"]


def _token_match(args: dict, record: dict, doc: dict) -> bool:
    # Both counts absent would make every call true whatever the name holds —
    # a fail-open in a test that decides an entity's kind. All three calls in
    # the proven documents supply a count, so refusing the meaningless call
    # costs nothing and cannot silently pass.
    if args.get("min_count") is None and args.get("max_count") is None:
        raise Conflict("token_match requires min_count or max_count")
    listed = declared(doc, args["token_list"], "token list")
    found = _tokens_found(
        value(record, args["field"]), listed, normalizer(args["normalizer"], doc)
    )
    if args.get("exclude_list"):
        excluded = set(declared(doc, args["exclude_list"], "exclude list"))
        found = [t for t in found if t not in excluded]
    if args.get("min_count") is not None and len(found) < args["min_count"]:
        return False
    return not (args.get("max_count") is not None and len(found) > args["max_count"])


def _name_shape(args: dict, record: dict, doc: dict) -> bool:
    raw = str(value(record, args["field"]) or "").strip()
    if not raw:
        return False
    # Digit and character checks read the ORIGINAL string: normalizing first
    # deletes the very characters being checked (research 03 §6).
    if any(ch in raw for ch in (args.get("forbid_characters") or {}).get("value", [])):
        return False
    if (args.get("forbid_digits") or {}).get("value") and re.search(r"\d", raw):
        return False
    tokens = [
        t for t in re.split(r"[\s,]+", normalizer(args["normalizer"], doc)(raw)) if t
    ]
    if not args["min_tokens"] <= len(tokens) <= args["max_tokens"]:
        return False
    suffixes = set(declared(doc, args["suffix_list"], "suffix list"))
    if len([t for t in tokens if t not in suffixes]) < 2:
        return False
    return all(re.fullmatch(r"[A-Z]+", t) for t in tokens)


def _fields_all_empty(args: dict, record: dict, doc: dict) -> bool:
    return all(
        is_empty(value(record, path))
        for path in declared(doc, args["fields"], "field list")
    )


def _runs_in_the_merge_stage(args: dict, record: dict, doc: dict) -> Any:
    # A binding test compares a record with master state, which one record
    # cannot see; `binding.propose` evaluates it with the lookup in hand.
    raise Conflict("Binding and compatibility tests run in the Merge Stage")


REGISTRY = MappingProxyType(
    {
        "identifier_match@1": Primitive(_runs_in_the_merge_stage, "binding"),
        "identifier_cardinality@1": Primitive(_runs_in_the_merge_stage, "binding"),
        "kind_equal@1": Primitive(_runs_in_the_merge_stage, "binding"),
        "evidence_present@1": Primitive(_evidence_present, "classification"),
        "field_in_set@1": Primitive(_field_in_set, "classification"),
        "token_match@1": Primitive(_token_match, "classification"),
        "name_shape@1": Primitive(_name_shape, "classification"),
        "fields_all_empty@1": Primitive(_fields_all_empty, "classification"),
    }
)


def primitive_family(name: Any) -> str:
    """The family a named test belongs to. An unknown pair is refused by name."""
    if name not in REGISTRY:
        raise UnknownPrimitive(f"Policy names an unknown primitive: {name}")
    return REGISTRY[name].family


def call(name: str, args: dict, record: dict, doc: dict) -> Any:
    """Run one named test. An unknown pair is refused by name, fail closed."""
    if name not in REGISTRY:
        raise UnknownPrimitive(f"Policy names an unknown primitive: {name}")
    return REGISTRY[name].fn(args, record, doc)
