"""A record's detail lists (ticket 120; operator, 2026-10-20: "Detail rows set in config
(Recommended)"): a Dataset Contract's reading gives them in its `details` column and
`detail_keys` names the field that keys each list's rows. Invented values only."""

import pytest

from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
from edgar_warehouse.mdm.clean.evidence import assertion, validate_assertion
from edgar_warehouse.mdm.clean.store import register_dataset
from tests.mdm.test_clean_cross_reference import BASE, GOLDEN, PUBLICATION
from tests.support.reading import reading

LISTINGS = {"value": {"path": "listings"}}  # the list of objects, as the source gives it


def contract(kind="security", detail_keys=None, details=True):
    body = reading({"name": "name"})
    if details:
        body["read"]["tables"]["mapped"]["columns"]["details"] = {"object": {"fields": {"listings": LISTINGS}}}
    return {"schema_version": "1", "adapter": {
        "version": "fixture-v1", "kind": kind, "record_key": ["id"], "identifiers": {"cik": "cik"},
        "identifier_formats": {"cik": "sec_cik"}, "reading": body,
        "detail_keys": {"listings": "figi"} if detail_keys is None else detail_keys}}


def row(**listings):
    return {"id": "1", "cik": "320193", "name": "Example", "listings": list(listings.values())}


def test_a_record_without_details_keeps_its_assertion_id():
    assert assertion(**BASE, details={})["assertion_id"] == GOLDEN
    assert "details" not in assertion(**BASE)


def test_details_are_hashed_in_key_order_and_validate():
    body = assertion(**BASE, details={"listings": [{"key": "F2", "ticker": "B"}, {"key": "F1", "ticker": "A"}]})
    assert [r["key"] for r in body["details"]["listings"]] == ["F1", "F2"] and body["assertion_id"] != GOLDEN
    validate_assertion(body)
    with pytest.raises(ValueError):
        validate_assertion({**body, "details": {"listings": [{"key": "F1", "ticker": "Z"}]}})


def test_a_contract_gives_its_rows_keyed_and_leaves_out_empty_values():
    body = normalize(row(a={"figi": "F2", "exchange": "LN", "ticker": None}, b={"figi": "F1", "exchange": "US", "ticker": "A"}),
                     source_code="fixture.primary", publication=PUBLICATION, contract=contract())
    assert body["details"] == {"listings": [{"key": "F1", "exchange": "US", "ticker": "A"},
                                            {"key": "F2", "exchange": "LN"}]}
    assert "details" not in normalize(row(), source_code="fixture.primary", publication=PUBLICATION, contract=contract())


@pytest.mark.parametrize("listings, reason", [
    ({"a": {"exchange": "US"}}, "missing_detail_key"),
    ({"a": {"figi": "F1"}, "b": {"figi": "F1"}}, "duplicate_detail_key"),
])
def test_a_row_without_its_key_or_a_key_held_twice_sets_the_record_aside(listings, reason):
    with pytest.raises(UnsupportedRecord) as refused:
        normalize(row(**listings), source_code="fixture.primary", publication=PUBLICATION, contract=contract())
    assert refused.value.reason == reason


@pytest.mark.parametrize("changes, words", [
    ({"kind": "company"}, "other than company"),
    ({"details": False}, "details column"),
    ({"detail_keys": {"Listings": "figi"}}, "lower-case words"),
    ({"detail_keys": {"listings": ""}}, "lower-case words"),
])
def test_registration_refuses_detail_lists_it_cannot_keep(changes, words):
    with pytest.raises(ValueError, match=words):
        register_dataset(None, "fixture.primary", contract(**changes))


def test_registration_takes_a_securitys_detail_lists():
    """Past the detail check, registration asks for the Rules authority, as for any contract."""
    with pytest.raises(ValueError, match="no Rules source authority|approved frozen"):
        register_dataset(None, "fixture.primary", contract())
