"""Identifier types declared as rules (rebuild priorities ticket 81).

Operator, 2026-10-14: "why and why it takes so long, data profiling is not
enough", then "yes" to declaring identifier types instead of coding each one.
"""

import random
import string
import sys
from pathlib import Path

import pytest

from edgar_warehouse.mdm.clean import identifier_types
from edgar_warehouse.mdm.clean.activation import _check_contract
from edgar_warehouse.mdm.clean.adapters import FORMATS
from edgar_warehouse.mdm.clean.identifier_types import FAMILIES, DeclarationError, declared
from edgar_warehouse.mdm.clean.primitives import NORMALIZERS
from edgar_warehouse.mdm.clean.store import Conflict

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "data-profiling" / "scripts"))
from profiling import identifiers as profiled  # noqa: E402

# An invented identifier type: two letters and four digits, Luhn over the letter values.
WIDGET = {
    "identifier": "widget",
    "version": 1,
    "case": "upper",
    "parts": [{"length": 2, "characters": ["letters"]}, {"length": 4, "characters": ["digits"]}],
    "check_digit": "luhn over letter values",
    "refuse_one_repeated_character": True,
}


def test_a_declaration_gives_its_check_and_its_reasons():
    widget = declared(WIDGET, "widget")
    good = next(f"AB{n:03d}{d}" for n in range(1000) for d in range(10)
                if identifier_types.luhn_letter_values(f"AB{n:03d}{d}"))
    assert widget.refusal(f" {good.lower()} ") == (good, None)
    assert widget.refusal("A12345")[1] == "invalid_widget"
    assert widget.refusal(good[:-1] + str((int(good[-1]) + 1) % 10))[1] == "invalid_widget_checksum"
    assert widget.normalizer_name == "normalize_identifier@widget-v1"


def test_a_run_of_one_character_is_refused_only_when_declared():
    assert declared({**WIDGET, "parts": [{"length": 6, "characters": ["digits"]}],
                     "check_digit": None}, "widget").refusal("000000")[1] == "invalid_widget"
    assert declared({**WIDGET, "parts": [{"length": 6, "characters": ["digits"]}], "check_digit": None,
                     "refuse_one_repeated_character": False}, "widget").refusal("000000")[1] is None


@pytest.mark.parametrize("change, said", [
    ({"identifier": "gadget"}, "the file's name"),
    ({"version": "1"}, "whole number"),
    ({"parts": []}, "lists the identifier's parts"),
    ({"parts": [{"length": 0, "characters": ["digits"]}]}, "length"),
    ({"parts": [{"length": 2, "characters": ["[A-Z]"]}]}, "one character"),
    ({"case": "lower"}, "upper or as filed"),
    ({"check_digit": "mod 13"}, "unknown check-digit family"),
    ({"pattern": "[A-Z]{2}"}, "unknown keys"),
])
def test_a_declaration_this_build_cannot_run_is_refused(change, said):
    with pytest.raises(DeclarationError, match=said):
        declared({**WIDGET, **change}, "widget")


def test_the_declared_types_are_formats_and_normalizers():
    for name, kind in identifier_types.TYPES.items():
        assert name in FORMATS
        assert NORMALIZERS[kind.normalizer_name] == kind.normalize
    assert {"cusip", "isin"} <= set(identifier_types.TYPES)


def test_an_identifier_contract_may_name_a_declared_normalizer():
    contract = {
        "authority": "an issuing agency",
        "sources": ["a.source.v1"],
        "normalizer": "normalize_identifier@cusip-v1",
        "claim": {"forward": 1},
        "compatibility": {"field": "kind", "predicate": "kind_equal@1"},
        "verification": {"corpus_sha256": "0" * 64, "approved_by": "operator",
                         "approved_at": "2026-10-14", "reason": "test"},
        "tolerance": {"unit": "decisions", "warm_up_decisions": 0, "max_per_10k": 0},
    }
    _check_contract("cusip", contract)
    with pytest.raises(Conflict, match="unknown normalizer"):
        _check_contract("cusip", {**contract, "normalizer": "normalize_identifier@cusip-v9"})


@pytest.mark.parametrize("family", sorted(set(FAMILIES) & set(profiled.FAMILIES)))
def test_the_engine_and_profiling_agree_on_each_family(family):
    # Over values both read: upper-case letters and digits, ending in a digit.
    rng = random.Random(family)
    alphabet = string.digits + string.ascii_uppercase
    values = ["".join(rng.choice(alphabet) for _ in range(rng.randint(2, 15))) + rng.choice(string.digits)
              for _ in range(20_000)]
    test = profiled.FAMILIES[family][0]
    readable = {
        "mod 11-2": str.isdigit, "mod 11-10": str.isdigit, "luhn": str.isdigit, "damm": str.isdigit,
        "luhn over letter digits": lambda v: not v.isdigit(),
    }.get(family, lambda v: True)
    for value in values:
        if readable(value):
            assert FAMILIES[family](value) == test(value), (family, value)


def test_every_profiling_family_is_one_the_engine_runs():
    assert set(profiled.FAMILIES) <= set(FAMILIES)
