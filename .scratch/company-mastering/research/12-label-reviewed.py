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

# Judgments from reading the new seed-20260924.8 300-per-step draw. The
# previous draw's CIK exceptions are deliberately absent: they cannot be used
# as evidence for this version. A BDC is a Company under the operator's
# 2026-09-24 domain decision, despite N-2 or 40-APP filings.
SAMPLE_OTHER = {
    # Claude's recheck, 2026-09-24 ~21:50 ET, on the standard of the seed-.6
    # reading (a private fund with no BDC election is a Fund, as Blackstone
    # Private Equity Strategies Fund was): 10-12G, 10-K, Form D, tender offers,
    # no N-54A, no ticker.
    "0002045458": (
        "fund",
        "Stonepeak-Plus Infrastructure Fund LP: private infrastructure fund "
        "registered under 10-12G, no BDC election; a Fund, not a Company",
    ),
}
SAMPLE_COMPANY = {
    "0001125727": "First Interstate Bank files 8-K and NT 10-K; N-PX does not make the bank a fund.",
    "0001253986": "Real estate investment trust issuer with 10-K and 10-Q, not an asset-backed loan pool.",
    "0001297996": "Real estate investment trust issuer with 10-K and 10-Q, not an asset-backed loan pool.",
    "0001360604": "Real estate investment trust issuer with 10-K and 10-Q, not an asset-backed loan pool.",
    "0001547546": "Real estate investment trust issuer with 10-K, 10-Q and S-11, not an asset-backed loan pool.",
    "0001903382": "Real estate investment trust issuer with 10-K, 10-Q and S-11, not an asset-backed loan pool.",
    "0001944366": "Real estate investment trust issuer with 10-K and 10-Q, not an asset-backed loan pool.",
    "0001976927": "Real estate finance trust issuer with 10-K and 10-Q, not an asset-backed loan pool.",
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
    "0001420106": "Gilde Healthcare Holding B.V. is a legal holding company; ownership filings do not make it a person.",
    "0001743984": "GCM Investments GP, LLC is a legal entity in the ownership-only arm.",
    "0001826374": "BTO DE GP - NQ L.L.C. is a legal entity in the ownership-only arm.",
    "0002008590": "SPFM Holdings, LLC is a legal entity in the ownership-only arm.",
    "0002088704": "AAC II Holdings II LP is a legal partnership in the ownership-only arm.",
    "0002096490": "GreenWood Investors LLC is a legal entity in the ownership-only arm.",
    "0002146115": "Submarine Buyer Holdco LLC is a legal entity in the ownership-only arm.",
    "0002148329": "WSLS EMP OFFSHORE INVESTMENTS, L.P. is a legal partnership in the ownership-only arm.",
    "0002151486": "Serra Verde Rare Earths Ltd. is a legal entity in the ownership-only arm.",
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
    else:
        r["final"] = "company"
        if cik in SAMPLE_COMPANY:
            r["note"] = SAMPLE_COMPANY[cik]
        elif forms & {"N-2", "40-APP", "40-17G"} and "FUND" in name.upper():
            r["note"] = "BDC issuer with 10-K and 10-Q plus Investment Company Act filings; the operator treats a BDC as Company."
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
    elif "investment fund" in r["arms"]:
        assert forms & {"N-1A", "N-4", "N-6", "N-CEN", "N-CSR", "NPORT-P", "485BPOS", "497"}, cik
        r["final"] = "fund"
        r["note"] = "Fund prospectus or portfolio filings (" + ", ".join(sorted(forms & {"N-1A", "N-4", "N-6", "N-CEN", "N-CSR", "NPORT-P", "485BPOS", "497"})[:4]) + ")."
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
