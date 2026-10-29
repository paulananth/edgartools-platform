"""Ticket 46: the line-item map names RDM's `financial-line-items` codes, and
every concept it reads is in that code set's crosswalk, and nothing else."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.financials import line_items
from edgar_warehouse.financials.line_items import FLAG_MATCH, crosswalk_of

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "rules" / "sources" / "sec.company-facts" / "line-items.yaml"
PUBLISHED = ROOT / "rules" / "reference" / "published"
TAXONOMIES = ("us-gaap", "ifrs-full")


def _published(code_set: str, version: str) -> list[dict]:
    folder = PUBLISHED / code_set / version
    data = (folder / "canonical.jsonl").read_bytes()
    assert hashlib.sha256(data).hexdigest() == json.loads((folder / "pin.json").read_text())["sha256"]
    return [json.loads(line) for line in data.decode().splitlines()]


def test_the_map_names_the_code_set_s_codes_in_both_taxonomies():
    items = line_items.load(MAP)
    assert len(items.lists) == 23 and all(set(lists) == set(TAXONOMIES) for lists in items.lists.values())
    # gross profit reads revenue, so revenue is built first
    assert [s for s in items.stages() if "gross_profit" in s] != [s for s in items.stages() if "revenue" in s]
    assert items.larger_total_check == {"revenue": "revenue quality check"}


def _with(code: str, entries: list) -> dict:
    body = yaml.safe_load(MAP.read_text())
    body["line_items"][code]["us-gaap"] = entries
    return body


@pytest.mark.parametrize("code, entries, refused", [
    ("total_debt", [{"computed": "sum", "terms": [{"optional": "Debt"}, "LongTermDebt"]}], "first term"),
    ("gross_profit", [{"computed": "sum", "terms": [{"line_item": "revenue"}]}], "reads at least one fact"),
    ("revenue", [{"computed": "sum", "terms": ["Revenues", {"line_item": "gross_profit"}]}], "cycle"),
    ("revenue", [{"computed": "sum", "terms": ["Revenues", {"line_item": "turnover"}]}], "unknown line item"),
    ("revenue", [{"concept": "Revenues", "flag": "a new flag"}], "no match type"),
    ("revenue", ["Revenues'; DROP TABLE x"], "not a concept name"),
    ("revenue", [{"computed": "product", "terms": ["Revenues"]}], "sum or a difference"),
])
def test_the_map_is_refused_whole_when_an_entry_breaks_its_grammar(code, entries, refused):
    with pytest.raises(Blocked, match=refused):
        line_items.parse(_with(code, entries))


def test_none_of_research_01_s_concept_hazards_is_in_the_map():
    """Research 01 section 5, hazards 1 to 6: concepts the old code and edgartools
    read as a line item they are not."""
    items = line_items.load(MAP)
    read = {(code, concept) for code, lists in items.lists.items() for t in TAXONOMIES for e in lists[t]
            for _, concept in ([e.concept] if e.concept else [c for term in e.terms for c in term.concepts])}
    concepts = {concept for _, concept in read}
    assert "LineOfCreditFacilityRemainingBorrowingCapacity" not in concepts  # 1: undrawn capacity
    assert ("liabilities", "LiabilitiesAndStockholdersEquity") in read  # 2: only as a term less equity
    assert all(e.concept is None for e in items.lists["liabilities"]["us-gaap"]
               if any(("us-gaap", "LiabilitiesAndStockholdersEquity") in t.concepts for t in e.terms))
    assert ("assets", "AssetsCurrent") not in read  # 3
    assert not {"CommonStockSharesIssued", "WeightedAverageNumberOfSharesOutstandingBasic"} & {
        c for code, c in read if code == "shares_outstanding"}  # 4
    assert not {"IncomeTaxesPaidNet", "InterestIncomeExpenseNet", "AmortizationOfIntangibleAssets"} & concepts  # 5
    assert "CurrentPortionOfLongTermDebt" not in concepts  # 6
    assert not any(("us-gaap", "LongTermDebt") in t.concepts and ("us-gaap", "LongTermDebtCurrent") in u.concepts
                   for e in items.lists["total_debt"]["us-gaap"] for t in e.terms for u in e.terms)  # 6


def test_every_concept_the_map_reads_is_in_the_crosswalk_and_nothing_else():
    body = yaml.safe_load(MAP.read_text())
    pin = body["code_set"]
    published = {(row["code"], to_set, concept): match
                 for row in _published(pin["code_set"], pin["version"])
                 for to_set, version, concept, match in row["crosswalk"] if version == "outside"}
    assert published == crosswalk_of(line_items.parse(body))


def test_the_crosswalk_states_how_each_kind_of_entry_relates():
    pin = yaml.safe_load(MAP.read_text())["code_set"]
    rows = {(row["code"], to_set, concept): match
            for row in _published(pin["code_set"], pin["version"])
            for to_set, _, concept, match in row["crosswalk"]}
    assert rows[("revenue", "us-gaap", "Revenues")] == "close"
    assert rows[("revenue", "us-gaap", "PremiumsEarnedNet")] == "close"  # an industry kind is the line item
    assert rows[("net_income", "us-gaap", "ProfitLoss")] == "broad"  # includes NCI
    assert rows[("cash", "ifrs-full", "Cash")] == "narrow"  # cash only
    assert rows[("shares_outstanding", "dei", "EntityCommonStockSharesOutstanding")] == "close"
    assert ("book_value", "us-gaap", "MinorityInterest") not in rows  # a computed value's term
    assert not any(code == "total_debt" for code, _, _ in rows)  # every form is computed
