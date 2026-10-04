"""The local cohort uses unchanged, approved adapters for two distinct kinds."""

from collections import Counter

from tests.support.fresh_mastering import cohort


def test_the_local_cohort_reads_as_two_companies_and_two_people():
    policy, contracts, records = cohort()
    assert Counter(r["kind"] for r in records) == {"company": 2, "person": 2}
    assert len({r["identifiers"]["cik"] for r in records}) == 4
    assert {r["source_code"] for r in records} == set(contracts)
    assert all(r["provenance"]["classification"] for r in records)
    assert {r["rule_id"] for r in policy["automatic_rules"]} >= {
        "company-cik", "person-cik", "sec-company-candidate", "sec-person-candidate"}


def test_removing_person_fixture_conversion_preserves_all_assertion_ids_and_provenance():
    import hashlib
    import json

    # Recorded from the retained conversion at 07cd4ef0, before replacing it
    # with raw Person fixture documents. Includes all four complete assertions.
    actual = json.dumps(cohort()[2], sort_keys=True).encode()
    assert hashlib.sha256(actual).hexdigest() == "35220d0129283863f957b93fee8317c4ce9ec390003d57d74d52e3709c29640c"
