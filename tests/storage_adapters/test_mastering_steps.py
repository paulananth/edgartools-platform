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
