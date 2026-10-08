"""RDM without a database (profiling ticket 02): a reference table drafts as a
code set version and rebuilds exactly; paths, cycles and the canonical form."""

import pytest

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.rdm import store, tables
from tests.support import place_codes

PLACES = [tables.Crosswalk.parse("iso=iso-3166@outside:exact"),
          tables.Crosswalk.parse("type=sec-place-types@1:broad")]


def test_the_place_code_table_drafts_and_rebuilds_exactly():
    table = place_codes.table()
    found = tables.draft(table, label="place", crosswalks=PLACES, source="test")
    assert len(found["codes"]) == len(table) == 309
    assert [t["code"] for t in found["targets"]["sec-place-types"]] == ["CANADIAN", "FOREIGN", "UNKNOWN", "US"]
    assert "iso-3166" not in found["targets"]  # an outside standard: RDM does not hold it
    assert not any(x["from_code"] == "XX" and x["to_set"] == "iso-3166" for x in found["crosswalk"])
    assert tables.rebuild(tables.as_version(found), label="place", crosswalks=PLACES) == table


def test_a_field_with_no_place_refuses_the_import():
    with pytest.raises(Blocked, match="no place"):
        tables.draft({"A": {"place": "X", "colour": "red"}}, label="place", crosswalks=[], source="test")
    with pytest.raises(Blocked, match="<field>="):
        tables.Crosswalk.parse("iso-3166")


def test_paths_follow_the_one_parent_and_refuse_cycles():
    codes = [{"code": "A", "label": "Finance", "parent_code": None},
             {"code": "A1", "label": "Depository", "parent_code": "A"},
             {"code": "A1/x", "label": "State banks", "parent_code": "A1"}]
    found = {p["code"]: p for p in store.paths(codes, {1: "division", 3: "industry"})}
    assert found["A1/x"] == {"code": "A1/x", "path": "A/A1/A1\\/x", "label_path": "Finance > Depository > State banks",
                             "level": "industry", "depth": 3}
    assert found["A1"]["level"] is None and found["A"]["depth"] == 1
    with pytest.raises(Blocked, match="cycle"):
        store.paths([{"code": "A", "label": "a", "parent_code": "B"}, {"code": "B", "label": "b", "parent_code": "A"}], {})
    with pytest.raises(Blocked, match="lacks"):
        store.paths([{"code": "A", "label": "a", "parent_code": "Z"}], {})


def test_the_canonical_form_is_order_free_and_covers_labels_and_crosswalks():
    one = {"code": "B", "label": "b", "labels": [{"language": "en", "kind": "preferred", "label": "b"}],
           "crosswalk": [{"to_set": "x", "to_version": "1", "to_code": "y", "match_type": "exact"}]}
    two = {"code": "A", "label": "a"}
    assert store.canonical([one, two]) == store.canonical([two, one])
    assert store.canonical([one, two]).decode().splitlines()[0].startswith('{"code":"A"')
    moved = {**one, "crosswalk": [{**one["crosswalk"][0], "to_code": "z"}]}
    assert store.sha256([one, two]) != store.sha256([moved, two])
    assert store.sha256([one, two]) != store.sha256([one, two], {1: "division"})  # level names are in the pin
