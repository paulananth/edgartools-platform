"""Hand-read labels for the rule .9 draws (Claude, 2026-09-25).

Every record in `12-9-sample.jsonl` (600) and `12-9-adversarial.jsonl` (432)
was read by name, industry code, filer category and forms filed. Records not
listed below were read as Companies; the note says on which evidence.

Operator standards applied: registered funds and SEC `investment` filers are
Funds; BDCs (an N-54A election) are Companies; exchange-traded commodity and
crypto trusts are Funds; a private fund that registers by Form 10 and is not a
BDC is a Fund, holding-company-style vehicles included (2026-09-25 05:58 ET).

PENDING_OPERATOR records are private REITs that register by Form 10 with a
Form D offering. The operator has not ruled on them; they are labelled Fund
here, the reading that counts against the rule, and the summary reports the
result both ways.

    uv run python .scratch/company-mastering/research/12-9-label.py
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

FUNDS = {
    "0002089975": "HPS Real Assets Lending Co LP: private credit vehicle "
    "registered by Form 10 (10-12G), no BDC election.",
    "0001640265": "GPB Holdings II: private-placement holding vehicle (Form D) "
    "registered by Form 10, no BDC election; Fund under the operator's "
    "2026-09-25 decision.",
}
PENDING_OPERATOR = {
    "0002027537": "Goldman Sachs Real Estate Finance Trust: private REIT "
    "registered by Form 10 (10-12G, Form D).",
    "0001914496": "Sculptor Diversified Real Estate Income Trust: private REIT "
    "registered by Form 10 (10-12G, Form D).",
    "0002107762": "HPS Net Lease Income REIT: private REIT registered by Form 10.",
}

BORDERLINE_COMPANY = {
    "NORTH EUROPEAN OIL ROYALTY TRUST": "Listed royalty trust: not a fund or a "
    "loan trust; read as a Company, noted for the operator.",
    "MV Oil Trust": "Listed royalty trust: read as a Company, noted for the "
    "operator.",
    "CNL Strategic Capital, LLC": "Publicly offered (S-1) holding company that "
    "controls private businesses; not a Form-10 private fund; read as a "
    "Company, noted for the operator.",
}


def company_note(r: dict) -> str:
    forms = set(r["forms"])
    if r["name"] in BORDERLINE_COMPANY:
        return BORDERLINE_COMPANY[r["name"]]
    if "N-54A" in forms:
        return "Former or current BDC election, now an operating issuer."
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
        elif r["cik"] in PENDING_OPERATOR:
            r["final"] = "fund"
            r["note"] = PENDING_OPERATOR[r["cik"]] + " Pending the operator."
        else:
            r["final"], r["note"] = "company", company_note(r)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    return rows


if __name__ == "__main__":
    for name in ("12-9-sample.jsonl", "12-9-adversarial.jsonl"):
        rows = label(name)
        print(name, sum(r["final"] != "company" for r in rows), "not Companies")
