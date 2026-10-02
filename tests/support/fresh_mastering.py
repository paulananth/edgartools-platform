"""Small offline cohort under the repository's unchanged mastering rules.

Company rows come from the pinned four-company fixture. Its two individual
controls are converted back to the raw field names consumed by the Person
adapter; this conversion is fixture setup, not a new acquisition reader.
"""

from pathlib import Path
import json

from edgar_warehouse.mdm.clean.adapters import normalize
from edgar_warehouse.mdm.clean.store import digest
from edgar_warehouse.rules import files

ROOT = Path(__file__).resolve().parents[2]
AS_OF = "2026-10-01T14:00:00+00:00"


def cohort():
    policy = files.policy()
    contracts = {
        f"sec.submissions.{kind}.v1": files.mdm_contract(f"sec.submissions.{kind}", f"sec.submissions.{kind}.v1")
        for kind in ("company", "person")
    }
    fixture = json.loads((ROOT / "tests/fixtures/clean_mdm/four_companies_v1/four_companies_v1.json").read_text())
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
