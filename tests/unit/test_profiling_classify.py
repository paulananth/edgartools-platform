"""The five-class tests of the data-profiling skill."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "data-profiling" / "scripts"))
from profiling import classify  # noqa: E402

BASE = {"rows": 3000, "key": ["k"], "key_found": True, "in_degree": 2, "out_degree": 3, "self_ends": False,
        "key_links": 0, "key_other": 1, "name_like": 0, "labels": 0, "attributes": 0,
        "measures": 0, "event_time": "d", "metadata_share": 0.0, "rows_pointing": 8000, "rows_pointed": 100000}


def test_a_part_pointing_at_others_is_never_reference():
    decided = classify.classify(BASE)
    assert decided["class"] == "transaction"
    failed = [t for t in classify.classify({**BASE, "out_degree": 0})["tests"] if not t["passed"]]
    assert classify.classify({**BASE, "out_degree": 0})["class"] != "transaction" or failed


def test_link_part_needs_a_key_of_links():
    link = {**BASE, "in_degree": 0, "out_degree": 2, "key_links": 2, "key_other": 1, 
            "event_time": None}
    assert classify.classify(link)["class"] == "relationship"
    assert classify.classify({**link, "key_links": 1})["class"] != "relationship"


def test_a_tie_is_unknown_and_every_test_is_reported():
    nothing = {k: (0 if isinstance(v, (int, float)) else v) for k, v in BASE.items()}
    nothing.update({"key_found": False, "event_time": None, "key": []})
    decided = classify.classify(nothing)
    assert decided["class"] == "unknown" and decided["confidence"] == 0.0 and decided["tests"]


def test_store_is_advice_only():
    assert classify.store("reference") == {"store": "rdm", "why": classify.STORE["reference"][1], "advisory": True}


def test_link_part_between_records_of_one_part_may_key_on_one_end_and_a_role():
    link = {**BASE, "in_degree": 0, "out_degree": 1, "self_ends": True, "key_links": 1, "key_other": 1,
            "event_time": None}
    assert classify.classify(link)["class"] == "relationship"
    assert classify.classify({**link, "self_ends": False})["class"] != "relationship"
