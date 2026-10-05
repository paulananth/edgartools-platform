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


def test_no_working_copy_outlives_the_run(result):
    assert not (result["out"] / ".work").exists()
    assert sorted(p.name for p in result["out"].iterdir()) == ["REPORT.md", "findings.yaml"]


def test_inputs_carry_rows_and_sha256_and_silver_integers_are_wide(result):
    inputs_found = result["findings"]["dataset"]["inputs"]
    assert all(i["sha256"] and len(i["sha256"]) == 64 for i in inputs_found)
    assert {i["rows"] for i in inputs_found} >= {300}
    visit = part(result, "visit")
    assert {c["name"]: c["type"] for c in visit["silver"]["columns"]}["visit_id"] == "BIGINT"
    assert result["findings"]["dataset"]["profiled_at"][-6:] in {"-04:00", "-05:00"}


def test_large_table_file_is_sampled_and_its_key_confirmed_in_full(tmp_path):
    (tmp_path / "big.csv").write_text("ref,grp\n" + "".join(f"R{i:06d},{i % 7}\n" for i in range(5000)))
    found = run.profile_inputs({"big": str(tmp_path / "big.csv")}, "big", limit=1000, sample=300, seed=3,
                               work=tmp_path / "w")
    big = found["parts"][0]
    assert big["scan"] == "sampled" and big["rows"] == 300
    assert big["record_key"]["columns"] == ["ref"]
    assert big["record_key"]["evidence"]["full_pass"]["ref"] == {
        "rows": 5000, "null_rows": 0, "distinct": 5000, "unique": True, "scan": "full"}


def test_contact_details_are_personal_in_any_part():
    from profiling import sensitivity
    assert sensitivity.tag("support_email", ["a@b.co"], False)["sensitivity"] == "personal"
    assert sensitivity.tag("contact", ["a@b.co", "c@d.org"], False)["sensitivity"] == "personal"
    assert sensitivity.tag("street", ["1 Main"], False)["sensitivity"] == "none"


def test_a_stopped_run_removes_its_working_copy(tmp_path):
    import os
    import signal
    import subprocess
    import time
    big = tmp_path / "big.jsonl"
    big.write_text("\n".join('{"k": %d}' % i for i in range(400_000)))
    scripts = Path(__file__).resolve().parents[2] / "skills" / "data-profiling" / "scripts"
    env = {**os.environ, "TMPDIR": str(tmp_path / "t")}
    (tmp_path / "t").mkdir()
    run_ = subprocess.Popen([sys.executable, "profile_data.py", "run", "--name", "x", "--input", f"b={big}",
                             "--out", str(tmp_path / "o")], cwd=scripts, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 30
    while not list((tmp_path / "t").glob("profiling-*")) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert list((tmp_path / "t").glob("profiling-*")), "the run never started"
    run_.send_signal(signal.SIGTERM)
    run_.wait(timeout=60)
    assert run_.returncode != 0, "the run finished before the signal: nothing was tested"
    assert not list((tmp_path / "t").glob("profiling-*"))


def test_link_part_ends_put_the_keyed_end_first_whatever_the_link_order():
    ends = [{"from": {"columns": ["to_id"]}}, {"from": {"columns": ["from_id"]}}]
    assert run._child_first(ends, ["from_id", "kind"]) == ("from_id", "to_id")
    assert run._child_first(list(reversed(ends)), ["from_id", "kind"]) == ("from_id", "to_id")
    assert run._child_first(ends, ["kind"]) == ("to_id", "from_id")
