"""Parser dispatch for warehouse form-family parsers."""

from __future__ import annotations

from edgar_warehouse.parsers.adv import parse_adv
from edgar_warehouse.parsers.earnings_release import parse_earnings_release
from edgar_warehouse.parsers.ownership import parse_ownership
from edgar_warehouse.parsers.proxy_fundamentals import parse_proxy_fundamentals

OWNERSHIP_FORMS = {"3", "3/A", "4", "4/A", "5", "5/A"}
ADV_FORMS = {"ADV", "ADV/A", "ADV-E", "ADV-E/A", "ADV-H", "ADV-H/A", "ADV-NR", "ADV-W", "ADV-W/A"}
PROXY_FORMS = {"DEF 14A", "DEF 14A/A", "DEFA14A", "PRE 14A"}
EARNINGS_8K_FORMS = {"8-K", "8-K/A"}

# 13F and EntityFacts parsers are NOT in this dispatch — they use separate
# command paths (bootstrap-fundamentals / bootstrap-entity-facts) because:
#   - 13F: primary artifact is the cover XML; infotable is a separate attachment
#   - EntityFacts: CIK-level API call, not per-filing


def get_parser(form_type: str):
    if form_type in OWNERSHIP_FORMS:
        return parse_ownership
    if form_type in ADV_FORMS:
        return parse_adv
    if form_type in PROXY_FORMS:
        return parse_proxy_fundamentals
    if form_type in EARNINGS_8K_FORMS:
        return parse_earnings_release
    raise ValueError(f"No dedicated parser for form type {form_type}")
