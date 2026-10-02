"""Small offline cohort under the repository's unchanged mastering rules.

Company rows come from the pinned four-company fixture. Its two individual
controls are converted back to the raw field names consumed by the Person
adapter; this conversion is fixture setup, not a new acquisition reader.

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
    for original in fixture["sec"]:
        if original["entity_type"] == "operating":
            code, row = "sec.submissions.company.v1", original
        elif not original["sic"]:
            code = "sec.submissions.person.v1"
            row = {"cik": original["cik"], "name": original["entity_name"],
                   "entityType": original["entity_type"], "sic": original["sic"],
                   "ein": original["ein"], "fiscalYearEnd": original["fiscal_year_end"],
                   "stateOfIncorporation": original["state_of_incorporation"]}
        else:
            continue
        readings.append(normalize(
            row, source_code=code, contract=contracts[code], policy=policy,
            publication={"publication_key": f"offline-cohort/{original['cik']}@{digest(row)}",
                         "revision": 1, "artifact_sha256": digest(row),
                         "member": "four_companies_v1.json", "record_locator": str(original["cik"])},
        ))
    return policy, contracts, readings


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
    node = lambda lei: {"NodeID": {"$": lei}, "NodeIDType": {"$": "LEI"}}
    link = _gleif("relationships", {"RelationshipRecord": {
        "Relationship": {
            "StartNode": node(CHILD_LEI), "EndNode": node(PARENT_LEI),
            "RelationshipType": {"$": "IS_DIRECTLY_CONSOLIDATED_BY"},
            "RelationshipPeriods": {"RelationshipPeriod": {
                "PeriodType": {"$": "RELATIONSHIP_PERIOD"},
                "StartDate": {"$": "2020-01-01T00:00:00Z"}}},
            "RelationshipStatus": {"$": "ACTIVE"}},
        "Registration": {"LastUpdateDate": {"$": AS_OF}, "RegistrationStatus": {"$": "PUBLISHED"}},
    }}, 0)
    return level1, link
