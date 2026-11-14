"""The Rust preparation boundary preserves values for every supported record type."""

import pytest

from edgar_warehouse.mdm.evidence import KINDS, assertion
from edgar_warehouse.mdm.store import digest
from edgar_warehouse.mdm.survivorship import current_claims, profile_key


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


def test_a_role_a_later_revision_restates_keeps_its_earliest_start():
    """Operator, 2026-11-14: "Yes" (a role restated by later records keeps its earliest known start). Each
    quarter's record states the adviser role from that quarter's filing (invented values)."""
    def quarter(revision, start, profiles=None):
        return assertion(
            source_code="example.records", record_key="one", publication_key=f"q{revision}", revision=revision,
            effective_at=start, kind="company", fields={},
            profiles=profiles if profiles is not None else [
                {"role": "adviser", "authority": "Invented", "registration": "1", "valid_from": start,
                 "fields": {"note": f"q{revision}"}}])
    first, later = quarter(1, "2025-12-01T00:00:00+00:00"), quarter(2, "2026-07-14T00:00:00+00:00")
    record = current_claims([later, first], "2026-11-14T00:00:00+00:00", set())[first["subject"]]
    [role] = record["profiles"]
    assert role["valid_from"] == "2025-12-01T00:00:00+00:00"
    # Its fields are the latest revision's, under the role as it now reads.
    assert record["profile_fields"][profile_key(role)]["note"]["value"] == "q2"
    # A role the latest revision no longer states is not brought back.
    dropped = quarter(3, "2026-10-01T00:00:00+00:00", profiles=[])
    assert current_claims([dropped, later, first], "2026-11-14T00:00:00+00:00", set())[first["subject"]]["profiles"] == []
