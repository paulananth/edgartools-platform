"""Hand-read labels for the Account hold-back draws, rule 2026-09-25.13 (Claude, 2026-09-25).

Every record in `12-13-sample.jsonl` (600), `12-13-adversarial.jsonl` (328)
and `12-13-held.jsonl` (34) was read by name, industry code, filer
category, catalog tickers and forms filed. Records not listed below were
read as Companies; the note says on which evidence.

Operator standards applied:
- registered funds and SEC `investment` filers are Funds;
- BDCs (an N-54A election) are Companies;
- exchange-traded commodity and crypto trusts are Funds;
- a private fund that registers by Form 10 and is not a BDC is a Fund
  (2026-09-25 05:58 ET);
- a private REIT that registers by Form 10 with a Form D offering is a Fund
  (2026-09-25 06:09 ET);
- an insurance company's separate account is a Fund (2026-09-25).
A REIT or partnership that registers a public offering on S-11 is read as a
Company, and a listed royalty trust too, as in every earlier draw. A
corporation a government owns is a Company, not a Government Entity
(glossary): the Tennessee Valley Authority, Swedish Export Credit.

    uv run python .scratch/company-mastering/research/12-13-label.py
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

FUNDS = {
    # Held back at step 5 (fund-name words): nothing is decided for them.
    "0000812801": "Nuveen Municipal Value Fund: registered closed-end fund.",
    "0000845611": "Gabelli Convertible & Income Securities Fund: registered "
    "closed-end fund.",
    "0000919567": "RENN Fund: registered closed-end fund.",
    "0000946155": "TIAA Real Estate Account: insurance separate account; a Fund "
    "(operator, 2026-09-25).",
    "0001315061": "Ridgewood Energy O Fund: oil and gas investment program "
    "registered by Form 10, no BDC election.",
    "0001338474": "Ridgewood Energy Q Fund: as the O Fund.",
    "0001352190": "Ridgewood Energy S Fund: as the O Fund.",
    "0001364397": "Ridgewood Energy T Fund: as the O Fund.",
    "0001377178": "Ridgewood Energy U Fund: as the O Fund.",
    "0001385662": "Ridgewood Energy V Fund: as the O Fund.",
    "0001409947": "Ridgewood Energy W Fund: as the O Fund.",
    "0001434070": "Ridgewood Energy Y Fund: as the O Fund.",
    "0001455741": "Ridgewood Energy X Fund: as the O Fund.",
    "0001457919": "Ridgewood Energy A-1 Fund: as the O Fund.",
    "0002000046": "Fidelity Ethereum Fund: exchange-traded crypto trust.",
    "0002013744": "Bitwise Ethereum ETF: exchange-traded crypto trust.",
}

BORDERLINE_COMPANY = {
    "0001376986": "Tennessee Valley Authority: a corporation the US government "
    "owns; a Company under the glossary, not a Government Entity.",
    "0000352960": "Swedish Export Credit: a state-owned corporation; a Company.",
    "0000310522": "Fannie Mae: federally chartered corporation; a Company.",
    "0000070502": "National Rural Utilities Cooperative Finance: a cooperative "
    "lender; a Company.",
    "0001505413": "VOC Energy Trust: listed royalty trust, read as a Company.",
    "0000319655": "San Juan Basin Royalty Trust: listed royalty trust, read as a "
    "Company.",
    "0001704720": "Cannae Holdings: listed holding company; a Company.",
    "0001345122": "Compass Diversified: listed holding company; a Company.",
    "0000931755": "AEI Income & Growth Fund XXI: net-lease real-estate "
    "partnership offered publicly; a Company under the S-11 standard.",
    "0001023458": "AEI Income & Growth Fund XXII: as Fund XXI.",
    "0001185198": "AEI Income & Growth Fund 25: as Fund XXI.",
    "0001550453": "TriLinc Global Impact Fund: publicly offered (S-1) lender; "
    "read as a Company, noted.",
}


def company_note(r: dict) -> str:
    forms = set(r["forms"])
    if r["cik"] in BORDERLINE_COMPANY:
        return BORDERLINE_COMPANY[r["cik"]]
    if "N-54A" in forms:
        return "BDC (N-54A election); the operator counts BDCs as Companies."
    if r["sic"] == "6770":
        return "Blank-check company (SIC 6770)."
    if forms & {"20-F", "40-F", "6-K", "F-1", "F-4"}:
        return "Foreign issuer filing issuer reports or registrations."
    if forms & {"10-K", "10-Q", "S-1", "S-4", "10-12B", "8-K"}:
        return "Operating issuer; its forms and name read as a business."
    return "Operating business by name and its filings."


def label(name: str) -> list[dict]:
    path = HERE / name
    rows = [json.loads(line) for line in path.open()]
    for r in rows:
        if r["cik"] in FUNDS:
            r["final"], r["note"] = "fund", FUNDS[r["cik"]]
        else:
            r["final"], r["note"] = "company", company_note(r)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    return rows


if __name__ == "__main__":
    for name in ("12-13-sample.jsonl", "12-13-adversarial.jsonl", "12-13-held.jsonl"):
        rows = label(name)
        print(name, sum(r["final"] != "company" for r in rows), "not Companies")
