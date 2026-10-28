"""Ticket 146: a native policy's inline relationship types become today's pin."""

import pytest

from edgar_warehouse.mdm.clean.conversion import pinned
from edgar_warehouse.mdm.clean.relationships import types_of
from edgar_warehouse.mdm.clean.store import Conflict
from edgar_warehouse.rules import files

TODAY = types_of(files.policy())


def native(types):
    return {"version": 1, "relationships": {"version": "invented-types-v1", "types": types}}


def test_inline_types_become_the_pinned_code_set_and_a_dropped_type_is_named():
    body, dropped = pinned(native({**TODAY, "INVENTED_LINK": {"from": ["company"], "to": ["company"]}}))
    assert body["relationships"] == files.policy()["relationships"]
    assert types_of(body) == TODAY
    assert dropped == {"INVENTED_LINK"}


def test_a_type_defined_differently_is_refused():
    name = sorted(TODAY)[0]
    with pytest.raises(Conflict, match="differs from today's code set"):
        pinned(native({**TODAY, name: {**TODAY[name], "from": ["invented_kind"]}}))


def test_a_policy_with_no_inline_types_is_kept():
    body = {"version": 1}
    assert pinned(body) == (body, set())


def test_a_type_added_since_is_accepted():
    name = sorted(TODAY)[0]
    body, dropped = pinned(native({k: v for k, v in TODAY.items() if k != name}))
    assert types_of(body) == TODAY and dropped == set()
