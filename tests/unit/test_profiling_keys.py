"""Keys and links of the data-profiling skill, on a synthetic data set."""

import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")  # in the mdm extra, which CI installs

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "data-profiling" / "scripts"))
from profiling import inputs, keys, profile  # noqa: E402
from tests.unit.profiling_fixture import build  # noqa: E402


@pytest.fixture(scope="module")
def found(tmp_path_factory):
    folder = build(tmp_path_factory.mktemp("data") / "set")
    con = duckdb.connect()
    parts = {p.name: p for p in inputs.register(con, "set", str(folder), folder.parent / "w")}
    profiles = {name: profile.columns(con, name) for name in parts}
    unique = {name: keys.unique_keys(con, name, cols) for name, cols in profiles.items()}
    single = keys.links(con, profiles, unique, parts, {})
    return {"con": con, "parts": parts, "profiles": profiles, "keys": unique, "links": single,
            "composite": keys.composite_links(con, profiles, unique)}


def link(found, part, column):
    return next((l for l in found["links"] if (l["from"]["part"], l["from"]["columns"]) == (part, [column])), None)


def test_single_and_composite_keys_are_exact(found):
    assert found["keys"]["member"] == [["member_id"]]
    assert ["item_code"] in found["keys"]["item"]
    assert found["keys"]["line"] == [["visit_id", "line_no"]]
    assert found["keys"]["pairing"] == [["member_a", "member_b", "role"]] or \
        found["keys"]["pairing"] == [["member_a", "member_b"]]


def test_near_inclusion_link_is_found_with_its_sigma(found):
    l = link(found, "visit", "member_id")
    assert l["to"] == {"part": "member", "columns": ["member_id"]}
    assert 0.9 <= l["inclusion"] < 1.0 and l["cardinality"] == "N:1"


def test_small_numbers_do_not_link_to_a_counter(found):
    assert link(found, "line", "qty") is None


def test_links_of_line_pairing_and_codes(found):
    assert link(found, "line", "item_code")["to"]["part"] == "item"
    assert link(found, "line", "visit_id")["to"]["part"] == "visit"
    assert link(found, "pairing", "member_a")["to"]["part"] == "member"
    assert link(found, "pairing", "member_b")["to"]["part"] == "member"
    assert link(found, "member", "grp_code")["to"] == {"part": "grp", "columns": ["grp_code"]}
    assert link(found, "grp", "parent_grp_code")["to"] == {"part": "grp", "columns": ["grp_code"]}


def test_record_key_prefers_the_key_others_point_at():
    columns = [{"name": "day", "structure": False}, {"name": "day_number", "structure": False}]
    incoming = [{"to": {"part": "cal", "columns": ["day"]}}]
    chosen = keys.choose_record_key("cal", [["day_number"], ["day"]], columns, incoming, None)
    assert chosen["columns"] == ["day"] and chosen["found"] and chosen["alternatives"] == [["day_number"]]


def test_designed_keys_when_none_is_found():
    child = keys.choose_record_key("p.l", [], [], [], ["k"])
    assert child["columns"] == ["k", "_position"] and child["design"] == "natural_composite"
    columns = [{"name": "a", "structure": False, "fill": 1.0, "distinct": 3, "type": "VARCHAR", "tokens": 1}]
    surrogate = keys.choose_record_key("p", [], columns, [], None)
    assert surrogate["design"] == "surrogate" and "a" in surrogate["rule"] and not surrogate["found"]


def test_sampled_key_is_confirmed_in_full_and_links_use_every_value(tmp_path):
    import json
    con = duckdb.connect()
    (tmp_path / "m.jsonl").write_text("\n".join(json.dumps({"ref": f"R{i:05d}", "v": i % 7}) for i in range(2000)))
    (tmp_path / "e.csv").write_text("ref\n" + "".join(f"R{i:05d}\n" for i in range(0, 2000, 3)))
    m = inputs.register(con, "m", str(tmp_path / "m.jsonl"), tmp_path / "w", limit=10, sample=100, seed=1)[0]
    inputs.register(con, "e", str(tmp_path / "e.csv"), tmp_path / "w")
    from profiling import profile as columns_of
    confirmed = {"m": keys.confirm_sampled(con, m, [["ref"]], columns_of.columns(con, "m"))}
    assert confirmed["m"]["ref"]["unique"] and confirmed["m"]["ref"]["rows"] == 2000
    measured = keys.inclusion(con, "e", "ref", "m", "ref", confirmed)
    assert measured["sigma"] == 1.0


def test_child_key_unique_within_its_parent_and_plain_value_lists(tmp_path):
    import json
    con = duckdb.connect()
    f = tmp_path / "p.json"
    # The same reference appears under two parents (shared by both), once per parent.
    f.write_text(json.dumps([{"id": "A", "refs": [{"r": "x1"}, {"r": "x2"}], "tags": ["t", "t"]},
                             {"id": "B", "refs": [{"r": "x1"}], "tags": ["u"]}]))
    inputs.register(con, "p", str(f), tmp_path / "w")
    refs = profile.columns(con, "p.refs")
    assert keys.unique_keys(con, "p.refs", refs) == []
    within = keys.unique_within_parent(con, "p.refs", refs)
    chosen = keys.choose_record_key("p.refs", [], refs, [], ["id"], within)
    assert chosen["columns"] == ["id", "r"] and chosen["found"]
    assert keys.plain_values(profile.columns(con, "p.tags"))


def test_zero_padded_text_matches_numbers(tmp_path):
    con = duckdb.connect()
    con.execute("CREATE TABLE p AS SELECT lpad(CAST(i AS VARCHAR), 10, '0') AS ref FROM range(1, 200) r(i)")
    con.execute("CREATE TABLE f AS SELECT (i % 199) + 1 AS ref FROM range(500) r(i)")
    assert keys.inclusion(con, "f", "ref", "p", "ref", {})["sigma"] == 0.0
    assert keys.inclusion(con, "f", "ref", "p", "ref", {}, as_number=True)["sigma"] == 1.0
