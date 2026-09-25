"""Name, jurisdiction and postal comparisons for the SEC-to-GLEIF matching rule.

Company mastering ticket 08. Pure functions: no store, clock or network, so a
pinned policy digest reproduces every result. A correction is a new version,
never an edit (`primitives.py`).

**The legal form is kept.** The earlier comparison cut INC, LLC and LP off
both names before comparing, and so matched parents to their subsidiaries:
"Wayfair Inc." to "WAYFAIR LLC", "COUSINS PROPERTIES INC" to "COUSINS
PROPERTIES LP". Here only the *spelling* of a legal form is unified
(CORPORATION is CORP, L.L.C. is LLC), never its presence. Measured on the 883
reviewed development pairs: `.scratch/company-mastering/research/08-draft-rule.md`.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# One spelling per legal form, longest first so "L L P" is not read as "L P".
_FORMS = (
    ("L L C", "LLC"),
    ("L L P", "LLP"),
    ("L P", "LP"),
    ("P L C", "PLC"),
    ("N V", "NV"),
    ("S A", "SA"),
    ("A G", "AG"),
    ("S E", "SE"),
    ("B V", "BV"),
    ("CORPORATION", "CORP"),
    ("INCORPORATED", "INC"),
    ("COMPANY", "CO"),
    ("LIMITED", "LTD"),
    ("HOLDINGS", "HLDGS"),
    ("INTERNATIONAL", "INTL"),
)
# The state tag SEC appends to a conformed name: "BERKSHIRE HATHAWAY INC /DE/".
_SEC_TAG = re.compile(r"\s*/[A-Z0-9 .]{1,6}/?\s*$")


def legal_form_key(name: Any) -> str:
    """A name with its legal form kept: WAYFAIR INC and WAYFAIR LLC differ."""
    text = unicodedata.normalize("NFKD", str("" if name is None else name))
    text = "".join(c for c in text if not unicodedata.combining(c)).upper()
    text = text.replace("&", " AND ")
    text = " " + re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", text)).strip() + " "
    for long, short in _FORMS:
        text = text.replace(f" {long} ", f" {short} ")
    text = text.strip()
    return text.removeprefix("THE ")


def sec_legal_form_key(name: Any) -> str:
    """The same key for an SEC conformed name, after its state tag is dropped."""
    return legal_form_key(_SEC_TAG.sub("", str("" if name is None else name).upper()))


# EDGAR state and country codes (SEC `stateOfIncorporation`, address
# `stateOrCountry` and `countryCode`) as GLEIF writes a jurisdiction. Built
# from the descriptions SEC writes beside each code in bronze: 156 codes seen
# across 76,230 filers (ticket 08, `research/08-edgar-codes.json`).
_US_STATES = frozenset(
    [
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "DC",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
        "PR",
        "GU",
        "VI",
    ]
)
# SEC codes these as states; GLEIF may write them as countries.
_US_TERRITORIES = frozenset({"PR", "GU", "VI"})
_EDGAR_CODES = {
    "A0": "CA-AB", "A1": "CA-BC", "A2": "CA-MB", "A3": "CA-NB", "A4": "CA-NL",
    "A5": "CA-NS", "A6": "CA-ON", "A8": "CA-QC", "A9": "CA-SK", "Z4": "CA",
    "1E": "BA", "1H": "EE", "1P": "KZ", "1Q": "LT", "1T": "MH", "1U": "MK",
    "1Z": "RU", "2A": "SI", "2B": "SK", "2J": "UM", "2K": "UZ", "2M": "DE",
    "2N": "CZ", "B1": "BW", "B9": "AG", "C0": "AE", "C1": "AR", "C3": "AU",
    "C4": "AT", "C5": "BS", "C6": "BH", "C8": "BB", "C9": "BE", "D0": "BM",
    "D1": "BZ", "D5": "BR", "D6": "IO", "D8": "VG", "E0": "BG", "E9": "KY",
    "F3": "CL", "F4": "CN", "F5": "TW", "F8": "CO", "G2": "CR", "G4": "CY",
    "G7": "DK", "G8": "DO", "H1": "EC", "H2": "EG", "H3": "SV", "H9": "FI",
    "I0": "FR", "J1": "GI", "J3": "GR", "K3": "HK", "K5": "HU", "K6": "IS",
    "K7": "IN", "K8": "ID", "L2": "IE", "L3": "IL", "L6": "IT", "L7": "CI",
    "L8": "JM", "M0": "JP", "M2": "JO", "M3": "KE", "M5": "KR", "M6": "KW",
    "M8": "LB", "N0": "LR", "N2": "LI", "N4": "LU", "N8": "MY", "O1": "MT",
    "O4": "MU", "O5": "MX", "O9": "MC", "P4": "OM", "P7": "NL", "P8": "CW",
    "Q1": "VN", "Q2": "NZ", "Q5": "NG", "Q8": "NO", "R0": "PK", "R1": "PA",
    "R5": "PE", "R6": "PH", "R9": "PL", "S1": "PT", "S3": "QA", "T0": "SA",
    "T3": "ZA", "U0": "SG", "U3": "ES", "U7": "KN", "V6": "SZ", "V7": "SE",
    "V8": "CH", "W0": "TZ", "W1": "TH", "W5": "TT", "W6": "TN", "W8": "TR",
    "X0": "GB", "X1": "US", "X3": "UY", "X5": "VE", "Y0": "WS", "Y7": "GG",
    "Y8": "IM", "Y9": "JE", "Z2": "RS",
}  # fmt: skip


def edgar_jurisdiction(code: Any) -> str | None:
    """An EDGAR state or country code as an ISO jurisdiction, or None if unknown."""
    code = str("" if code is None else code).strip().upper()
    if code in _US_STATES:
        return f"US-{code}"
    return _EDGAR_CODES.get(code)


def jurisdictions_agree(sec: str | None, gleif: str | None) -> bool:
    """Whether two ISO jurisdictions name the same place of incorporation.

    Exactly equal, or outside the US a country on one side and a subdivision of
    it on the other (GB and GB-ENG). A US record must name its state: Delaware
    and Nevada are different places to incorporate.
    """
    if not sec or not gleif:
        return False
    sec, gleif = sec.upper(), gleif.upper()
    if sec == gleif:
        return True
    if sec.startswith("US-") and sec[3:] in _US_TERRITORIES:
        return gleif == sec[3:]
    s_country, g_country = sec.split("-")[0], gleif.split("-")[0]
    if s_country == "US" or s_country != g_country:
        return False
    return "-" not in sec or "-" not in gleif


def jurisdictions_conflict(
    sec: str | None, gleif: str | None, *, sec_business_country: str | None
) -> bool:
    """Whether SEC and GLEIF name two different places of incorporation.

    The postal step's veto (ticket 08). Its first version bound AAON, Inc., a
    Nevada parent, to GLEIF's AAON, Inc. of Oklahoma, its subsidiary of the
    same name at the same address. A side naming no place, or naming only the
    country the other side's subdivision sits in, is no conflict.

    SEC's US state is set aside when SEC's own business address and GLEIF's
    jurisdiction both put the entity in one other country: Shell's SEC state
    of incorporation reads "DC", while both place it in Britain.
    """
    if not sec or not gleif:
        return False
    sec, gleif = sec.upper(), gleif.upper()
    if jurisdictions_agree(sec, gleif):
        return False
    s_country, g_country = sec.split("-")[0], gleif.split("-")[0]
    if s_country == g_country and ("-" not in sec or "-" not in gleif):
        return False
    return not (
        s_country == "US"
        and sec_business_country is not None
        and sec_business_country != "US"
        and sec_business_country == g_country
    )


def _postal(code: Any) -> str:
    text = re.sub(r"[^A-Z0-9]", "", str("" if code is None else code).upper())
    return text[:5] if re.fullmatch(r"\d{5}(\d{4})?", text) else text


def postal_codes_agree(
    sec_code: Any, sec_country: str | None, gleif_code: Any, gleif_country: str | None
) -> bool:
    """Whether two postal codes in one country are the same code.

    SEC keeps only the four digits of a Dutch code ("5504" for "5504 DR"), so
    that one shape agrees on a prefix, in the Netherlands only.
    """
    s, g = _postal(sec_code), _postal(gleif_code)
    if not s or not g or not sec_country or sec_country != gleif_country:
        return False
    if s == g:
        return True
    return (
        sec_country == "NL"
        and re.fullmatch(r"\d{4}", s) is not None
        and re.fullmatch(r"\d{4}[A-Z]{2}", g) is not None
        and g.startswith(s)
    )
