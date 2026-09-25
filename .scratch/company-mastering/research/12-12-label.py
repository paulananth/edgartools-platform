"""Hand-read labels for the Forms hold-back draws, rule 2026-09-25.12 (Claude, 2026-09-25).

Every record in `12-12-sample.jsonl` (600), `12-12-adversarial.jsonl` (320)
and `12-12-held.jsonl` (104) was read by name, industry code, filer
category, catalog tickers and forms filed. Records not listed below were
read as Companies; the note says on which evidence.

Operator standards applied:
- registered funds and SEC `investment` filers are Funds;
- BDCs (an N-54A election) are Companies;
- exchange-traded commodity and crypto trusts are Funds;
- a private fund that registers by Form 10 and is not a BDC is a Fund
  (2026-09-25 05:58 ET);
- a private REIT that registers by Form 10 with a Form D offering is a Fund
  (2026-09-25 06:09 ET).
A REIT or partnership that registers a public offering on S-11 is read as a
Company, and a listed royalty trust too, as in every earlier draw.

OPEN is a record no ruling covers. It is labelled as `OPEN_READING` says
until the operator rules; the score reports both readings.

    uv run python .scratch/company-mastering/research/12-12-label.py
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

FUNDS = {
    # Held back at 7a or 7b: nothing is decided for them.
    "0000803016": "California First Leasing Corp: now a registered closed-end fund "
    "(N-2, N-CSR, N-CEN, N-PORT).",
    "0001560672": "Ellington Credit Co: now a registered closed-end fund (N-CSR "
    "2026-05-29, N-CEN, N-PORT).",
    "0001578742": "GPB Automotive Portfolio: private vehicle registered by Form 10, "
    "Form D, no BDC election; as GPB Holdings II.",
    "0001690012": "InPoint Commercial Real Estate Income: non-traded REIT registered "
    "by Form 10 with Form D offerings; only its preferred shares listed.",
}

OPEN = {
    "0000946155": "TIAA Real Estate Account: a pooled real-estate account inside "
    "TIAA, sold to annuity holders under an S-1 and filing 10-K; not a legal "
    "person and not registered under the Investment Company Act. No ruling "
    "covers an insurance separate account.",
}
# Operator, 2026-09-25: an insurance company's separate account is a Fund.
OPEN_READING = "fund"

BORDERLINE_COMPANY = {
    "0000080172": "National Presto Industries: once deemed an investment company "
    "(N-8A, N-2), a manufacturer; read as a Company.",
    "0001356115": "NexPoint Diversified Real Estate Trust: former registered fund, "
    "now a listed REIT; read as a Company, as before.",
    "0001452477": "Seven Hills Realty Trust: former registered fund, now a listed "
    "mortgage REIT; read as a Company.",
    "0001563922": "Greenbacker Renewable Energy Co: once fund-like, now an operating "
    "power producer; read as a Company, noted.",
    "0001587987": "NewtekOne: former BDC (N-2, 497), now a bank holding company.",
    "0001724009": "PermRock Royalty Trust: listed royalty trust, read as a Company.",
    "0001581552": "Energy 11: oil and gas partnership offered on S-1; read as a "
    "Company, as Energy Resources 12.",
    "0001418372": "Salamander Innisbrook: resort rental-pool operator; a Company.",
    "0000310522": "Fannie Mae: federally chartered corporation; a Company, as the "
    "Federal Home Loan Banks.",
    "0000845877": "Farmer Mac: federally chartered corporation; a Company.",
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
        elif r["cik"] in OPEN:
            r["final"] = OPEN_READING
            r["note"] = OPEN[r["cik"]] + f" Read as {OPEN_READING} until ruled."
        else:
            r["final"], r["note"] = "company", company_note(r)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    return rows


if __name__ == "__main__":
    for name in ("12-12-sample.jsonl", "12-12-adversarial.jsonl", "12-12-held.jsonl"):
        rows = label(name)
        print(name, sum(r["final"] != "company" for r in rows), "not Companies")
