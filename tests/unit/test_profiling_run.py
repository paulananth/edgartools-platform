"""A whole data-profiling run on the synthetic set: classes, links, hierarchies, masking."""

import json
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
    assert sorted(p.name for p in result["out"].iterdir()) == ["REPORT.md", "findings.yaml", "fingerprints.json",
                                                                "invalid_rows.jsonl"]


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


def test_findings_keep_each_columns_distribution_but_never_a_personal_ones(result):
    visit, member = part(result, "visit"), part(result, "member")
    amount = next(c for c in visit["columns"] if c["name"] == "amount")
    assert amount["distribution"]["kind"] == "quantiles" and len(amount["distribution"]["points"]) == 21
    assert amount["distribution"]["points"] == sorted(amount["distribution"]["points"])
    group = next(c for c in member["columns"] if c["name"] == "grp_code")
    shares = group["distribution"]
    assert shares["kind"] == "categories" and abs(sum(shares["shares"].values()) + shares["other"] - 1) < 1e-3
    assert all(c["distribution"] is None for c in member["columns"] if c["sensitivity"] != "none")


def test_compare_reports_a_moved_distribution(result, tmp_path):
    import shutil
    findings = yaml.safe_load((result["out"] / "findings.yaml").read_text())
    findings["approval"]["status"] = "approved"
    approved = tmp_path / "approved.yaml"
    approved.write_text(yaml.safe_dump(findings, sort_keys=False))
    changed = tmp_path / "set"
    shutil.copytree(result["folder"], changed)
    # Every amount tripled; nine members in ten moved to one group.
    lines = (changed / "visit.csv").read_text().splitlines()
    rows = [line.split(",") for line in lines[1:]]
    (changed / "visit.csv").write_text("\n".join([lines[0]] + [",".join(r[:3] + [f"{float(r[3]) * 3:.2f}"]) for r in rows]) + "\n")
    lines = (changed / "member.csv").read_text().splitlines()
    rows = [line.split(",") for line in lines[1:]]
    (changed / "member.csv").write_text("\n".join([lines[0]] + [",".join(r[:4] + ["G01" if n % 10 else r[4]] + r[5:]) for n, r in enumerate(rows)]) + "\n")
    out = tmp_path / "out"
    assert profile_data.main(["compare", "--approved", str(approved), "--input", f"set={changed}", "--out", str(out)]) == 0
    moved = {(d["part"], d["column"]): d for d in yaml.safe_load((out / "drift.yaml").read_text())["drift"]
             if d["drift"] == "distribution_changed"}
    assert "Kolmogorov-Smirnov" in moved[("visit", "amount")]["detail"]
    assert "significant" in moved[("member", "grp_code")]["detail"]
    assert ("visit", "visited_on") not in moved  # unchanged dates do not drift


def test_psi_and_ks_measure_how_far_a_distribution_moved():
    from profiling import drift

    same = {"a": 0.5, "b": 0.5}
    assert drift.psi(same, 0.0, same, 0.0) == 0
    assert drift.psi({"a": 0.9, "b": 0.1}, 0, {"a": 0.1, "b": 0.9}, 0) > drift.PSI_SIGNIFICANT
    assert drift.distribution_drift({"kind": "categories", "shares": {"a": 0.5, "b": 0.5}, "other": 0},
                                    {"kind": "categories", "shares": {"a": 0.52, "b": 0.48}, "other": 0}) is None
    line = [float(i) for i in range(21)]
    assert drift.ks(line, line) == 0
    assert abs(drift.ks(line, [v + 10 for v in line]) - 0.5) < 0.01  # half the values lie beyond the other's top
    assert drift.distribution_drift({"kind": "quantiles", "points": line}, {"kind": "quantiles", "points": [5.0] * 21})
    assert drift.distribution_drift(None, {"kind": "quantiles", "points": line}) is None  # approved before it was kept


def test_a_long_code_list_does_not_drift_when_values_only_swap_out_of_the_listed_top():
    from profiling import drift

    # 1,000 nearly equal values: each side lists a different top 200, the rest in other.
    old = {"kind": "categories", "shares": {f"v{i}": 0.001 for i in range(200)}, "other": 0.8}
    new = {"kind": "categories", "shares": {f"v{i}": 0.001 for i in range(100, 300)}, "other": 0.8}
    assert drift.distribution_drift(old, new) is None
    # A complete list: a value that vanished is a real shift.
    gone = drift.psi({"a": 0.5, "b": 0.5}, 0.0, {"a": 1.0}, 0.0)
    assert gone > drift.PSI_SIGNIFICANT
    assert "measured differently" in drift.distribution_drift(old, {"kind": "quantiles", "points": [0.0] * 21})


def test_ks_is_exact_at_a_jump():
    from profiling import drift

    # Half the values are 0 (a mass point), the rest spread from 0 to 10.
    massed = [0.0] * 11 + [float(i) for i in range(1, 11)]
    spread = [i / 2 for i in range(21)]
    assert abs(drift.ks(massed, spread) - 0.5) < 0.06


def test_a_zoned_time_is_measured_as_its_own_instant(tmp_path):
    import duckdb
    from profiling import profile

    con = duckdb.connect()
    con.execute("SET TimeZone = 'America/New_York'")
    con.execute("CREATE TABLE t AS SELECT TIMESTAMPTZ '2024-01-01 00:00:00+00' + INTERVAL (i) DAY AS at FROM range(30) r(i)")
    column = profile.columns(con, "t")[0]
    assert profile.distribution(con, "t", column, False)["points"][0] == 1704067200.0


def _approved(result, tmp_path):
    import shutil
    findings = yaml.safe_load((result["out"] / "findings.yaml").read_text())
    findings["approval"]["status"] = "approved"
    path = tmp_path / "approved.yaml"
    path.write_text(yaml.safe_dump(findings, sort_keys=False))
    shutil.copy(result["out"] / "fingerprints.json", tmp_path / "fingerprints.json")  # read beside the findings
    return path


def test_two_deliveries_measure_persistence_and_the_delivery_kind(result, tmp_path):
    import shutil

    visit = part(result, "visit")["fingerprint"]
    assert visit["sampled"] == 3000 and visit["prefix"] == "" and "keys" not in visit  # every key, kept beside
    assert len(json.loads((result["out"] / "fingerprints.json").read_text())["visit"]) == 3000
    approved = _approved(result, tmp_path)
    # The same full delivery again: a snapshot.
    out = tmp_path / "same"
    assert profile_data.main(["compare", "--approved", str(approved), "--input", f"set={result['folder']}",
                              "--out", str(out)]) == 0
    same = {m["part"]: m for m in yaml.safe_load((out / "drift.yaml").read_text())["deliveries"]}
    assert same["visit"]["persistence"] == 1.0 and same["visit"]["changed"] == 0.0
    assert same["visit"]["delivery"] == "snapshot"
    again = {p["part"]: p for p in yaml.safe_load((out / "findings.yaml").read_text())["parts"]}["visit"]
    assert again["time"]["delivery"] == "snapshot" and again["record_key"]["evidence"]["persistence"] == 1.0
    # Only the visits that changed, plus new ones: changes only.
    changed = tmp_path / "set"
    shutil.copytree(result["folder"], changed)
    lines = (changed / "visit.csv").read_text().splitlines()
    rows = [line.split(",") for line in lines[1:]]
    kept = [r[:3] + [f"{float(r[3]) + 1:.2f}"] for r in rows[::10]]  # one visit in ten, amount corrected
    fresh = [[str(5000 + n), r[1], r[2], r[3]] for n, r in enumerate(rows[:300])]
    (changed / "visit.csv").write_text("\n".join([lines[0]] + [",".join(r) for r in kept + fresh]) + "\n")
    out = tmp_path / "changes"
    assert profile_data.main(["compare", "--approved", str(approved), "--input", f"set={changed}",
                              "--out", str(out)]) == 0
    visits = {m["part"]: m for m in yaml.safe_load((out / "drift.yaml").read_text())["deliveries"]}["visit"]
    assert visits["persistence"] < 0.5 and visits["changed"] == 1.0 and visits["delivery"] == "changes"


def test_a_key_holding_a_personal_value_is_never_sampled(tmp_path):
    import csv

    folder = tmp_path / "set"
    folder.mkdir()
    with (folder / "people.csv").open("w", newline="") as f:
        csv.writer(f).writerows([["email", "given_name", "city"],
                                 *[[f"person{n}@example.com", f"Ann{n}", f"Town {n % 7}"] for n in range(400)]])
    findings = run.profile_inputs({"set": str(folder)}, "people")
    (people,) = findings["parts"]
    assert people["record_key"]["columns"] == ["email"] and people["fingerprint"] is None


def test_versions_per_key_when_the_key_holds_its_recording_time():
    import duckdb
    from profiling import timing

    con = duckdb.connect()
    con.execute("CREATE TABLE v AS SELECT 'E' || (i % 100) AS entity, TIMESTAMP '2026-01-01' + INTERVAL (i) HOUR AS "
                "updated_at FROM range(300) r(i)")
    assert timing.versions(con, "v", ["entity", "updated_at"], ["updated_at", None]) == {"p50": 3, "p99": 3}
    assert timing.versions(con, "v", ["entity"], ["updated_at", None]) is None


def test_deliveries_sampled_differently_compare_only_the_keys_both_sampled():
    from profiling import drift

    every = {f"{n % 16:x}{n}": "row" for n in range(64)}  # four keys start with each hex digit
    part = lambda prefix, keys: {"part": "p", "time": {"delivery": "unknown"},
                                 "fingerprint": {"prefix": prefix, "keys": keys, "capped": False, "latest": None}}
    small = {"parts": [part("", every)]}
    large = {"parts": [part("0", {k: v for k, v in every.items() if k.startswith("0")})]}
    (m,) = drift.deliveries(small, large)
    assert m["persistence"] == 1.0 and m["delivery"] == "snapshot" and m["keys_sampled"] == 4


def test_a_growing_capped_part_is_still_a_snapshot_and_a_renumbered_key_tells_nothing():
    import duckdb
    from profiling import drift, profile, timing

    con = duckdb.connect()
    con.execute("CREATE TABLE s AS SELECT i AS id, 'v' || i AS k FROM range(200000) r(i)")  # a column named k
    con.execute("CREATE TABLE g AS SELECT i AS id, 'v' || i AS k FROM range(240000) r(i)")
    take = lambda t: {"part": "p", "time": {"delivery": "unknown"}, "fingerprint": timing.fingerprint(
        con, t, ["id"], [c for c in profile.columns(con, t)], None)}
    (m,) = drift.deliveries({"parts": [take("s")]}, {"parts": [take("g")]})
    assert m["persistence"] == 1.0 and m["changed"] == 0.0 and m["delivery"] == "snapshot"
    con.execute("CREATE TABLE r AS SELECT i + 1000000 AS id, 'v' || i AS k FROM range(200000) r(i)")
    (m,) = drift.deliveries({"parts": [take("s")]}, {"parts": [take("r")]})
    assert m["persistence"] == 0.0 and m["delivery"] == "unknown"


def test_a_number_is_hashed_by_its_value():
    import duckdb
    from profiling import profile, timing

    con = duckdb.connect()
    con.execute("CREATE TABLE a AS SELECT CAST(i AS BIGINT) AS id, CAST(i * 2 AS BIGINT) AS n FROM range(50) r(i)")
    con.execute("CREATE TABLE b AS SELECT CAST(i AS DOUBLE) AS id, CAST(i * 2 AS DOUBLE) AS n FROM range(50) r(i)")
    hashes = [timing.fingerprint(con, t, ["id"], profile.columns(con, t), None)["keys"] for t in ("a", "b")]
    assert hashes[0] == hashes[1]


def test_a_part_read_as_a_sample_keeps_no_fingerprint(result):
    findings = run.profile_inputs({"set": str(result["folder"])}, "small limit", limit=1000, sample=500)
    sampled = [p for p in findings["parts"] if p["scan"] == "sampled"]
    assert sampled and all(p["fingerprint"] is None for p in sampled)


def test_a_working_copy_the_run_made_itself_is_removed(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path / "temp"))
    (tmp_path / "temp").mkdir()
    folder = build(tmp_path / "set")
    assert run.profile_inputs({"set": str(folder)}, "fixture")["dataset"]["name"] == "fixture"
    assert not list((tmp_path / "temp").iterdir())
