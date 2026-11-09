"""Small offline cohort under the repository's unchanged mastering rules.

Company rows come from the pinned four-company fixture. Person controls
are separate raw JSON documents with their original field names; no runtime
field-name conversion is used.
"""

from pathlib import Path
import json

from edgar_warehouse.mdm.adapters import normalize
from edgar_warehouse.mdm.store import digest
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
        code: files.mdm_contract(source, code)
        for source, code in (
            ("sec.company", "sec.company.v1"),
            ("sec.submissions.person", "sec.submissions.person.v1"),
        )
    }
    fixture = json.loads(FIXTURE.read_text())
    readings = []
    company = [("sec.company.v1", row) for row in fixture["sec"]
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
