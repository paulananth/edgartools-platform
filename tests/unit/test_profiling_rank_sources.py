"""Source ranking (rebuild priorities ticket 110): which source states each field best,
measured from the sources' own records."""

import json
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "data-profiling" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import profile_data  # noqa: E402
import rank_sources as rs  # noqa: E402


def write(path: Path, rows: list[dict]) -> str:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return str(path)


def test_values_are_compared_normalised():
    assert rs.normalise("  Acme, Inc. ") == rs.normalise("ACME INC") == "ACME INC"
    assert rs.normalise("Cl-A") == "CL A"


def test_a_dotted_path_walks_nested_records_and_lists():
    record = {"name": {"sample": [{"label": "one"}, {"label": "two"}, {"other": "x"}]}, "id": "k1"}
    assert list(rs.walk(record, ["name", "sample", "label"])) == ["one", "two"]
    assert list(rs.walk(record, ["missing"])) == []


def test_measures_and_order(tmp_path):
    # Bureau: one value per key, three of four keys. Filers: every key, a key repeated
    # with two different words. Registry: one value per key, two keys.
    bureau = write(tmp_path / "bureau.jsonl", [
        {"id": "k1", "title": "Alpha"}, {"id": "k2", "title": "Beta"}, {"id": "k3", "title": "Gamma"}])
    filers = write(tmp_path / "filers.jsonl", [
        {"id": "k1", "title": "ALPHA"}, {"id": "k1", "title": "Alpha Corp"},
        {"id": "k2", "title": "Beta"}, {"id": "k3", "title": "Gamma"}, {"id": "k4", "title": "Delta"}])
    registry = write(tmp_path / "registry.csv", [])
    (tmp_path / "registry.csv").write_text("code,label\nk1,Other\nk4,Delta\n", encoding="utf-8")
    ranking = rs.rank({"bureau": (bureau, "id"), "filers": (filers, "id"), "registry": (registry, "code")},
                      {"title": {"bureau": "title", "filers": "title", "registry": "label"}})
    title = ranking["fields"]["title"]
    assert title["keys"] == 4
    assert title["sources"]["bureau"] == {"keys": 3, "coverage": 0.75, "one_value_keys": 3, "one_value": 1.0}
    assert title["sources"]["filers"] == {"keys": 4, "coverage": 1.0, "one_value_keys": 3, "one_value": 0.75}
    assert title["sources"]["registry"]["coverage"] == 0.5
    pairs = {tuple(p["sources"]): (p["keys_both"], p["agree"]) for p in title["agreement"]}
    # k1: the filers state ALPHA among their words, so they share a value with the bureau.
    assert pairs[("bureau", "filers")] == (3, 3)
    assert pairs[("bureau", "registry")] == (1, 0)
    assert pairs[("filers", "registry")] == (2, 1)
    # One value first, then coverage: registry (one value each, half the keys) before filers.
    assert title["recommended"] == ["bureau", "registry", "filers"] and title["tied"] == []
    assert ranking["recommended_defaults"] == ["bureau", "registry", "filers"]
    assert ranking["merge_rules"] == {"defaults": {"sources": ["bureau", "registry", "filers"]}}


def test_a_field_whose_order_differs_gets_its_own_sources_and_ties_are_named(tmp_path):
    # name: a states one value per key, b two; kind: b one value per key, a two; code: a and b equal.
    a = write(tmp_path / "a.jsonl", [{"id": "k1", "name": "N", "kind": "X", "code": "C"},
                                    {"id": "k1", "kind": "Y"}, {"id": "k2", "name": "M", "kind": "Z", "code": "D"}])
    b = write(tmp_path / "b.jsonl", [{"id": "k1", "name": "N", "kind": "X", "code": "C"},
                                    {"id": "k1", "name": "O"}, {"id": "k2", "name": "M", "kind": "Z", "code": "D"}])
    ranking = rs.rank({"a": (a, "id"), "b": (b, "id")},
                      {"name": {"a": "name", "b": "name"}, "kind": {"a": "kind", "b": "kind"},
                       "code": {"a": "code", "b": "code"}})
    assert ranking["fields"]["name"]["recommended"] == ["a", "b"]
    assert ranking["fields"]["kind"]["recommended"] == ["b", "a"]
    assert ranking["fields"]["code"]["tied"] == [["a", "b"]]
    rules = ranking["merge_rules"]
    defaults = rules["defaults"]["sources"]
    assert {f for f, r in ranking["fields"].items() if r["recommended"] != defaults} == set(rules["fields"])
    assert all(rules["fields"][f]["sources"] == ranking["fields"][f]["recommended"] for f in rules["fields"])


def test_a_source_without_the_field_is_left_out_of_it(tmp_path):
    a = write(tmp_path / "a.jsonl", [{"id": "k1", "name": "N", "kind": "X"}])
    b = write(tmp_path / "b.jsonl", [{"id": "k1", "name": "N"}])
    ranking = rs.rank({"a": (a, "id"), "b": (b, "id")}, {"name": {"a": "name", "b": "name"}, "kind": {"a": "kind"}})
    assert set(ranking["fields"]["kind"]["sources"]) == {"a"}
    assert ranking["fields"]["kind"]["agreement"] == []


def test_the_cli_writes_counts_only(tmp_path):
    a = write(tmp_path / "a.jsonl", [{"id": "k1", "name": "Secret Name"}])
    b = write(tmp_path / "b.jsonl", [{"id": "k1", "name": "Secret Name"}])
    out = tmp_path / "out"
    subprocess.run([sys.executable, str(SCRIPTS / "rank_sources.py"), "--source", f"a={a}:id",
                    "--source", f"b={b}:id", "--field", "name=a:name,b:name", "--out", str(out)], check=True)
    text = (out / "ranking.yaml").read_text() + (out / "RANKING.md").read_text()
    assert "Secret" not in text.title() and "SECRET" not in text
    assert yaml.safe_load((out / "ranking.yaml").read_text())["fields"]["name"]["agreement"][0]["agree"] == 1


def test_the_profilers_fingerprint_does_not_cover_it(tmp_path, monkeypatch):
    # The fingerprint reads profile_data.py and profiling/*.py only, so this mode beside them
    # leaves every source's `profiled_with` as it was: a changed copy of it changes nothing.
    before = profile_data.profiler_sha256()
    copy = tmp_path / "scripts"
    import shutil
    shutil.copytree(SCRIPTS, copy, ignore=shutil.ignore_patterns("__pycache__"))
    (copy / "rank_sources.py").write_text("# changed\n", encoding="utf-8")
    monkeypatch.setattr(profile_data, "__file__", str(copy / "profile_data.py"))
    assert profile_data.profiler_sha256() == before
    (copy / "profiling" / "report.py").write_text("# changed\n", encoding="utf-8")
    assert profile_data.profiler_sha256() != before


def test_a_json_array_and_a_number_key_join_with_text_keys(tmp_path):
    array = tmp_path / "a.json"
    array.write_text(json.dumps([{"id": 12, "name": "N"}, {"id": "13", "name": "M"}]), encoding="utf-8")
    lines = write(tmp_path / "b.jsonl", [{"id": "12", "name": "N"}, {"id": 13.0, "name": "M"}])
    ranking = rs.rank({"a": (str(array), "id"), "b": (lines, "id")}, {"name": {"a": "name", "b": "name"}})
    assert ranking["fields"]["name"]["agreement"][0] == {"sources": ["a", "b"], "keys_both": 2, "agree": 2,
                                                          "agreement": 1.0}
