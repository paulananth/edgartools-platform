"""Hand-read labels for `12-adversarial-2.jsonl` (Claude, 2026-09-24).

Every one of the 339 records was read by name, industry code, filer category
and forms filed. Records not listed in FUNDS were read as Companies; the note
says on which evidence. Operator standards applied (2026-09-24): SEC
`investment` filers and registered funds are Funds; BDCs (an N-54A election)
are Companies; exchange-traded commodity and crypto trusts are Funds; private
funds are Funds (Stonepeak-Plus, the earlier Blackstone private-equity fund).

    uv run python .scratch/company-mastering/research/12-label-adversarial-2.py
"""

import json
from pathlib import Path

PATH = Path(__file__).resolve().parent / "12-adversarial-2.jsonl"

FUNDS = {
    "0000845611": "Registered closed-end fund: files N-CSR, N-CEN and N-2.",
    "0000919567": "Registered closed-end fund: files N-CSR and N-CEN.",
    "0001844684": "Files N-CSR, N-CEN and NPORT-P, a registered fund's reports, "
    "after its N-54A: now a registered fund.",
    "0001953940": "Private equity fund registered under the Exchange Act (10-12G), "
    "no BDC election.",
    "0001957845": "KKR's perpetual private-equity vehicle (10-12G, Form D offering), "
    "no BDC election; same standard as the Blackstone private-equity fund.",
    "0001974395": "Face-amount certificate company: registered under the "
    "Investment Company Act (N-8A, 497).",
    "0002000046": "Exchange-traded crypto trust (S-1, 10-K).",
    "0002000597": "Private credit vehicle registered under the Exchange Act "
    "(10-12G, Form D), no BDC election.",
    "0002013744": "Exchange-traded crypto trust.",
    "0002032020": "Private equity vehicle (10-12G, Form D), no BDC election.",
    "0002039458": "Exchange-traded crypto trust.",
    "0002046946": "Private fund (10-12G, Form D), no BDC election.",
    "0002059924": "Private infrastructure vehicle (10-12G, Form D), no BDC election.",
    "0002065337": "Private equity fund (10-12G, Form D), no BDC election.",
    "0002073537": "Private credit vehicle (10-12G, Form D, 40-APP), no BDC election.",
    "0002074450": "Private fund (10-12G, Form D), no BDC election.",
    "0002082826": "Private equity fund (10-12G, Form D), no BDC election.",
    "0002096330": "Private equity fund (10-12G, Form D), no BDC election.",
}


def company_note(r: dict) -> str:
    forms = set(r["forms"])
    if "N-54A" in forms:
        return "BDC (N-54A election); the operator counts BDCs as Companies."
    if r["sic"] == "6770":
        return "Blank-check company (SIC 6770) registering its offering."
    if forms & {"20-F", "40-F", "6-K", "F-1", "F-4"}:
        return "Foreign issuer filing issuer reports or registrations."
    if forms & {"10-K", "10-Q", "S-1", "S-4", "10-12B", "8-K"}:
        return "Operating issuer; its forms and name read as a business."
    return "Operating business by name and its offering filings."


rows = [json.loads(line) for line in PATH.open()]
for r in rows:
    if r["cik"] in FUNDS:
        r["final"], r["note"] = "fund", FUNDS[r["cik"]]
    else:
        r["final"], r["note"] = "company", company_note(r)
PATH.write_text(
    "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
)
print(json.dumps({"labelled": len(rows), "funds": len(FUNDS)}))
