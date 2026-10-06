"""Name matching evidence (profiling ticket 07b): which name parts tell entities
apart, which are variants of one entity, and which attributes support a match."""

import json
import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")  # in the mdm extra, which CI installs

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "data-profiling" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import match_names  # noqa: E402
from profiling import name_matching as nm  # noqa: E402

DISTINCT = [
    ("1", "Alpha Growth Fund Class A"), ("2", "Alpha Growth Fund Class C"),
    ("3", "Beta Income Fund Class A"), ("4", "Beta Income Fund Class C"),
    ("5", "Gamma Holdings Inc"), ("6", "Gamma Holdings LLC"),
    ("7", "Delta Partners Inc"), ("8", "Delta Partners LLC"),
    ("9", "Epsilon Trust II"), ("10", "Epsilon Trust III"),
]


def test_tokens_fold_case_and_split_on_punctuation():
    assert nm.tokens("ACME, Inc./DE") == ["acme", "inc", "de"]
    assert [nm.token_class(t) for t in ("a", "12", "iii", "fund")] == ["letter", "number", "roman", "word"]


def test_names_one_token_apart_with_different_keys_tell_entities_apart():
    found = nm.distinguishing(duckdb.connect(), DISTINCT)
    assert found.counts[("a", "c")] == 2 and found.counts[("inc", "llc")] == 2
    assert found.counts[("ii", "iii")] == 1
    assert found.examples[("a", "c")][0]["context"] == "class"
    classes = {(tuple(r["classes"]), r["after"]) for r in nm.by_class(found)}
    assert (("letter", "letter"), "class") in classes


def test_one_key_never_distinguishes_from_itself():
    found = nm.distinguishing(duckdb.connect(), [("1", "Alpha Fund Class A"), ("1", "Alpha Fund Class C")])
    assert not found.counts


def test_variants_of_one_entity_and_renames_kept_apart():
    pairs = [("Zeta Corp", "Zeta Corporation"), ("Eta Corp", "Eta Corporation"),
             ("Theta Systems Inc", "Theta Systems"), ("Iota Systems Inc", "Iota Systems"),
             ("Inhale Therapeutic Systems", "Nektar Therapeutics"),  # a rename
             ("Gamma Holdings Inc", "Gamma Holdings LLC")]  # a conversion: one entity
    alike = nm.variants(pairs)
    assert alike.counts[("corp", "corporation")] == 2 and alike.counts[("", "inc")] == 2
    assert ("inhale", "nektar") not in alike.counts
    clash = nm.conflicts(nm.distinguishing(duckdb.connect(), DISTINCT), alike)
    assert [c["pair"] for c in clash] == [["inc", "llc"]]


def test_attributes_agree_when_folded_or_one_is_the_start_of_the_other():
    assert nm.agree("60191-1234", "60191") and nm.agree("DE", "US-DE") and nm.agree("New York", "NEW YORK")
    assert nm.agree("DE", "NY") is False and nm.agree(None, "x") is None
    same = [({"zip": "10001"}, {"postal": "10001-2"}), ({"zip": "20002"}, {"postal": "20002"})]
    near = [({"zip": "10001"}, {"postal": "94105"})]
    (row,) = nm.support(same, near, [("zip", "postal")])
    assert row["agrees_on_same"] == 1.0 and row["separates_near_homonyms"] == 1.0


def test_homonym_rate_counts_folded_names_held_twice():
    risk = nm.homonyms([("1", "Acme Inc"), ("2", "ACME, INC."), ("3", "Other Co")])
    assert risk["held_by_more_than_one"] == 1 and risk["rate"] == 0.5


def write(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return str(path)


def test_the_command_writes_evidence_and_masks_personal_names(tmp_path):
    left = write(tmp_path / "left.jsonl", [
        {"id": k, "name": n, "zip": "1000" + k[-1], "ref": f"R{k}", "old": []} for k, n in DISTINCT] + [
        {"id": "11", "name": "Zeta Corp", "zip": "20002", "ref": "R11", "old": ["Zeta Corporation"]}])
    right = write(tmp_path / "right.jsonl", [
        {"lei": "L1", "legal": "Alpha Growth Fund Class A", "postal": "10001", "ref": "R1", "other": [["PREVIOUS", "Alpha Growth Fund A"]]},
        {"lei": "L11", "legal": "Zeta Corporation", "postal": "20002", "ref": "R11", "other": []}])
    out = tmp_path / "out"
    args = ["--left", left, "--left-key", "id", "--left-name", "name", "--left-variants", "old",
            "--right", right, "--right-key", "lei", "--right-name", "legal", "--right-variants", "other",
            "--same", "ref=ref", "--attribute", "zip=postal", "--out", str(out)]
    assert match_names.main(args) == 0
    found = json.loads(json.dumps(__import__("yaml").safe_load((out / "name-matching.yaml").read_text())))
    assert found["proved_pairs"] == 2 and found["supporting_attributes"][0]["agrees_on_same"] == 1.0
    assert {tuple(r["pair"]) for r in found["distinguishing"]} >= {("a", "c"), ("inc", "llc")}
    assert "Compare exactly" in (out / "NAME-MATCHING.md").read_text()
    assert match_names.main([*args, "--personal", "--out", str(tmp_path / "masked")]) == 0
    masked = (tmp_path / "masked" / "name-matching.yaml").read_text()
    assert "Alpha" not in masked and "Aaaaa" in masked


def test_an_id_from_the_name_folds_variants_and_keeps_what_tells_entities_apart():
    apart = nm.distinguishing(duckdb.connect(), DISTINCT)
    alike = nm.variants([("Zeta Corp", "Zeta Corporation"), ("Eta Corp", "Eta Corporation"),
                         ("Gamma Holdings Inc", "Gamma Holdings LLC"), ("Delta Partners Inc", "Delta Partners LLC")])
    rules = nm.folds(alike, apart)
    assert ("corp", "corporation") in rules and not any("llc" in f for f, _ in rules)
    assert nm.name_key("ZETA CORP.", rules) == nm.name_key("Zeta Corporation", rules)
    assert nm.name_key("Alpha Growth Fund Class A", rules) != nm.name_key("Alpha Growth Fund Class C", rules)
    joined = nm.join_by_name([("1", "Zeta Corp"), ("2", "Twin Co"), ("3", "Twin Co")],
                             [("A", "Zeta Corporation"), ("B", "Twin Co")], rules)
    assert joined["joined"] == {"zeta corporation": ("1", "A")} and joined["ambiguous"] == ["twin co"]


def test_the_profiling_name_id_is_the_engines_cross_reference_format():
    from edgar_warehouse.mdm.clean.adapters import FORMATS, UnsupportedRecord

    for name in ("ACME, Inc./DE", "Alpha Growth Fund Class A", "Straße  Holdings", "ＡＣＭＥ widgets"):
        assert FORMATS["name_id@1"](name) == nm.name_id(name)
    assert FORMATS["name_id@1"]("Fund Class A") != FORMATS["name_id@1"]("Fund Class C")
    assert FORMATS["name_id@1"]("acme inc") == FORMATS["name_id@1"]("ACME, INC.")
    with pytest.raises(UnsupportedRecord):
        FORMATS["name_id@1"](" ,. ")


def test_a_dropped_token_that_tells_entities_apart_is_never_folded():
    apart = nm.distinguishing(duckdb.connect(), [("1", "Kappa Holdings"), ("2", "Kappa Holdings Inc"),
                                                 ("3", "Lambda Group"), ("4", "Lambda Group Inc")])
    assert apart.counts[("", "inc")] == 2
    alike = nm.variants([("Mu Corp", "Mu Corp Inc"), ("Nu Corp", "Nu Corp Inc")])
    assert ("", "inc") in alike.counts and ("inc", "") not in nm.folds(alike, apart)


def test_personal_masking_covers_every_name_part():
    found = {"variants_not_folded": [["jon", "john"]], "after": "smith", "count": 2}
    masked = match_names._masked(found, True)
    assert "john" not in json.dumps(masked) and "smith" not in json.dumps(masked) and masked["count"] == 2


def test_a_path_with_a_quote_reads(tmp_path):
    path = write(tmp_path / "o'neil.jsonl", [{"id": "1", "name": "Omicron Ltd"}])
    rows = list(match_names._rows(duckdb.connect(), path, ["id", "name"]))
    assert rows == [{"id": "1", "name": "Omicron Ltd"}]
