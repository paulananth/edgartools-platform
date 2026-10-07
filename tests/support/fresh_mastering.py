"""Small offline cohort under the repository's unchanged mastering rules.

Company rows come from the pinned four-company fixture. Person controls
are separate raw JSON documents with their original field names; no runtime
field-name conversion is used.

GLEIF readings go through the real GLEIF reader (`record_evidence`): two
Level 1 records from the same fixture, and one accounting-parent record
between them. That parent record is synthetic, not a GLEIF fact.
"""

from pathlib import Path
import json

from edgar_warehouse.mdm.clean import gleif_source
from edgar_warehouse.mdm.clean.adapters import normalize
from edgar_warehouse.mdm.clean.store import digest
from edgar_warehouse.rules import files

ROOT = Path(__file__).resolve().parents[2]
AS_OF = "2026-10-01T14:00:00+00:00"
FIXTURE = ROOT / "tests/fixtures/clean_mdm/four_companies_v1/four_companies_v1.json"
# Apple (child) and Microsoft (parent): both are in the fixture's SEC and GLEIF
# rows. The link between them is synthetic.
CHILD_LEI, PARENT_LEI = "HWUPKR0MPOU8FGXBT394", "INR2EJN1ERAN0W5ZP974"


def cohort():
    policy = files.policy()
    contracts = {
        f"sec.submissions.{kind}.v1": files.mdm_contract(f"sec.submissions.{kind}", f"sec.submissions.{kind}.v1")
        for kind in ("company", "person")
    }
    fixture = json.loads(FIXTURE.read_text())
    readings = []
    company = [("sec.submissions.company.v1", row) for row in fixture["sec"]
               if row["entity_type"] == "operating"]
    person_file = FIXTURE.with_name("person_raw.jsonl")
    person = [("sec.submissions.person.v1", json.loads(line))
              for line in person_file.read_text().splitlines() if line.strip()]
    for code, row in [*company, *person]:
        readings.append(normalize(
            row, source_code=code, contract=contracts[code], policy=policy,
            publication={"publication_key": f"offline-cohort/{row['cik']}@{digest(row)}",
                         "revision": 1, "artifact_sha256": digest(row),
                         "member": "four_companies_v1.json", "record_locator": str(row["cik"])},
        ))
    return policy, contracts, readings


def _node(lei):
    return {"NodeID": {"$": lei}, "NodeIDType": {"$": "LEI"}}


def _gleif(member, row, ordinal):
    publication = {"publication_key": f"offline-cohort/gleif/{member}", "revision": 1,
                   "artifact_sha256": digest(row), "member": member,
                   "record_locator": str(ordinal)}
    outcome, reading = gleif_source.record_evidence(
        row, member=member, contract=gleif_source.dataset_contract(member),
        source_code=f"gleif.{member}.v1", eligible_leis={CHILD_LEI, PARENT_LEI},
        publication=publication, ordinal=ordinal)
    assert outcome == "assertion", reading
    return reading


def gleif_cohort():
    """The two GLEIF Level 1 readings, then the synthetic parent link reading."""
    fixture = json.loads(FIXTURE.read_text())
    level1 = [_gleif("level1", row, n) for n, row in enumerate(fixture["gleif"])
              if row["LEI"]["$"] in {CHILD_LEI, PARENT_LEI}]
    link = _gleif("relationships", {"RelationshipRecord": {
        "Relationship": {
            "StartNode": _node(CHILD_LEI), "EndNode": _node(PARENT_LEI),
            "RelationshipType": {"$": "IS_DIRECTLY_CONSOLIDATED_BY"},
            "RelationshipPeriods": {"RelationshipPeriod": {
                "PeriodType": {"$": "RELATIONSHIP_PERIOD"},
                "StartDate": {"$": "2020-01-01T00:00:00Z"}}},
            "RelationshipStatus": {"$": "ACTIVE"}},
        "Registration": {"LastUpdateDate": {"$": AS_OF}, "RegistrationStatus": {"$": "PUBLISHED"}},
    }}, 0)
    return level1, link


def gleif_successor(effective: str):
    """The child's Level 1 record again, now naming the parent as its successor
    with a completed merger on `effective` (synthetic: a parent absorbing its
    subsidiary; profiling ticket 04c), read by the real GLEIF reader."""
    fixture = json.loads(FIXTURE.read_text())
    (row,) = [r for r in fixture["gleif"] if r["LEI"]["$"] == CHILD_LEI]
    row = json.loads(json.dumps(row))
    row["Entity"]["SuccessorEntity"] = [{"SuccessorLEI": {"$": PARENT_LEI}}]
    row["Entity"]["LegalEntityEvents"] = {"LegalEntityEvent": [{
        "@event_status": "COMPLETED", "LegalEntityEventType": {"$": "MERGERS_AND_ACQUISITIONS"},
        "LegalEntityEventEffectiveDate": {"$": effective},
        "AffectedFields": {"AffectedField": [{"$": PARENT_LEI}]}}]}
    row["Registration"]["LastUpdateDate"] = {"$": AS_OF}
    # A later GLEIF publication: a new revision of the same record.
    publication = {"publication_key": "offline-cohort/gleif/level1/succession", "revision": 2,
                   "artifact_sha256": digest(row), "member": "level1", "record_locator": "0"}
    outcome, reading = gleif_source.record_evidence(
        row, member="level1", contract=gleif_source.dataset_contract("level1"), source_code="gleif.level1.v1",
        eligible_leis={CHILD_LEI, PARENT_LEI}, publication=publication, ordinal=0)
    assert outcome == "assertion", reading
    return reading
