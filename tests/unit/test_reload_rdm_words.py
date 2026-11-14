"""Every published code set has its words and source in scripts/dev/reload_rdm.py (ticket 189), so an empty RDM reloads."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("reload_rdm", ROOT / "scripts/dev/reload_rdm.py")
reload_rdm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reload_rdm)


def published() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for pin in (ROOT / "rules/reference/published").glob("*/*/pin.json"):
        found.setdefault(pin.parent.parent.name, set()).add(pin.parent.name)
    return found


def test_every_published_version_has_its_words_and_a_place_in_the_order():
    held = published()
    assert set(reload_rdm.WORDS) == set(held) == set(reload_rdm.ORDER)
    for code_set, words in reload_rdm.WORDS.items():
        assert set(words["versions"]) == held[code_set]
        assert words["name"] and words["definition"] and words["authority"] and words["ticket"]


def test_a_crosswalk_target_is_loaded_before_the_set_that_points_at_it():
    import json
    order = reload_rdm.ORDER
    for code_set in order:
        for version in reload_rdm.WORDS[code_set]["versions"]:
            for line in (reload_rdm.PUBLISHED / code_set / version / "canonical.jsonl").read_text().splitlines():
                for to_set, to_version, _, _ in json.loads(line)["crosswalk"]:
                    if to_set in order:
                        assert order.index(to_set) < order.index(code_set), (code_set, to_set)


def test_a_next_version_holds_every_published_code_and_the_added_one():
    import pytest
    from edgar_warehouse.control_contract import Blocked

    added = [{"code": "INVESTMENT_ADVISER_TO:invented", "parent_code": "INVESTMENT_ADVISER_TO", "level": "Capacity",
              "label": "Invented", "definition": "An invented capacity. Source: a test."}]
    body = reload_rdm.next_draft("mdm-relationship-types", "99", added)
    newest = max(reload_rdm.WORDS["mdm-relationship-types"]["versions"], key=int)
    rows = (reload_rdm.PUBLISHED / "mdm-relationship-types" / newest / "canonical.jsonl").read_text().splitlines()
    assert body["supersedes"] == newest and body["version"] == "99"
    assert [c["code"] for c in body["codes"]][-1] == "INVESTMENT_ADVISER_TO:invented"
    assert len(body["codes"]) == len(rows) + 1
    assert {"depth": 2, "name": "Capacity"} in body["levels"]
    with pytest.raises(Blocked, match="already held"):
        reload_rdm.next_draft("mdm-relationship-types", "99", [{**added[0], "code": "INVESTMENT_ADVISER_TO"}])
