"""Cross-reference identifiers: kept for lookup, never used to join (profiling ticket 03).

A Dataset Contract names them in `cross_references` (namespace → path), apart
from `identifiers`, which bind records to entities. The operator's ruling
(2026-09-26): ids such as a tax number or a source's own copy of another
register's id are kept so any document can be looked up by them, and they never
join records by themselves.
"""

import pytest

from edgar_warehouse.mdm.clean.adapters import normalize
from edgar_warehouse.mdm.clean.evidence import assertion, validate_assertion
from edgar_warehouse.mdm.clean.store import register_dataset

AT = "2026-01-02T00:00:00+00:00"
BASE = dict(source_code="fixture.primary", record_key="k1", publication_key="p1", revision=1, effective_at=AT,
            kind="company", fields={"name": "Acme"}, identifiers={"cik": "0000320193"})
# Computed on main before cross-references existed (2026-10-06): a record without
# them must keep this id, or every decision citing an assertion would be orphaned.
GOLDEN = "df9612c3f2e6d4831e64927e08945ec0b1d9ecdf7ba3b7bbf1ee5dbfb6f86b4d"
PUBLICATION = {"artifact_sha256": "0" * 64, "member": "m", "publication_key": "p1", "revision": 1}


def contract(**adapter):
    return {"schema_version": "1", "adapter": {
        "version": "fixture-v1", "kind": "company", "record_key": ["id"], "identifiers": {"cik": "cik"},
        "identifier_formats": {"cik": "sec_cik"}, "fields": {"name": "name"}, **adapter}}


def test_a_record_without_cross_references_keeps_its_assertion_id():
    assert assertion(**BASE)["assertion_id"] == GOLDEN
    assert assertion(**BASE, cross_references={})["assertion_id"] == GOLDEN
    assert "cross_references" not in assertion(**BASE)


def test_cross_references_are_hashed_and_validate():
    body = assertion(**BASE, cross_references={"tax_id": "12-3456789"})
    assert body["assertion_id"] != GOLDEN and body["cross_references"] == {"tax_id": "12-3456789"}
    validate_assertion(body)
    tampered = {**body, "cross_references": {"tax_id": "99-9999999"}}
    with pytest.raises(ValueError):
        validate_assertion(tampered)


def test_a_contract_maps_cross_references_apart_from_identifiers():
    body = normalize({"id": "1", "cik": "320193", "name": "Acme", "tax_id": " 12-3456789 ", "other_lei": None},
                     source_code="fixture.primary", publication=PUBLICATION,
                     contract=contract(cross_references={"tax_id": "tax_id", "other_lei": "other_lei"}))
    assert body["identifiers"] == {"cik": "0000320193"}
    assert body["cross_references"] == {"tax_id": "12-3456789"}  # an empty value is left out


def test_a_cross_reference_takes_a_named_format():
    body = normalize({"id": "1", "cik": "320193", "name": "Acme", "filer": "789019"},
                     source_code="fixture.primary", publication=PUBLICATION,
                     contract=contract(cross_references={"other_filer": "filer"},
                                       cross_reference_formats={"other_filer": "sec_cik"}))
    assert body["cross_references"] == {"other_filer": "0000789019"}


@pytest.mark.parametrize("adapter, words", [
    ({"cross_references": {"cik": "cik"}}, "also an identifier"),
    ({"cross_references": {"lei": "lei"}}, "binds records"),
    ({"cross_references": {"tax_id": "tax_id"}, "cross_reference_formats": {"tax_id": "nope"}}, "Unknown format"),
    ({"cross_references": {"Tax Id": "tax_id"}}, "lower-case"),
    ({"cross_reference_formats": {"tax_id": "sec_cik"}}, "no cross-reference"),
])
def test_registration_refuses_a_cross_reference_that_could_join_or_cannot_run(adapter, words):
    with pytest.raises(ValueError, match=words):
        register_dataset(None, "fixture.primary", contract(**adapter))
