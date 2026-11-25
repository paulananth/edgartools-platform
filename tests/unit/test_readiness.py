"""The readiness gate: a load starts only when the infrastructure passed its checks for this store and this code."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "data-operations" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import readiness  # noqa: E402

ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=ET)


def record(tmp_path, **changes):
    body = {"passed": True, "at": (NOW - timedelta(hours=1)).isoformat(), "generation": "g1", "sha": "abc"}
    body.update(changes)
    (tmp_path / readiness.READY).write_text(json.dumps(body))


def test_the_gate_is_closed_without_a_record(tmp_path):
    assert "run readiness.py" in readiness.gate(tmp_path, "g1", "abc", NOW)


def test_the_gate_opens_for_a_fresh_pass_of_this_store_and_this_code(tmp_path):
    record(tmp_path)
    assert readiness.gate(tmp_path, "g1", "abc", NOW) is None


@pytest.mark.parametrize("change, generation, sha, words", [
    ({"passed": False}, "g1", "abc", "failed"),
    ({}, "g2", "abc", "made again"),
    ({}, "", "abc", "made again"),
    ({}, "g1", "def", "code changed"),
    ({}, "g1", "", "code changed"),
    ({"at": (NOW - timedelta(hours=25)).isoformat()}, "g1", "abc", "a day old"),
])
def test_the_gate_closes_when_the_pass_is_not_for_this_store_this_code_or_this_day(tmp_path, change, generation, sha, words):
    record(tmp_path, **change)
    assert words in readiness.gate(tmp_path, generation, sha, NOW)


def test_an_unreadable_record_closes_the_gate(tmp_path):
    (tmp_path / readiness.READY).write_text("{not json")
    assert "cannot be read" in readiness.gate(tmp_path, "g1", "abc", NOW)


def facts(**changes):
    base = {"git": {"clean": True, "contains_main": True, "ci": "success"}, "engine": {"applicable": True, "built": "h1", "source": "h1"},
            "doctor": True, "loader": {"limit": 300, "settings": {"work_mem": "64MB", "statement_timeout": "4h", "idle_in_transaction_session_timeout": "10min"}},
            "reference": {"codes": 7000, "specs": 20, "silver_tables": 20}, "plan_missing": 0, "loads_running": 0, "loader_sessions": 0,
            "disk_gib": 500, "load1": 1.0, "cores": 8, "audit": [],
            "logins": {"worker.env": "answers", "reader.env": "answers"}, "state": {"verdict": "fresh", "done_steps": 0},
            "registered": {"policies": 1, "datasets": 18, "profiles": 10, "profiles_granted": 10}}
    base.update(changes)
    return base


def failed(facts_):
    return {r["id"] for r in readiness.evaluate(facts_) if not r["ok"]}


def test_ready_infrastructure_passes_every_check():
    assert failed(facts()) == set()


@pytest.mark.parametrize("check, change", [
    ("CODE", {"git": {"clean": False, "contains_main": True, "ci": "success"}}),
    ("CODE", {"git": {"clean": True, "contains_main": False, "ci": "success"}}),
    ("DOCTOR", {"doctor": False}),
    ("GUARDS", {"loader": None}),
    ("GUARDS", {"loader": {"limit": -1, "settings": {"work_mem": "64MB", "statement_timeout": "4h", "idle_in_transaction_session_timeout": "10min"}}}),
    ("GUARDS", {"loader": {"limit": 300, "settings": {"statement_timeout": "4h"}}}),
    ("REFERENCE", {"reference": None}),
    ("REFERENCE", {"reference": {"codes": 0, "specs": 20, "silver_tables": 20}}),
    ("REFERENCE", {"reference": {"codes": 7000, "specs": 20, "silver_tables": 3}}),
    ("CAPTURES", {"plan_missing": 2}),
    ("QUIET", {"loads_running": 1}),
    ("QUIET", {"loader_sessions": 4}),
    ("ROOM", {"disk_gib": 10}),
    ("ROOM", {"load1": 9.0}),
    ("AUDIT", {"audit": ["LOG.postgres"]}),
    ("AUDIT", {"audit": None}),
    # The gate once passed on a freshly initialized store with steps 5 to 7 of the init runbook not run, and every load step
    # then stopped at once ("permission denied for schema mdm").
    ("REGISTERED", {"registered": None}),
    ("REGISTERED", {"registered": {"policies": 0, "datasets": 18, "profiles": 10, "profiles_granted": 10}}),
    ("REGISTERED", {"registered": {"policies": 1, "datasets": 0, "profiles": 10, "profiles_granted": 10}}),
    ("REGISTERED", {"registered": {"policies": 1, "datasets": 18, "profiles": 10, "profiles_granted": 0}}),
])
def test_each_unready_fact_fails_its_own_check(check, change):
    assert check in failed(facts(**change))


def test_readiness_does_not_depend_on_ci_or_engine_provenance():
    assert failed(facts(git={"clean": True, "contains_main": True})) == set()


def test_load_jobs_starts_nothing_until_the_gate_is_open(tmp_path, monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("load_jobs_gate", SCRIPTS / "load_jobs.py")
    chain = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(chain)
    monkeypatch.setattr(chain, "STORES", tmp_path)
    monkeypatch.setattr(chain, "LOGS", tmp_path / "logs")
    monkeypatch.setattr(chain, "subprocess", type("S", (), {"Popen": staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("started"))),
                                                            "run": staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("started")))}))
    monkeypatch.setattr(sys, "argv", ["load_jobs.py", "--auto"])
    (tmp_path / "worker.env").write_text("")
    assert chain.main() == 2
    assert "Not started" in capsys.readouterr().err


def test_the_engine_hash_follows_the_source_and_not_the_file_times(tmp_path):
    crate = tmp_path / "crate"
    (crate / "src").mkdir(parents=True)
    (crate / "src" / "lib.rs").write_text("fn a() {}")
    (crate / "Cargo.toml").write_text("[package]")
    first = readiness.engine_hash(crate)
    import os
    os.utime(crate / "src" / "lib.rs", (1, 1))  # a checkout changes times, not content
    assert readiness.engine_hash(crate) == first
    (crate / "src" / "lib.rs").write_text("fn b() {}")
    assert readiness.engine_hash(crate) != first


def test_the_audit_runs_with_the_readers_login_so_it_can_read_the_database(monkeypatch):
    seen = {}

    def run(command, **kwargs):
        seen.update(kwargs["env"])
        return type("Done", (), {"stdout": json.dumps([{"id": "CST.postgres", "result": "FAIL"}, {"id": "IND.postgres", "result": "PASS"}])})()

    monkeypatch.setattr(readiness.subprocess, "run", run)
    assert readiness.audit_failures({"DATA_URL": "postgresql://invented@h/data"}) == ["CST.postgres"]
    assert seen["DATA_URL"] == "postgresql://invented@h/data"


@pytest.mark.parametrize("change", [
    {"logins": {"worker.env": "answers", "governance.env": "does not answer (OperationalError)"}},
    {"logins": {}},
    {"state": None},
    {"state": {"verdict": "adopted", "done_steps": 59}},
])
def test_a_login_that_fails_or_a_state_file_unread_closes_the_gate(change):
    assert {"LOGINS", "STATE"} & failed(facts(**change))


def test_a_state_file_that_will_be_set_aside_is_shown_and_a_catalog_that_drifted_or_is_down_never_closes_the_gate():
    assert failed(facts(state={"verdict": "set aside", "done_steps": 59})) == set()
    assert failed(facts(catalog="drift")) == set() and "CATALOG" not in readiness.CHECKS


def results(**failing):
    return [{"id": cid, "title": cid, "ok": cid not in failing, "evidence": None} for cid in readiness.CHECKS]


def test_a_run_that_fails_only_because_a_load_runs_leaves_the_passing_record_for_that_code_and_store(tmp_path):
    """Running the gate beside a load fails QUIET; it must not close the gate under the scheduler that is running that load."""
    record(tmp_path)
    previous = json.loads((tmp_path / readiness.READY).read_text())
    assert readiness.next_record(previous, results(QUIET=1), "g1", "abc", NOW) is None
    for failing, generation, sha in (({"QUIET": 1, "CODE": 1}, "g1", "abc"), ({"QUIET": 1}, "g2", "abc"), ({"QUIET": 1}, "g1", "def")):
        written = readiness.next_record(previous, results(**failing), generation, sha, NOW)
        assert written is not None and written["passed"] is False
    assert readiness.next_record(None, results(QUIET=1), "g1", "abc", NOW)["passed"] is False
    assert readiness.next_record(previous, results(), "g1", "abc", NOW)["passed"] is True


def test_a_step_has_a_capture_when_its_folder_holds_receipts_and_the_check_plans_no_load(monkeypatch, tmp_path):
    """A capture is its folder's receipts file: the check looks at each folder and runs no command."""
    import load_jobs
    from tests.support.patching import checked

    good = '{"key": "k", "sha256": "' + "0" * 64 + '"}\n'
    for name, receipts in (("c1", good), ("bad", "not json\n"), ("nosha", '{"key": "k"}\n')):
        (tmp_path / "here" / name).mkdir(parents=True)
        (tmp_path / "here" / name / "receipts.jsonl").write_text(receipts)
    (tmp_path / "here" / "c2").mkdir()  # a capture without its receipts cannot be loaded
    one = {"source": "sec.company", "target": "mastering"}
    steps = [{"name": "a", "capture": "c1", **one}, {"name": "b", "capture": "c2", **one}, {"name": "c", "capture": "c3", **one},
             {"name": "d", "capture": "c1", "capture_root": "proving", **one},
             {"name": "e", "capture": "bad", **one}, {"name": "f", "capture": "nosha", **one},  # receipts a load cannot read
             {"name": "g", "capture": "c1", "source": "sec.company", "target": "undeclared"}]  # a target the source lacks
    checked(monkeypatch, load_jobs, "load_jobs", lambda *a, **k: steps)
    monkeypatch.setattr(load_jobs, "ROOTS", {"captures": tmp_path / "here", "proving": tmp_path / "there"})
    checked(monkeypatch, readiness.subprocess, "run", lambda *a, **k: pytest.fail("a capture check runs no command"))
    assert readiness.plan_missing({}) == 6


def test_an_image_names_the_commit_ci_built_it_from_for_the_gate_and_the_code_check(tmp_path, monkeypatch):
    """A loader image has no git checkout: CI writes the commit it built from into the image, and only builds a commit
    that passed CI on main. The gate and CODE read that commit and run neither git nor gh."""
    (tmp_path / readiness.IMAGE_COMMIT).write_text("abc123\n")

    def no_command(*args, **kwargs):
        raise AssertionError("an image runs no git or gh")
    monkeypatch.setattr(readiness.subprocess, "run", no_command)
    assert readiness.current_sha(tmp_path) == "abc123"
    assert readiness.git_facts(tmp_path) == {"clean": True, "contains_main": True, "image": "abc123"}


def test_a_folder_with_neither_a_checkout_nor_an_image_commit_has_no_commit(tmp_path):
    assert readiness.current_sha(tmp_path) == ""


def test_a_checkout_holding_a_commit_file_is_still_a_checkout(tmp_path):
    """A `COMMIT` file committed or left in a checkout must not stand in for git: only a folder without `.git` is an image."""
    (tmp_path / readiness.IMAGE_COMMIT).write_text("abc123\n")
    (tmp_path / ".git").write_text("gitdir: elsewhere\n")  # a worktree's .git is a file
    assert readiness.image_commit(tmp_path) == ""
