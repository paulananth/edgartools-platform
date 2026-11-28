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
            "registered": {"policies": 1, "datasets": 18, "profiles": 10, "profiles_granted": 10}, "mirror": "exact"}
    base.update(changes)
    return base


def failed(facts_):
    return {r["id"] for r in readiness.evaluate(facts_) if not r["ok"]}


def test_ready_infrastructure_passes_every_check():
    assert failed(facts()) == set()
def test_readiness_publishes_check_progress_for_a_run_id(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    from edgar_warehouse.hosted_store_clear_progress import snapshot, start_run

    stores = tmp_path / "stores"
    run_id = start_run(stores_folder=stores)
    monkeypatch.setattr(readiness, "gather", lambda _stores: facts())
    monkeypatch.setattr(readiness, "current_sha", lambda: "abc")
    monkeypatch.setitem(
        sys.modules,
        "load_jobs",
        SimpleNamespace(
            load_env=lambda _path: {},
            data_url=lambda _env: "dsn",
            database_generation=lambda _url: "g1",
        ),
    )

    assert readiness.main([
        "--stores", str(stores), "--progress-run-id", run_id, "--progress-step", "preflight",
    ]) == 0
    progress = snapshot(run_id, stores)
    assert progress["steps"]["preflight"]["state"] == "complete"
    assert progress["steps"]["preflight"]["completed"] == len(readiness.CHECKS)



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
    steps = [{**step, "deliveries": [{name: step[name] for name in ("capture", "capture_root") if name in step}]} for step in steps]
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


def test_a_duty_login_is_tried_on_each_database_by_its_own_url_and_a_missing_url_keeps_the_gate_shut(tmp_path, monkeypatch):
    """A worker file without the config database's URL would pass a check that derives every database from DATA_URL, and its
    load would then stop at the first Rules call."""
    import psycopg2

    from tests.support.patching import checked

    def duty(login, databases):
        return "".join(f"export {variable}='postgresql://{login}:invented@h.invalid:5432/{database}'\n"
                       for variable, database in databases)

    every = (("DATA_URL", "data"), ("CONTROL_URL", "control"), ("CONFIG_URL", "config"))
    (tmp_path / "owner.env").write_text(duty("admin", every))
    (tmp_path / "worker.env").write_text(duty("edgar_loader", every[:2]))
    (tmp_path / "governance.env").write_text(duty("governance", every))
    (tmp_path / "reader.env").write_text(duty("ops_reader", every))
    tried = []

    class Connection:
        def close(self):
            pass

    def connect(*args, **kwargs):
        tried.append(args[0].rsplit("@", 1)[1])
        return Connection()

    checked(monkeypatch, psycopg2, "connect", connect)
    found = readiness.login_facts(tmp_path)
    assert found["worker.env"] == "unreadable (KeyError)"
    assert found["governance.env"] == found["reader.env"] == found["owner.env"] == "answers"
    assert tried.count("h.invalid:5432/config") == 2 and "h.invalid:5432/postgres" in tried


@pytest.mark.parametrize("fact", ["missing: silver.adv_custody", "not replicating: mdm.mastering_master (SNAPSHOTTING)",
                                  "unreadable (the mirror operator could not list the mirror)"])
def test_a_load_waits_for_the_mirror_that_init_makes(fact):
    assert failed(facts(mirror=fact)) == {"MIRRORED"}


def test_the_mirror_is_exact_only_when_its_listing_is_the_record_every_table_replicating():
    import sys
    sys.path.insert(0, str(Path(readiness.REPO) / "skills" / "data-platform" / "scripts" / "exposure"))
    import mirror_sql
    record = mirror_sql.tables(mirror_sql.load(mirror_sql.MANAGED), mirror_sql.load(mirror_sql.EXPOSURE))
    rows = [{"SOURCE_SCHEMA_NAME": t.split(".")[0], "SOURCE_TABLE_NAME": t.split(".")[1], "STATE": "REPLICATING"} for t in record]
    assert readiness.mirror_fact(lambda sql: rows) == "exact"
    assert readiness.mirror_fact(lambda sql: rows[1:]).startswith("missing:")
    assert "not replicating" in readiness.mirror_fact(lambda sql: [{**rows[0], "STATE": "SNAPSHOTTING"}, *rows[1:]])
    assert readiness.mirror_fact(lambda sql: None).startswith("unreadable")
    assert readiness.mirror_fact(lambda sql: {"error": "invented"}).startswith("unreadable")


def readiness_mirror_tables():
    sys.path.insert(0, str(Path(readiness.REPO) / "skills" / "data-platform" / "scripts" / "exposure"))
    import mirror_sql
    return mirror_sql.tables(mirror_sql.load(mirror_sql.MANAGED), mirror_sql.load(mirror_sql.EXPOSURE))


def operator_file(tmp_path):
    secret_file = tmp_path / "mirror-operator.env"
    secret_file.write_text("\n".join(f"export MIRROR_SNOWFLAKE_{k}=invented-{k.lower()}" for k in ("ACCOUNT", "USER", "PRIVATE_KEY_PATH", "ROLE", "WAREHOUSE")))
    return secret_file


def test_a_failed_listing_keeps_none_of_its_error_text(monkeypatch, tmp_path):
    import snowflake.connector
    from tests.support.patching import checked
    monkeypatch.setattr(readiness, "MIRROR_OPERATOR", operator_file(tmp_path))

    def refused(*_, **__):
        raise snowflake.connector.errors.DatabaseError("account invented-account not found")
    checked(monkeypatch, snowflake.connector, "connect", refused)
    with pytest.raises(readiness.SnowflakeRefused):
        readiness.run_as_mirror_operator("CALL x();")
    assert "invented" not in readiness.mirror_fact()


def test_a_refused_listing_names_snowflakes_error_number_and_nothing_of_its_text(monkeypatch, tmp_path):
    import snowflake.connector
    from tests.support.patching import checked
    monkeypatch.setattr(readiness, "MIRROR_OPERATOR", operator_file(tmp_path))

    def over_quota(*_, **__):
        raise snowflake.connector.errors.ProgrammingError("invented-account: warehouse refused", errno=90073)
    checked(monkeypatch, snowflake.connector, "connect", over_quota)
    assert readiness.mirror_fact() == "unreadable (Snowflake error 090073)"


def test_the_listing_is_read_as_the_mirror_operator_in_a_loader_image_that_has_no_snowflake_command(monkeypatch, tmp_path):
    import snowflake.connector
    from tests.support.patching import checked
    monkeypatch.setattr(readiness, "MIRROR_OPERATOR", operator_file(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path))
    record = sorted(readiness_mirror_tables())
    rows = [{"SOURCE_SCHEMA_NAME": t.split(".")[0], "SOURCE_TABLE_NAME": t.split(".")[1], "STATE": "REPLICATING"} for t in record]
    logins, statements = [], []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def cursor(self, kind):
            assert kind is snowflake.connector.DictCursor
            return type("Cursor", (), {"execute": lambda cursor, sql: statements.append(sql) or cursor, "fetchall": lambda cursor: rows})()
    checked(monkeypatch, snowflake.connector, "connect", lambda **login: logins.append(login) or Connection())
    assert readiness.mirror_fact() == "exact"
    assert [{k: v for k, v in login.items() if k in ("user", "authenticator", "private_key_file", "role")} for login in logins] == [
        {"user": "invented-user", "authenticator": "SNOWFLAKE_JWT", "private_key_file": "invented-private_key_path", "role": "invented-role"}]
    assert statements and not statements[0].endswith(";")
