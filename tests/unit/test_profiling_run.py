"""A whole data-profiling run on the synthetic set: classes, links, hierarchies, masking."""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "data-profiling" / "scripts"))
from profiling import report, run  # noqa: E402
from tests.unit.profiling_fixture import build  # noqa: E402

import profile_data  # noqa: E402


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    base = tmp_path_factory.mktemp("run")
    folder = build(base / "set")
    out = base / "out"
    assert profile_data.main(["run", "--name", "fixture", "--input", f"set={folder}", "--out", str(out)]) == 0
    return {"findings": yaml.safe_load((out / "findings.yaml").read_text()), "report": (out / "REPORT.md").read_text(),
            "folder": folder, "out": out}


def part(result, name):
    return next(p for p in result["findings"]["parts"] if p["part"] == name)


@pytest.mark.parametrize("name, cls", [("member", "master"), ("item", "master"), ("grp", "reference"),
                                       ("visit", "transaction"), ("line", "transaction"), ("pairing", "relationship")])
def test_each_part_gets_its_class_with_evidence(result, name, cls):
    p = part(result, name)
    assert p["class"] == cls and p["confidence"] >= 0.6
    assert all({"test", "value", "passed"} <= set(t) for t in p["tests"])


def test_hierarchies_by_parent_column_and_code_nesting(result):
    kinds = {(h["part"], h["evidence_kind"], h["type"]) for h in result["findings"]["hierarchies"]}
    assert ("grp", "parent_column", "reference") in kinds
    assert ("item", "code_nesting", "reference") in kinds


def test_relationship_part_onboards_with_its_master(result):
    rels = {(r["from"]["part"], r["from"]["columns"][0]): r for r in result["findings"]["relationships"]}
    assert rels[("pairing", "member_a")]["onboard"] == "together"
    assert rels[("pairing", "member_a")]["role_column"] == "role"
    assert rels[("visit", "member_id")]["onboard"] == "separate"


def test_personal_values_never_reach_the_outputs(result):
    member = part(result, "member")
    tagged = {c["name"] for c in member["columns"] if c["sensitivity"] != "none"}
    assert {"given_name", "surname", "birth_date", "street_address"} <= tagged
    raw = {line.split(",")[1] for line in (result["folder"] / "member.csv").read_text().splitlines()[1:]}
    text = (result["out"] / "findings.yaml").read_text() + result["report"]
    assert not [name for name in raw if f" {name}" in text or f"'{name}'" in text]
    assert not any(c["sensitivity"] != "none" for p in result["findings"]["parts"] if p["part"] != "member"
                   for c in p["columns"])


def test_silver_spec_for_transactions_and_new_kind_questions(result):
    visit = part(result, "visit")
    assert visit["silver"]["key"] == ["visit_id"] and visit["silver"]["load_mode"] == "append"
    assert visit["silver"]["links"][0]["mdm_id_column"] == "member_id_mdm_id"
    assert part(result, "member")["silver"] is None
    asked = [q["about"] for q in result["findings"]["questions"]]
    assert "member" in asked and result["findings"]["approval"]["status"] == "draft"


def test_approve_records_exact_words(result):
    path = result["out"] / "findings.yaml"
    profile_data.main(["approve", "--findings", str(path), "--by", "operator", "--words", "approved as shown"])
    approval = yaml.safe_load(path.read_text())["approval"]
    assert approval["status"] == "approved" and approval["approved_words"] == "approved as shown"


def test_report_names_every_part_and_says_advice_only(result):
    for name in ("member", "item", "grp", "visit", "line", "pairing"):
        assert f"| {name} |" in result["report"]
    assert "advice only" in result["report"]


def test_compare_lists_drift_against_approved_findings(result, tmp_path):
    import shutil
    approved = result["out"] / "findings.yaml"
    findings = yaml.safe_load(approved.read_text())
    findings["approval"]["status"] = "approved"
    approved_copy = tmp_path / "approved.yaml"
    approved_copy.write_text(yaml.safe_dump(findings, sort_keys=False))
    changed = tmp_path / "set"
    shutil.copytree(result["folder"], changed)
    lines = (changed / "visit.csv").read_text().splitlines()
    lines = [lines[0] + ",channel"] + [line.replace(",", ",9", 1) + ",web" for line in lines[1:]]
    (changed / "visit.csv").write_text("\n".join(lines) + "\n")
    out = tmp_path / "out"
    assert profile_data.main(["compare", "--approved", str(approved_copy), "--input", f"set={changed}",
                              "--out", str(out)]) == 0
    drift = yaml.safe_load((out / "drift.yaml").read_text())["drift"]
    kinds = {(d["drift"], d["part"]) for d in drift}
    assert ("column_new", "visit") in kinds
    assert ("link_broken", "visit") in kinds or ("link_weaker", "visit") in kinds
    assert all(d["handled_by"] in {"data-quality", "refining-rules", "rdm"} for d in drift)


def test_compare_refuses_findings_that_are_not_approved(result, tmp_path):
    draft = yaml.safe_load((result["out"] / "findings.yaml").read_text())
    draft["approval"]["status"] = "draft"
    path = tmp_path / "draft.yaml"
    path.write_text(yaml.safe_dump(draft))
    with pytest.raises(SystemExit, match="not approved"):
        profile_data.main(["compare", "--approved", str(path), "--input", f"set={result['folder']}",
                           "--out", str(tmp_path / "o")])
