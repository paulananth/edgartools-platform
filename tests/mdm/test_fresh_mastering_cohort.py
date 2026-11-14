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


def test_the_cohort_records_are_the_recorded_ones():
    """Every assertion id and provenance of the four records, as one hash."""
    import hashlib
    import json

    actual = json.dumps(cohort()[2], sort_keys=True).encode()
    assert hashlib.sha256(actual).hexdigest() == "2ea20cf72fe8b1d96ccde80f380400a99f564476154b7cbbd657be1bcbbedec7"
