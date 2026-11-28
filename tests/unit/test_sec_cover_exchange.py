"""A cover's exchange wording names a Trading Venue through `sec-cover-exchange`: each wording crosswalks to an ISO
10383 MIC RDM holds, and a segment's venue is its operating MIC."""
import json
from pathlib import Path

PUBLISHED = Path(__file__).resolve().parents[2] / "rules" / "reference" / "published"


def rows(code_set: str, version: str) -> dict:
    return {row["code"]: row for row in map(json.loads, (PUBLISHED / code_set / version / "canonical.jsonl").open())}


def venue(wording: str) -> str:
    """The operating MIC a wording names, or none for a wording the set lacks."""
    held = rows("sec-cover-exchange", "1").get(" ".join(wording.upper().split()))
    if held is None:
        return None
    [(to_set, to_version, mic, match)] = held["crosswalk"]
    assert (to_set, match) == ("iso-10383-mic", "exact")
    code = rows(to_set, to_version)[mic]
    return code["parent_code"] or code["code"]


def test_each_cover_wording_names_its_venue_and_an_unmapped_one_names_none():
    assert {wording: venue(wording) for wording in (
        "Nasdaq", "Nasdaq Stock Market", "Nasdaq Capital Market", "NASDAQ Global Market", "Nasdaq Global Select Market",
        "New York Stock Exchange", "nySe", "NYSE American", " NYSE  American ", "Example Exchange")} == {
        "Nasdaq": "XNAS", "Nasdaq Stock Market": "XNAS", "Nasdaq Capital Market": "XNAS", "NASDAQ Global Market": "XNAS",
        "Nasdaq Global Select Market": "XNAS", "New York Stock Exchange": "XNYS", "nySe": "XNYS", "NYSE American": "XNYS",
        " NYSE  American ": "XNYS", "Example Exchange": None}

