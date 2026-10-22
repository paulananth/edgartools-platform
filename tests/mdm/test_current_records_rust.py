"""The Rust preparation boundary preserves values for every supported record type."""

import pytest

from edgar_warehouse.mdm.clean.evidence import KINDS, assertion
from edgar_warehouse.mdm.clean.store import digest
from edgar_warehouse.mdm.clean.survivorship import current_claims, profile_key


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_preparation_preserves_exact_values_for_every_record_type(kind):
    number = 10**100 + 17
    original = assertion(
        source_code="example.records", record_key="one", publication_key="first",
        revision=number, effective_at=None, kind=kind,
        fields={"amount": number, "details": {"value": [number, None, "", -0.0]}},
    )
    revised = assertion(
        source_code="example.records", record_key="one", publication_key="second",
        revision=number + 1, effective_at=None, kind=kind,
        fields={"amount": {"op": "unknown"}, "details": {"op": "retract"}},
    )
    current = current_claims([revised, original], "2026-10-19T00:00:00+00:00", set())
    record = current[original["subject"]]
    assert record["fields"]["amount"]["value"] == number
    assert record["fields"]["amount"]["assertion_id"] == original["assertion_id"]
    assert "details" not in record["fields"]
    assert record["assertion_id"] == revised["assertion_id"]


def test_profile_identity_preserves_existing_unicode_and_missing_value_hash():
    profile = {"role": "adviser", "authority": "Invented Autorité", "registration": "test"}
    expected = digest([profile.get(name) for name in
                       ("role", "authority", "registration", "jurisdiction", "valid_from")])
    assert profile_key(profile) == expected


def test_preparation_compares_offset_times_and_keeps_original_evidence_time():
    reading = assertion(
        source_code="example.records", record_key="one", publication_key="first",
        revision=1, effective_at="2026-10-18T20:00:00-04:00", kind="company",
        fields={"label": "Invented record"},
    )
    assert current_claims([reading], "2026-10-19T00:00:00+00:00", set())
    assert not current_claims([reading], "2026-10-18T23:59:59.999999+00:00", set())
    assert not current_claims([reading], "2026-10-19T00:00:00+00:00", {"example.records"})


def test_preparation_retains_the_existing_input_time_format_contract():
    reading = assertion(
        source_code="example.records", record_key="one", publication_key="first",
        revision=1, effective_at=None, kind="company", fields={"label": "Invented record"},
    )
    expected = current_claims([reading], "2026-10-19T00:00:00+00:00", set())
    assert current_claims([reading], "20261019T000000+0000", set()) == expected
    assert current_claims([reading], "2026-10-19 00:00+00:00", set()) == expected
