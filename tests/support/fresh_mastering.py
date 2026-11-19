"""Small offline cohort under the repository's unchanged mastering rules.

Company rows come from the invented four-company fixture (tests/fixtures/clean_mdm/four_companies_v1/build.py). Person controls
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
    # Phase 1 (ticket 204) masters listed operating filers only; the pinned fixture states no tickers, so the two
    # operating rows are read with the tickers they have, and keyed by the row as pinned.
    listed = {9000001: ["ORCH"], 9000002: ["BLUF"]}
    company = [("sec.company.v1", {**row, "tickers": listed[row["cik"]]}, row) for row in fixture["sec"]
               if row["entity_type"] == "operating"]
    person_file = FIXTURE.with_name("person_raw.jsonl")
    person = [("sec.submissions.person.v1", (raw := json.loads(line)), raw)
              for line in person_file.read_text().splitlines() if line.strip()]
    for code, row, pinned in [*company, *person]:
        readings.append(normalize(
            row, source_code=code, contract=contracts[code], policy=policy,
            publication={"publication_key": f"offline-cohort/{pinned['cik']}@{digest(pinned)}",
                         "revision": 1, "artifact_sha256": digest(pinned),
                         "member": "four_companies_v1.json", "record_locator": str(pinned["cik"])},
        ))
    return policy, contracts, readings
