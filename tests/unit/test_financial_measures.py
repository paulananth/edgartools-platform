"""Ticket 47: the measure definitions read only line items and the values computed
from them, and each filer's statement format and country follow its Company."""

from __future__ import annotations

import pytest
import yaml

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.financials import line_items, measures

CODES = set(line_items.load().period)


def test_the_definitions_name_every_measure_of_ticket_39():
    defined = measures.load()
    assert len(defined.ratios) == 10 and set(defined.returns) == {"roe", "roa", "roic"}
    assert defined.windows == (1, 3, 5, 10)
    assert defined.not_for_financial_services == {"gross_margin", "debt_to_assets", "debt_to_equity", "current_ratio",
                                                  "roic_average", "roic_beginning"}


def _with(part: str, value) -> dict:
    body = yaml.safe_load(measures.DEFINITIONS.read_text())
    body[part] = value
    return body


@pytest.mark.parametrize("part, value, refused", [
    ("ratios", {"turnover_margin": ["turnover", "revenue"]}, "two of the line items"),
    ("ratios", {"margin": ["revenue"]}, "two of the line items"),
    ("ratios", {"Margin; DROP": ["revenue", "assets"]}, "lower-case words"),
    ("growth", {"series": ["turnover"], "windows": [1]}, "growth reads line items"),
    ("growth", {"series": ["revenue"], "windows": [0]}, "whole number of years"),
    ("not_for_financial_services", ["gross_margin", "turnover_margin"], "not a measure"),
])
def test_the_definitions_are_refused_whole_when_one_breaks_its_grammar(part, value, refused):
    with pytest.raises(Blocked, match=refused):
        measures.parse(_with(part, value), CODES)


@pytest.mark.parametrize("sic, financial", [
    ("5999", False), ("6000", True), ("6199", True), ("6200", False), ("6300", True), ("6411", True),
    ("6412", False), (None, False), ("", False)])
def test_financial_services_is_sic_6000_to_6199_and_6300_to_6411(sic, financial):
    assert measures.financial_services(sic) is financial


def test_a_filer_s_country_is_its_place_of_incorporation_s_iso_country():
    formats = measures.filers({"1": ("6022", "PA"), "2": ("3571", "R1"), "3": ("3571", None)})
    # PA is the US state (US-PA), read as its country; R1 is Panama.
    assert formats == {"1": ("financial services", "US"), "2": ("industrial", "PA"), "3": ("industrial", None)}
