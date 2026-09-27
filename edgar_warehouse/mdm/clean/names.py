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

from edgar_warehouse.rules import files as rules_files

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
# `stateOrCountry` and `countryCode`) as GLEIF writes a jurisdiction. The table
# is reference data in `rules/reference/sec-place-codes.yaml`: SEC's whole list
# (309 codes), with the ISO codes company mastering ticket 08 built from
# bronze. The policy body carries the same file, so its digest pins it.
_EDGAR_ISO = {
    code: row["iso"]
    for code, row in rules_files.reference("sec-place-codes")["codes"].items()
    if row["iso"]
}
# SEC codes these as states; GLEIF may write them as countries.
_US_TERRITORIES = frozenset({"PR", "GU", "VI", "MP", "AS"})


def edgar_jurisdiction(code: Any) -> str | None:
    """An EDGAR state or country code as an ISO jurisdiction, or None if unknown."""
    return _EDGAR_ISO.get(str("" if code is None else code).strip().upper())


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
