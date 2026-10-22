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

from functools import partial
from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .identifier_types import TYPES
from .names import legal_form_key, sec_legal_form_key
from .store import Conflict


class UnknownPrimitive(Conflict):
    """A policy named a `name@version` this build does not hold."""


@dataclass(frozen=True)
class Primitive:
    fn: Callable[..., Any]
    family: str


def prepare_matching_value(name: str, item: Any, doc: dict | None = None) -> str:
    """Transport a value and declared normalization rules to Rust."""
    from edgar_warehouse.rules.source_engine import apply_record_rules

    try:
        return apply_record_rules({
            "action": "prepare_matching_value", "name": name, "value": item,
            "doc": doc or {},
            "normalizers": {kind.normalizer_name: kind.upper for kind in TYPES.values()},
        })
    except ValueError as error:
        raise UnknownPrimitive(str(error)) from None


def _conformed(text: Any) -> str:
    from edgar_warehouse.rules.source_engine import compare_matching_values

    return compare_matching_values({"action": "prepare_conformed_name", "value": text})


NORMALIZERS: dict[str, Callable[[Any], str]] = {
    "normalize_text@edgar-conformed-v1": _conformed,
    "normalize_identifier@sec-cik-v1": partial(prepare_matching_value, "normalize_identifier@sec-cik-v1"),
    "normalize_identifier@crd-v1": partial(prepare_matching_value, "normalize_identifier@crd-v1"),
    "normalize_identifier@lei-v1": partial(prepare_matching_value, "normalize_identifier@lei-v1"),
    # Ticket 08: a name with its legal form kept, for the SEC-to-GLEIF
    # matching rule. SEC's variant drops the state tag of a conformed name.
    "normalize_text@legal-form-kept-v1": legal_form_key,
    "normalize_text@sec-legal-form-kept-v1": sec_legal_form_key,
}
# Ticket 81: each declared identifier type's normalizer, by its versioned name;
# a declared name never replaces a hand-written one.
for _kind in TYPES.values():
    if _kind.normalizer_name in NORMALIZERS:
        raise ValueError(f"{_kind.normalizer_name} is declared and also written in code")
    NORMALIZERS[_kind.normalizer_name] = _kind.normalize


def normalizer(name: str, doc: dict) -> Callable[[Any], str]:
    """Resolve a normalizer, through the document's own alias table if it has one."""
    resolved = (doc.get("normalizers") or {}).get(name, name)
    if resolved not in NORMALIZERS:
        raise UnknownPrimitive(f"Policy names an unknown normalizer: {name}")
    return NORMALIZERS[resolved]


def apply_record_test(name: str, args: dict, record: dict, doc: dict) -> bool:
    """Run each supported test once in the common Rust engine."""
    from edgar_warehouse.rules.source_engine import apply_record_rules

    try:
        return apply_record_rules({
            "action": "test_record", "name": name, "args": args,
            "record": record, "doc": doc,
            "normalizers": {kind.normalizer_name: kind.upper for kind in TYPES.values()},
        })
    except ValueError as error:
        raise Conflict(str(error)) from None


REGISTRY = MappingProxyType(
    {
        "identifier_match@1": Primitive(partial(apply_record_test, "identifier_match@1"), "binding"),
        "identifier_cardinality@1": Primitive(partial(apply_record_test, "identifier_cardinality@1"), "binding"),
        "kind_equal@1": Primitive(partial(apply_record_test, "kind_equal@1"), "binding"),
        # Ticket 08: the SEC-to-GLEIF matching rules. They compare two records
        # and a pinned census, so they too run where both are in hand
        # (`matching.propose`).
        **{
            name: Primitive(partial(apply_record_test, name), "name_binding")
            for name in (
                "name_census_match@1",
                "gleif_entity_eligible@1",
                "holds_no_other_lei@1",
                "jurisdiction_agrees@1",
                "jurisdictions_do_not_conflict@1",
                "postal_agrees@1",
                # Ticket 21: one pass of the cascade the census ran.
                "cascade_pass@1",
            )
        },
        "evidence_present@1": Primitive(partial(apply_record_test, "evidence_present@1"), "classification"),
        "field_in_set@1": Primitive(partial(apply_record_test, "field_in_set@1"), "classification"),
        "token_match@1": Primitive(partial(apply_record_test, "token_match@1"), "classification"),
        "token_match@2": Primitive(partial(apply_record_test, "token_match@2"), "classification"),
        "values_overlap@1": Primitive(partial(apply_record_test, "values_overlap@1"), "classification"),
        "name_shape@1": Primitive(partial(apply_record_test, "name_shape@1"), "classification"),
        "fields_all_empty@1": Primitive(partial(apply_record_test, "fields_all_empty@1"), "classification"),
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
