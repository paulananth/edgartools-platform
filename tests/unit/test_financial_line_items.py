"""Ticket 46: the line-item map names RDM's `financial-line-items` codes, and
every concept it reads is in that code set's crosswalk, and nothing else."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "rules" / "sources" / "sec.company-facts" / "line-items.yaml"
PUBLISHED = ROOT / "rules" / "reference" / "published"
TAXONOMIES = ("us-gaap", "ifrs-full")


# How a flagged concept relates to its line item, as SKOS mapping relations:
# broad when it holds more than the line item, narrow when less, close when it
# is the same figure read another way. A new flag needs its line here.
FLAG_MATCH = {
    "includes NCI": "broad", "includes software and intangibles": "broad",
    "includes intangibles and other assets": "broad", "includes restricted cash": "broad",
    "includes other finance costs": "broad", "includes impairment": "broad",
    "continuing operations": "narrow", "excludes amortization": "narrow",
    "excludes amortisation": "narrow", "cash only": "narrow", "cover-page date": "close",
}


def _concept(name: str, taxonomy: str) -> tuple[str, str]:
    """A concept's taxonomy and name; `dei:` names a cover-page concept."""
    return ("dei", name[4:]) if name.startswith("dei:") else (taxonomy, name)


def crosswalk_of(body: dict) -> dict[tuple[str, str, str], str]:
    """Each (line item, taxonomy, concept) the map tries as the line item itself,
    with its match type. A computed value's terms are inputs, not mappings, so
    they stay in the map only."""
    found: dict[tuple[str, str, str], str] = {}
    for code, lists in body["line_items"].items():
        for taxonomy in TAXONOMIES:
            for entry in lists[taxonomy]:
                if isinstance(entry, str):
                    found[(code, *_concept(entry, taxonomy))] = "close"
                elif "concept" in entry:
                    flag = entry.get("flag")
                    found[(code, *_concept(entry["concept"], taxonomy))] = FLAG_MATCH[flag] if flag else "close"
    return found


def _published(code_set: str, version: str) -> list[dict]:
    folder = PUBLISHED / code_set / version
    data = (folder / "canonical.jsonl").read_bytes()
    assert hashlib.sha256(data).hexdigest() == json.loads((folder / "pin.json").read_text())["sha256"]
    return [json.loads(line) for line in data.decode().splitlines()]


def test_the_map_names_the_code_set_s_codes_in_both_taxonomies():
    body = yaml.safe_load(MAP.read_text())
    pin = body["code_set"]
    codes = {row["code"] for row in _published(pin["code_set"], pin["version"])}
    assert set(body["line_items"]) == codes and len(codes) == 23
    for code, lists in body["line_items"].items():
        assert set(lists) == set(TAXONOMIES), code
        for taxonomy in TAXONOMIES:
            for entry in lists[taxonomy]:
                if isinstance(entry, dict) and "computed" in entry:
                    assert entry["computed"] in ("sum", "difference") and entry["terms"], code
                    refs = [t["line_item"] for t in entry["terms"] if isinstance(t, dict) and "line_item" in t]
                    assert set(refs) <= codes - {code}, code


def test_every_concept_the_map_reads_is_in_the_crosswalk_and_nothing_else():
    body = yaml.safe_load(MAP.read_text())
    pin = body["code_set"]
    published = {(row["code"], to_set, concept): match
                 for row in _published(pin["code_set"], pin["version"])
                 for to_set, version, concept, match in row["crosswalk"] if version == "outside"}
    assert published == crosswalk_of(body)


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
