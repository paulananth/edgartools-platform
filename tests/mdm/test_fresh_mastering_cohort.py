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


def test_removing_person_fixture_conversion_preserves_all_assertion_ids_and_provenance(monkeypatch):
    import hashlib
    import json

    from edgar_warehouse.rules import files

    actual = json.dumps(cohort()[2], sort_keys=True).encode()
    assert hashlib.sha256(actual).hexdigest() == "e908d67bbdf589e1081ff77aa025d2e83b89ad154ea0846428f46bdbff10e8d2"
    # Rebuild ticket 10 made Person's quality v2 (one more check, which the
    # cohort passes); a record names its quality version. Under v1 the hash is
    # the one recorded from the retained conversion at 07cd4ef0, before it was
    # replaced with raw Person fixture documents (all four complete assertions).
    contract = files.mdm_contract

    def before_ticket_10(source, code, root=None):
        found = contract(source, code, root)
        if source != "sec.submissions.person":
            return found
        quality = found["quality"]
        return {**found, "quality": {**quality, "version": "sec-person-quality-v1",
                                     "checks": [c for c in quality["checks"] if c["id"] != "legal_name_has_letter"]}}

    monkeypatch.setattr(files, "mdm_contract", before_ticket_10)
    actual = json.dumps(cohort()[2], sort_keys=True).encode()
    assert hashlib.sha256(actual).hexdigest() == "35220d0129283863f957b93fee8317c4ce9ec390003d57d74d52e3709c29640c"
