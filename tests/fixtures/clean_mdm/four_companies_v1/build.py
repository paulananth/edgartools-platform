"""Write four_companies_v1.json and person_raw.jsonl: an invented cohort of four SEC filers (two operating companies,
two other entity types) and two individual filers.

Every name, identifier and figure here is invented (the repository is public): nothing is recorded from a provider.
The two operating companies are the ones the offline mastering cohort reads (tests/support/fresh_mastering.py); the
pinned hash of its records is in tests/mdm/test_fresh_mastering_cohort.py, so a change here changes that hash once.

Usage: python build.py
"""

import hashlib
import json
from pathlib import Path

COMPANIES = [
    # Operating companies: listed filers.
    (9000001, "ORCHARD DATA SYSTEMS INC", "operating", "000000001", "7372", "Services-Prepackaged Software", "DE", "0630"),
    (9000002, "BLUEFERN HARDWARE CORP", "operating", "000000002", "3571", "Electronic Computers", "CA", "0926"),
    # Other entity types: a foreign issuer and a holding company, which the cohort does not master.
    (9000003, "KESTREL ENERGY PLC", "other", "000000000", "1311", "Crude Petroleum & Natural Gas", "DC", "1231"),
    (9000004, "QXLM MACHINERY HOLDING NV", "other", "000000000", "3559", "Special Industry Machinery, NEC", "", "1231"),
]
PERSONS = [(9000005, "DOE JANE Q"), (9000006, "ROE RICHARD")]


def main() -> None:
    folder = Path(__file__).parent
    sec = []
    for cik, name, kind, ein, sic, sic_description, state, year_end in COMPANIES:
        raw = hashlib.sha256(f"invented filer {cik}".encode()).hexdigest()
        sec.append({
            "category": "Large accelerated filer", "cik": cik, "description": "", "ein": ein, "entity_name": name,
            "entity_type": kind, "fiscal_year_end": year_end, "sic": sic, "sic_description": sic_description,
            "state_of_incorporation": state, "state_of_incorporation_desc": state,
            "sync_run_id": "invented-fixture", "last_sync_run_id": "invented-fixture", "load_mode": "fixture",
            "raw_object_id": raw,
        })
    for cik, name in PERSONS:
        sec.append({
            "category": "", "cik": cik, "description": "", "ein": None, "entity_name": name, "entity_type": "other",
            "fiscal_year_end": None, "sic": "", "sic_description": "", "state_of_incorporation": "",
            "state_of_incorporation_desc": "", "sync_run_id": "invented-fixture",
            "last_sync_run_id": "invented-fixture", "load_mode": "fixture",
            "raw_object_id": hashlib.sha256(f"invented filer {cik}".encode()).hexdigest(),
        })
    body = {"version": 1,
            "purpose": "invented cohort: two operating companies, two other filers and two individual filers; "
                       "test selection, not matching evidence",
            "sec": sec}
    (folder / "four_companies_v1.json").write_text(
        json.dumps(body, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    (folder / "person_raw.jsonl").write_text("".join(
        json.dumps({"cik": cik, "ein": None, "entityType": "other", "fiscalYearEnd": None, "name": name, "sic": "",
                    "stateOfIncorporation": ""}, sort_keys=True, separators=(",", ":")) + "\n" for cik, name in PERSONS))


if __name__ == "__main__":
    main()
