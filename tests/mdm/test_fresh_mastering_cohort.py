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
    from tests.mdm.test_rules_config_digests import WITHOUT_TICKET_129_FIELDS, _with_company_fields_back
    from tests.support import person_quality

    actual = json.dumps(cohort()[2], sort_keys=True).encode()
    assert hashlib.sha256(actual).hexdigest() == "a539af8021c6704a95d63d28301a5b322b1ddc0c6009fa35cadb846ddf82155b"
    # Ticket 129 took the SIC code's label out of the Company; with it put back
    # the cohort is the one pinned before.
    current = files.mdm_contract

    def with_company_fields(source, code, root=None):
        found = current(source, code, root)
        return _with_company_fields_back(found, code) if code in WITHOUT_TICKET_129_FIELDS else found

    monkeypatch.setattr(files, "mdm_contract", with_company_fields)
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
        return person_quality.before_ticket_10(found)

    monkeypatch.setattr(files, "mdm_contract", before_ticket_10)
    actual = json.dumps(cohort()[2], sort_keys=True).encode()
    assert hashlib.sha256(actual).hexdigest() == "35220d0129283863f957b93fee8317c4ce9ec390003d57d74d52e3709c29640c"
