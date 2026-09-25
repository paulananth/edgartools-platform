"""Apply the recorded manual reading of ticket 12's frozen local draw.

Read the names and filing-form sets in both JSONL files before adding a CIK
exception here. This script records that reading; it does not fetch labels.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
LOOKS_LIKE_FUND = re.compile(r"\b(FUND|FUNDS|TRUST|PARTNERSHIP|PARTNERS|L\.?P\.?)\b", re.I)
ABS_FORMS = {"10-D", "ABS-EE", "ABS-15G", "SF-3"}

# Judgments from the hand reading of the frozen 300-per-step sample. Unknown
# serial investment issuers count against proof; their summary has no business
# description sufficient to certify Company rather than investment vehicle.
SAMPLE_OTHER = {
    "0000804123": ("fund", "N-2, N-CEN and N-CSR identify a registered investment fund."),
    "0000858706": ("fund", "N-2, N-CEN and N-CSR identify a registered investment fund."),
    "0000882300": ("fund", "N-2, N-CEN and N-CSR identify a registered investment fund."),
    "0001185198": ("fund", "Income and Growth Fund 25 LLC files 10-K/10-Q as a pooled investment issuer; no operating business is shown."),
    "0001462371": ("fund", "Mortgage Fund LLC files 1-A and 1-K as an investment issuer."),
    "0001785494": ("trust", "A liquidation trust, despite its 10-K and 10-Q; no ongoing Company business is shown."),
    "0001867706": ("fund", "Properties Fund III LLC files 1-A and 1-K as an investment issuer."),
    "0002039458": ("fund", "HBAR ETF is an exchange-traded fund even though SEC types it operating."),
    "0002065598": ("fund", "Seattle Fund LLC files 1-A and 1-K as an investment issuer."),
    "0002069560": ("fund", "Diversification Fund LLC files 1-A and 1-K as an investment issuer."),
}
SAMPLE_COMPANY = {
    "0001086363": "BlackRock Financial Management is the INC asset manager; 13F-NT and N-PX alone do not make it a fund.",
    "0001541356": "Marriott Ownership Resorts Inc files S-4; ABS-15G exposure alone does not make the issuer a loan trust.",
    "0001603794": "AerCap aviation issuer files 10-Q and F-3ASR; this trust is a financing Company issuer, not an ABS loan pool in the supplied forms.",
}

ADVERSARIAL_COMPANIES = {
    "0000779335": "GOULD INVESTORS L P is a limited partnership, despite ownership-only forms.",
    "0000905718": "LOWENSTEIN SANDLER LLP is a law firm partnership, despite ownership-only forms.",
    "0000931588": "Pension Fund Administrator is an operating administrator, with 20-F/6-K, not the pension fund.",
    "0001165495": "Government Systems CORP is a corporate supplier with S-3/S-4, not a government.",
    "0001173227": "Southern Michigan Bank & Trust is a bank, not a trust fund.",
    "0001273693": "S.A. de C.V. identifies a legal company in the ownership-only no-code arm.",
    "0001398453": "Xinyuan Real Estate Co. Ltd. files 20-F and 6-K; Company name includes Estate.",
    "0001472698": "KKR Group Partnership L.P. is an operating partnership with securities filings.",
    "0001475365": "Sumitomo Mitsui Trust Group Inc. files 20-F; corporate bank group.",
    "0001499849": "BrasilAgro Real Estate Company files 20-F and 6-K.",
    "0001666605": "Investments House Ltd is a legal entity in the ownership-only no-code arm.",
    "0001688727": "Keystone Cranberry LLC is a legal entity in the ownership-only no-code arm.",
    "0001705700": "Hill Path Capital Partners Co-Investment E LP is a legal partnership.",
    "0001712949": "Red Mountain Ventures Limited Partnership files 1-A/1-K as an issuer.",
    "0001713334": "Studio City International Holdings Ltd files 20-F and 6-K.",
    "0001714268": "W.D. Company Inc. is a legal entity in the ownership-only no-code arm.",
    "0001731171": "Squadron Capital Holdings LLC is a legal entity in the ownership-only no-code arm.",
    "0001861089": "Andrew Arroyo Real Estate Inc. files 1-A/1-K as a corporate issuer.",
    "0001866803": "Roots Real Estate Investment Community I LLC is a legal issuer filing 1-A/1-K.",
    "0001868036": "Invitation Homes Operating Partnership LP files S-3ASR as issuer.",
    "0001888980": "Lead Real Estate Co. Ltd. files 20-F and 6-K.",
    "0001950844": "HP G GP LLC is a legal entity in the ownership-only no-code arm.",
    "0001969373": "Vesta Real Estate Corporation files 20-F and 6-K.",
    "0002046656": "Happy City Holdings Ltd files 20-F and 6-K; City is part of its corporate name.",
    "0002078250": "Compound Real Estate Bonds II Inc. is a corporate bond issuer filing 1-A.",
    "0002100161": "Blackstone Digital Infrastructure Trust Inc. files S-11 and S-8 as a REIT Company.",
}
ADVERSARIAL_NONCOMPANIES = {
    "0000913115": ("trust", "Telephone & Data Systems voting trust, not the operating INC named within it; ownership-only forms."),
    "0001065416": ("individual", "HOLDING is Frank B Holding's surname; JR and forms 3/4/5 identify a person."),
    "0001352097": ("plan", "LNL Agents 401(k) Savings Plan is an employee benefit plan, not the sponsor."),
    "0002063457": ("trust", "JBH Investment Trust is the trust owner, not a Company; ownership form 144 only."),
    "0002142974": ("loan trust", "Bread Financial Card Issuance Trust files SF-3; financing issuer, conservatively treated as a loan trust."),
}
# Corporate-looking names that are actually investment vehicles, judged from
# the full name and filings. This includes the difficult Reg A fund issuers.
FUND_CIKS = {
    "0000918923", "0001074922", "0001462371", "0001477049", "0001494728",
    "0001539190", "0001726122", "0001781324", "0001817069", "0001817413",
    "0001852039", "0001867706", "0001886822", "0001915521", "0001915673",
    "0001953520", "0001954416", "0001957571", "0001982615", "0002000719",
    "0002007995", "0002023066", "0002025000", "0002040120", "0002046788",
    "0002056463", "0002060312", "0002062936", "0002065598", "0002069560",
    "0002071262", "0002071540", "0002073505", "0002087989", "0002092195",
    "0002094263", "0002096363", "0002097887", "0002102705", "0002103547",
    "0002103612", "0002103976", "0002117580", "0002119505", "0002108383",
}


def save(name, rows):
    (ROOT / name).write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))


sample = [json.loads(line) for line in (ROOT / "12-sample.jsonl").open()]
for r in sample:
    cik, name, forms = r["cik"], r["name"], set(r["forms"])
    if cik in SAMPLE_OTHER:
        r["final"], r["note"] = SAMPLE_OTHER[cik]
    elif name.startswith("Masterworks ") and forms & {"1-A", "1-K"}:
        r["final"] = "unsure"
        r["note"] = "Serial Masterworks LLC with 1-A/1-K investment offering filings; summary alone does not establish Company rather than Fund. Counted against proof."
    else:
        r["final"] = "company"
        if cik in SAMPLE_COMPANY:
            r["note"] = SAMPLE_COMPANY[cik]
        elif LOOKS_LIKE_FUND.search(name):
            evidence = ", ".join(sorted(forms & {"10-K", "10-Q", "20-F", "40-F", "S-1", "S-11", "N-54A", "1-A", "1-K"}))
            r["note"] = f"Read name and forms ({evidence or 'issuer filings'}): legal operating or financing issuer, not a registered fund or ABS pool."
save("12-sample.jsonl", sample)

adversarial = [json.loads(line) for line in (ROOT / "12-adversarial.jsonl").open()]
for r in adversarial:
    cik, name, forms = r["cik"], r["name"], set(r["forms"])
    if cik in ADVERSARIAL_NONCOMPANIES:
        r["final"], r["note"] = ADVERSARIAL_NONCOMPANIES[cik]
    elif cik in ADVERSARIAL_COMPANIES:
        r["final"] = "company"
        r["note"] = ADVERSARIAL_COMPANIES[cik]
    elif r["entity_type"] == "investment":
        r["final"] = "fund"
        r["note"] = "SEC investment filer; fund forms or separate-account filings, as in the operator's bronze review."
    elif forms & ABS_FORMS and ("TRUST" in name.upper() or "SECURITIZATION" in name.upper()):
        r["final"] = "loan trust"
        r["note"] = "Asset-backed pool: " + ", ".join(sorted(forms & ABS_FORMS)) + "."
    elif cik in FUND_CIKS:
        r["final"] = "fund"
        r["note"] = "Investment vehicle by name and issuer filings (" + ", ".join(sorted(forms & {"1-A", "1-K", "10-12G", "20-F", "40-F", "S-1", "N-2"}) or ["ownership and offering forms"]) + ")."
    elif re.search(r"\bETF\b", name, re.I):
        r["final"] = "fund"
        r["note"] = "Exchange-traded fund named ETF; the retained form set was read with the name."
    elif "ownership only with industry code" in r["arms"] or "ownership only without industry code" in r["arms"]:
        r["final"] = "individual"
        r["note"] = "Personal name; only ownership forms " + ", ".join(sorted(forms)[:4]) + "."
    elif name.upper().startswith(("ISRAEL, STATE OF", "JAMAICA GOVERNMENT", "REPUBLIC OF", "URUGUAY REPUBLIC", "FEDERATIVE REPUBLIC")):
        r["final"] = "government"
        r["note"] = "Sovereign filer; 18-K government annual report."
    elif "TRUST" in name.upper():
        r["final"] = "trust"
        r["note"] = "Trust investment issuer by name and forms; no operating Company evidence in summary."
    else:
        r["final"] = "company"
        r["note"] = "Legal issuer; filings include " + ", ".join(sorted(forms)[:4]) + "."
save("12-adversarial.jsonl", adversarial)
