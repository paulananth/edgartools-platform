"""Hand-read labels for the rule .10 draws (Claude, 2026-09-25).

Every record in `12-10-sample.jsonl` (600), `12-10-adversarial.jsonl` (561)
and `12-10-held.jsonl` (100) was read by name, industry code, filer
category, catalog tickers and forms filed. Records with a real-estate or
investment code were also read against every older bronze submissions page,
and every record with both a Form 10 and a Form D was listed and read again.
Records not listed below were read as Companies; the note says on which
evidence.

Operator standards applied:
- registered funds and SEC `investment` filers are Funds;
- BDCs (an N-54A election) are Companies;
- exchange-traded commodity and crypto trusts are Funds;
- a private fund that registers by Form 10 and is not a BDC is a Fund
  (2026-09-25 05:58 ET);
- a private REIT that registers by Form 10 with a Form D offering is a Fund
  (2026-09-25 06:09 ET).

A REIT or partnership that registers a public offering on S-11 is read as a
Company, as in every earlier draw (Lightstone Value Plus REIT I, Bluerock
Homes Trust, Blackstone Digital Infrastructure Trust).

    uv run python .scratch/company-mastering/research/12-10-label.py
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

FUNDS = {
    # Violations: step 8 called these Companies.
    "0001412502": "Sterling Real Estate Trust: private REIT registered by Form 10 "
    "(10-12G, 2011, file 000-54295) with Form D offerings; no ticker, but a "
    "non-accelerated filer, so step 4 does not hold it.",
    "0001674356": "Terra Property Trust: non-traded REIT registered by Form 10 "
    "(10-12G) with Form D offerings; its catalog ticker is its NYSE-listed "
    "notes, so step 4 does not hold it.",
    # Held back by step 4: nothing is decided for them.
    "0001771514": "ExchangeRight Income Fund: private REIT registered by Form 10, "
    "Form D offering.",
    "0001986395": "Starwood Credit Real Estate Income Trust: private REIT "
    "registered by Form 10, Form D offering.",
    "0002026448": "Principal Credit Real Estate Income Trust: private REIT "
    "registered by Form 10, Form D offering.",
    "0002027537": "Goldman Sachs Real Estate Finance Trust: private REIT "
    "registered by Form 10, Form D offering.",
    "0002107762": "HPS Net Lease Income REIT: private REIT registered by Form 10.",
    "0002085428": "Nuveen Farmland REIT: private REIT registered by Form 10.",
    "0002032020": "EQT Private Equity Co: private equity vehicle registered by "
    "Form 10, Form D, no BDC election.",
    "0002065337": "Carlyle Private Equity Partners Fund: private equity fund "
    "registered by Form 10, Form D, no BDC election.",
    "0001971381": "Apollo Infrastructure Co: private infrastructure vehicle "
    "registered by Form 10, Form D, no BDC election.",
}

BORDERLINE_COMPANY = {
    "0001371782": "MV Oil Trust: listed royalty trust, read as a Company, as before.",
    "0001538822": "Pacific Coast Oil Trust: royalty trust, read as a Company, "
    "as MV Oil Trust.",
    "0000889123": "Redwood Mortgage Investors VIII: mortgage-lending partnership "
    "offering its units publicly on S-11; read as a Company under the S-11 "
    "standard, noted for the operator.",
    "0001662972": "Blackstone Real Estate Income Trust: non-traded REIT offered "
    "publicly on S-11; Company under the S-11 standard.",
    "0001498547": "CIM Real Estate Finance Trust (filed as CIM GROUP, INC.): "
    "non-traded REIT offered on S-11; Company under the S-11 standard.",
    "0001698538": "Strategic Student & Senior Housing Trust: non-traded REIT on "
    "S-11; Company under the S-11 standard.",
    "0001452936": "Pacific Oak Strategic Opportunity REIT: non-traded REIT on "
    "S-11; Company under the S-11 standard.",
    "0001482430": "KBS Real Estate Investment Trust III: non-traded REIT on S-11; "
    "Company under the S-11 standard.",
    "0001563756": "Lightstone Value Plus REIT III: non-traded REIT on S-11; "
    "Company under the S-11 standard.",
    "0001868516": "StratCap Digital Infrastructure REIT: non-traded REIT on S-11; "
    "Company under the S-11 standard.",
    "0001893262": "J.P. Morgan Real Estate Income Trust: non-traded REIT on S-11; "
    "Company under the S-11 standard.",
    "0001939433": "Cohen & Steers Income Opportunities REIT: non-traded REIT on "
    "S-11; Company under the S-11 standard.",
    "0001356115": "NexPoint Diversified Real Estate Trust: a registered closed-end "
    "fund (N-2, N-8A) that converted to a listed REIT (NYSE NXDT) filing 10-K; "
    "read as a Company, noted for the operator.",
    "0001785494": "Woodbridge Liquidation Trust: trust liquidating a failed "
    "real-estate business, filing 10-K; read as a Company, noted.",
    "0001684682": "CNL Strategic Capital: publicly offered (S-1) holding company; "
    "read as a Company, as before.",
    "0001696088": "Energy Resources 12: oil and gas drilling partnership offered "
    "on S-1; owns and operates wells; read as a Company.",
    "0001640967": "Rise Companies Corp: the operating company behind Fundrise, "
    "not one of its funds; read as a Company.",
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
    for name in ("12-10-sample.jsonl", "12-10-adversarial.jsonl", "12-10-held.jsonl"):
        rows = label(name)
        print(name, sum(r["final"] != "company" for r in rows), "not Companies")
