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

from typing import Any

from edgar_warehouse.rules import files as rules_files
from edgar_warehouse.rules.source_engine import compare_matching_values


def legal_form_key(name: Any) -> str:
    """Prepare a name for matching, keeping its legal form."""
    return compare_matching_values({"action": "prepare_name", "value": name})


def sec_legal_form_key(name: Any) -> str:
    """Legacy facade for names carrying a trailing place tag."""
    return compare_matching_values({"action": "prepare_name", "value": name, "remove_tag": True})


# Pinned reference data remains under Rules authority; comparisons belong to Rust.
_EDGAR_ISO = {
    row["code"]: target
    for row in rules_files.pinned_reference("sec-place-codes")
    for to_set, _version, target, match_type in row["crosswalk"]
    if to_set == "iso-3166" and match_type == "exact"
}
_US_TERRITORIES = frozenset({"PR", "GU", "VI", "MP", "AS"})


def edgar_jurisdiction(code: Any) -> str | None:
    """Read a pinned reference value using Rust's prepared lookup key."""
    key = compare_matching_values({"action": "prepare_reference_key", "value": code})
    return _EDGAR_ISO.get(key)


def jurisdictions_agree(sec: str | None, gleif: str | None) -> bool:
    return compare_matching_values({"action": "compare_places", "left": sec, "right": gleif})


def jurisdictions_conflict(sec: str | None, gleif: str | None, *, sec_business_country: str | None) -> bool:
    return compare_matching_values({
        "action": "find_place_conflict", "left": sec, "right": gleif,
        "business_country": sec_business_country,
    })


def postal_codes_agree(sec_code: Any, sec_country: str | None, gleif_code: Any, gleif_country: str | None) -> bool:
    return compare_matching_values({
        "action": "compare_postal_codes", "left": sec_code, "left_country": sec_country,
        "right": gleif_code, "right_country": gleif_country,
    })
