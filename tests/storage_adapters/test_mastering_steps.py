"""Conformance of the six approved mastering steps (CONTEXT.md, "Mastering"), one test per statement, on invented records.

Each test states the step it checks. A test that fails against the engine is a finding, never softened to pass.
"""

from edgar_warehouse.mdm.evidence import assertion
from tests.storage_adapters.test_mastering import COMPANY, GLEIF, opened, record, merge

CUSTODIANS = "iapd.adv.custodians.v1"
NAME_ID = "a1" * 32  # an invented name id (64 hex)


def custodian(key: str, name_id: str) -> dict:
    return assertion(source_code=CUSTODIANS, record_key=key, publication_key="invented", revision=1, effective_at=None,
                     kind="company", fields={"name": f"INVENTED {key}"}, cross_references={"name_id": name_id})


def open_reviews(db, subject: str) -> int:
    db.commit()
    return db.rows("select count(*) from mastering_review where subject=%s and open_review=1", [subject])[0][0]


def test_step_6_a_record_left_waiting_has_a_recorded_reason(database_factory):
    """Step 6: every decision is recorded. A record a rule leaves waiting has an open review saying so, for a
    name-only custodian (an exact-name rule) as for a GLEIF record (a name rule); before, the exact-name wait left none."""
    with opened(database_factory) as db:
        named = custodian("c1", NAME_ID)
        gleif = record(GLEIF, "g1", "company", {"name": "INVENTED GLEIF"}, lei="9999000000EXAMPLE016")
        merge.merge_file(db, COMPANY, [named, gleif])
        assert db.bound([named["subject"], gleif["subject"]]) == {}  # neither has a golden record
        assert open_reviews(db, named["subject"]) == 1
        assert open_reviews(db, gleif["subject"]) == 1


def named_custodian(key: str, **references) -> dict:
    return assertion(source_code=CUSTODIANS, record_key=key, publication_key="invented", revision=1, effective_at=None,
                     kind="company", fields={"name": f"INVENTED {key}"}, cross_references=references)


def test_step_1_a_custodian_named_only_by_name_has_a_golden_record(database_factory):
    """Step 1 (operator, 2026-11-09: "Name plus place"): a name that ends in a legal form makes one Company whatever
    its place; a name with no legal form makes one Company per place. Before, both waited with no golden record."""
    form_id, other_form_id, place_one, place_two = "e1" * 32, "e2" * 32, "f1" * 32, "f2" * 32
    with opened(database_factory) as db:
        records = [named_custodian("form-a", name_id=form_id, name_form_id=form_id, name_place_id=place_one),
                   named_custodian("form-b", name_id=form_id, name_form_id=form_id, name_place_id=place_two),
                   named_custodian("form-c", name_id=other_form_id, name_form_id=other_form_id, name_place_id=place_one),
                   named_custodian("bare-a", name_id="d1" * 32, name_place_id="c1" * 32),
                   named_custodian("bare-b", name_id="d1" * 32, name_place_id="c2" * 32)]
        merge.merge_file(db, COMPANY, records)
        bound = db.bound([r["subject"] for r in records])
        assert len(bound) == 5  # every record has a golden record
        by_key = {r["record_key"]: bound[r["subject"]] for r in records}
        assert by_key["form-a"] == by_key["form-b"] != by_key["form-c"]  # one legal-form name, one Company, whatever the place
        assert by_key["bare-a"] != by_key["bare-b"]  # one bare name in two places is two Companies
        assert len(set(bound.values())) == 4
