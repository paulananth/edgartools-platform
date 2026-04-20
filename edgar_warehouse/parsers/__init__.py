"""Parser dispatch for warehouse form-family parsers."""

from __future__ import annotations

from edgar_warehouse.parsers.adv import parse_adv
from edgar_warehouse.parsers.ownership import parse_ownership

OWNERSHIP_FORMS = {"3", "3/A", "4", "4/A", "5", "5/A"}
ADV_FORMS = {"ADV", "ADV/A", "ADV-E", "ADV-E/A", "ADV-H", "ADV-H/A", "ADV-NR", "ADV-W", "ADV-W/A"}


def get_parser(form_type: str):
    if form_type in OWNERSHIP_FORMS:
        return parse_ownership
    if form_type in ADV_FORMS:
        return parse_adv
    raise ValueError(f"No dedicated parser for form type {form_type}")
