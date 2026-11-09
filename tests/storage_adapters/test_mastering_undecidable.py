"""Step 1 of mastering: a record whose entity type cannot be decided waits, and no golden record is created for it.

The three sources whose entity type a classification rule decides, on invented rows through the real Dataset Contracts and
the real mastering merge: a record the rule cannot decide is refused by its adapter with a reason, set aside by the merge
with that reason, and creates no golden record; a decidable record of the same source creates one (the control).
"""

import pytest

from edgar_warehouse.mdm import adapters
from edgar_warehouse.mdm.evidence import deferred_record
from edgar_warehouse.mastering.reconcile import reconcile
from edgar_warehouse.rules import files
from tests.storage_adapters.test_mastering import AS_OF, POLICY, opened, merge

PUBLICATION = {"publication_key": "invented", "revision": 1, "artifact_sha256": "a" * 64, "member": "invented"}

COMPANY = ("sec.company", "sec.company.v1", "company",
           {"cik": 777001, "entity_name": "Example Holdings Inc", "entity_type": "other", "sic": "", "tickers": [],
            "forms": ["10-K"], "last_sync_run_id": "c1", "last_synced_at": "2026-01-01T00:00:00+00:00", "raw_object_id": "r1"},
           {"cik": 777002, "entity_name": "Example Corp", "entity_type": "operating", "sic": "3571", "tickers": ["EXC"],
            "forms": ["10-K"], "last_sync_run_id": "c1", "last_synced_at": "2026-01-01T00:00:00+00:00", "raw_object_id": "r2"},
           "classification_deferred")
PERSON = ("sec.submissions.person", "sec.submissions.person.v1", "person",
          {"cik": 777003, "name": "EXAMPLE ADVISORS LLC", "entityType": "other", "ein": None, "sic": "",
           "fiscalYearEnd": None, "stateOfIncorporation": ""},
          {"cik": 777004, "name": "COOK TIMOTHY D", "entityType": "other", "ein": None, "sic": "",
           "fiscalYearEnd": None, "stateOfIncorporation": ""},
          "classification_entity_undetermined")
OWNER = ("sec.ownership", "sec.ownership.reporting_owner.v1", "person",
         {"accession_number": "0000777005-26-000001", "rpt_owner_cik": 777005, "rpt_owner_name": "EXAMPLE CAPITAL LLC"},
         {"accession_number": "0000777006-26-000001", "rpt_owner_cik": 777006, "rpt_owner_name": "COOK TIMOTHY D",
          "is_director": True, "issuer_cik": 320193, "period_of_report": "2026-01-02"},
         "classification_entity_undetermined")


def read(source: str, code: str, row: dict) -> dict:
    return adapters.normalize(row, source_code=code, contract=files.mdm_contract(source, code), policy=POLICY,
                              publication={**PUBLICATION, "record_locator": str(row.get("cik") or row.get("rpt_owner_cik"))})


@pytest.mark.parametrize("source,code,kind,undecidable,decidable,reason", [COMPANY, PERSON, OWNER],
                         ids=["sec.company", "sec.submissions.person", "sec.ownership.reporting_owner"])
def test_an_undecidable_record_is_set_aside_with_its_reason_and_creates_no_golden_record(
        database_factory, source, code, kind, undecidable, decidable, reason):
    with pytest.raises(adapters.UnsupportedRecord) as refused:
        read(source, code, undecidable)
    assert refused.value.reason.startswith("classification_")  # the adapter refuses it with a classification reason
    held = deferred_record(source_code=code, publication_key="invented", record_locator="1", schema_version="1",
                           reason=refused.value.reason, raw_record=undecidable, provenance=refused.value.detail,
                           probable_kind=refused.value.probable_kind)
    settings = merge.Settings(POLICY, "invented-digest", kind, AS_OF)
    with opened(database_factory) as db:
        merge.merge_file(db, settings, [], deferred=[held])
        db.commit()
        assert db.rows("select count(*) from mastering_master")[0][0] == 0  # no golden record was created
        assert db.rows("select count(*) from mastering_record")[0][0] == 0
        assert db.rows("select reason from mastering_deferred where source_code=%s", [code]) == [(refused.value.reason,)]
        (closed,) = reconcile(db, code)  # the source's accounts close: one set aside, none stored, none waiting
        assert (closed["set_aside_delivered"], closed["set_aside_stored"], closed["stored"], closed["closes"]) == (1, 1, 0, True)
        # The control: a decidable record of the same source is mastered, so the test tells the two apart.
        merge.merge_file(db, settings, [read(source, code, decidable)])
        db.commit()
        assert db.rows("select count(*) from mastering_master")[0][0] == 1
        (closed,) = reconcile(db, code)
        assert (closed["new"], closed["stored"], closed["golden_record"], closed["set_aside_stored"], closed["closes"]) == (1, 1, 1, 1, True)
