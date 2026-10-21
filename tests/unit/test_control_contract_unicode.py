"""Opaque equality preserves code points; durable UTF-8 content stays strict."""
import json

import pytest

from edgar_warehouse.control_contract import canonical, digest
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts


@pytest.mark.parametrize("value", [
    "\udfff",
    {"\ud800": "invented", "é": "😀", "a": "\udfff"},
    [True, 1, 1.0, -0.0, 10**90, {"b": "\ud800", "a": None}],
    {10: "\ud800", 2: "invented", -1: "\udfff"},
    ("invented", ["\ud800\udc00", "𐀀", "\\udfff", "\b\t\n"]),
])
def test_native_opaque_canonical_equality_matches_existing_json_codec(value):
    assert canonical(value) == json.dumps(value, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=False, allow_nan=False)


def test_lone_surrogates_literal_escape_and_astral_characters_stay_distinct():
    assert len({canonical(value) for value in ["\ud800\udc00", "𐀀", "\\ud800\\udc00"]}) == 3


def test_opaque_canonical_still_rejects_nonfinite_numbers_and_cycles():
    for value in [float("nan"), float("inf"), -float("inf")]:
        with pytest.raises(ValueError):
            canonical(["\ud800", value])
    cycle = ["\ud800"]
    cycle.append(cycle)
    with pytest.raises(ValueError, match="Circular reference"):
        canonical(cycle)


def test_opaque_equality_does_not_permit_invalid_utf8_hashes_or_publication(tmp_path):
    value = {"invented": "\udfff"}
    assert canonical(value)
    with pytest.raises(UnicodeEncodeError):
        digest(value)
    with pytest.raises(UnicodeEncodeError):
        Artifacts().put(tmp_path.as_uri(), value)
    assert list(tmp_path.iterdir()) == []
