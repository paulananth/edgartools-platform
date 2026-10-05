"""A name as the only unique column: a designed durable key, never a found one."""

import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")  # in the mdm extra, which CI installs

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "data-profiling" / "scripts"))
from profiling import names, run  # noqa: E402


def test_normalization_folds_case_width_and_spaces():
    assert names.name_norm("  ＡＣＭＥ   Widgets\tGmbH ") == "acme widgets gmbh"
    assert names.name_norm("Straße") == names.name_norm("STRASSE")
    assert names.name_hash("p", "Acme  Widgets") == names.name_hash("p", "acme widgets")
    assert names.name_hash("p", "Acme") != names.name_hash("q", "Acme")


def test_a_unique_name_gives_a_durable_designed_key_never_a_found_one(tmp_path):
    (tmp_path / "things.csv").write_text("label,weight\n" + "".join(
        f"Long Thing Number {i} Deluxe,{i % 5}\n" for i in range(60)))
    found = run.profile_inputs({"things": str(tmp_path / "things.csv")}, "t", work=tmp_path / "w")
    key = found["parts"][0]["record_key"]
    assert key["found"] is False and key["design"] == "surrogate" and key["basis"] == ["label"]
    assert "alias" in key["rule"] and "Unicode" in key["rule"]
    assert key["evidence"]["unique_after_normalization"] and key["evidence"]["provisional"]


def test_names_that_fold_together_are_not_a_basis(tmp_path):
    rows = [f"Long Thing Number {i} Deluxe" for i in range(60)] + ["LONG THING NUMBER 1 DELUXE"]
    (tmp_path / "things.csv").write_text("label,weight\n" + "".join(f"{r},{i % 5}\n" for i, r in enumerate(rows)))
    found = run.profile_inputs({"things": str(tmp_path / "things.csv")}, "t", work=tmp_path / "w")
    key = found["parts"][0]["record_key"]
    assert key["found"] is False and "basis" not in key
