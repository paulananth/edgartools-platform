"""Issue 20 slice 20d: the installed empty-store Person proof on the `mastering` target.

L5's 1,000 pinned filers (`.planning/workstreams/object-records/qualification.json`,
capture `all-76230`) in two bundles of 500, each a run of SEC Person's
`mastering` target (read, records, merge) whose manifest the installed
`mdm prepare-capture` writes. Workers and verifiers run from the installed
bundle under their own logins; the checkout only provisions.

Expected, from the in-process outcomes under today's rules (386 assertions,
447 classification_entity_undetermined, 167 classification_deferred): 386
Person records staged and bound by the CIK rule, 447 + 167 open reviews; a
merge worker killed while it holds its unit and finished on a later attempt;
a second pass (each bundle's verified records merged again under new batch ids
and consumers) changing nothing.

    PG16_SERVER=pgserver PERSON_PROOF_OUT=<report.json> PATH="$HOME/.cargo/bin:$PATH" \\
      uv run --extra mdm --with pgserver pytest -q -s -p no:randomly \\
      .scratch/mastering-to-done/proof/installed_person_proof.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import create_engine, text

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.database import grant_profile
from edgar_warehouse.bookkeeping.clean.destinations import migrate_guard
from edgar_warehouse.mdm.clean.store import migrate, register_policy
from edgar_warehouse.rules import files
from tests.engine.test_data_skill_bundle_postgres import _run, _stores, installed  # noqa: F401
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401
from tests.support.rules_approval import approve
from tests.support.rules_authority import register_dataset

_HERE = Path(__file__).resolve()
_SPEC = importlib.util.spec_from_file_location("company_proof", _HERE.with_name("installed_mastering_proof.py"))
company = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(company)  # the 2026-10-10 helpers (counts, bindings) and the kill-and-recover step
old = company.old

WORK = Path(os.environ.get("PERSON_PROOF_WORK", "~/.local/share/edgartools/clean-mdm/proving/person-1000")).expanduser()
SOURCE, PERSON = "sec.submissions.person", "sec.submissions.person.v1"
AS_OF, CAPTURE_RUN = "2026-09-29T15:00:00+00:00", "local-cm27-all-76230"
EXPECTED = {
    "companies_open": 0,
    "stage_records": {f"{PERSON}:person": 386},
    "stage_bound": {PERSON: 386},
    "open_reviews": {"classification_entity_undetermined": 447, "classification_deferred": 167},
}

MASTERING = files.source(SOURCE)["bookkeeping"]["targets"]["mastering"]["steps"]
PIPELINE = {"pipeline": "installed-person-proof", "bookkeeping": {"version": 1, "targets": {
    "person": old.TARGET(MASTERING),
    "person-replay": old.TARGET([{**next(s for s in MASTERING if s["name"] == "merge"), "requires": []}])}}}


def test_installed_person_mastering(installed, databases, tmp_path):  # noqa: F811
    python, root = installed
    store = Artifacts()
    out = Path(os.environ["PERSON_PROOF_OUT"])
    names = sorted(p.name.removeprefix("documents-").removesuffix(".json") for p in WORK.glob("documents-*.json"))
    started = time.monotonic()
    minutes = lambda: round((time.monotonic() - started) / 60, 1)  # noqa: E731

    for profile in ("source.read", "mdm.prepare", "mdm.merge", "journal.record"):
        grant_profile(databases.admin, profile=profile, worker="bk_runtime", verifier="bk_verifier")
    with databases.admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql("CREATE DATABASE mdm_proof")
    mdm_admin = create_engine(databases.admin.url.set(database="mdm_proof"))
    mdm_app = create_engine(mdm_admin.url.set(username="clean_application", password="test"))
    migrate(mdm_admin, application_role="clean_application")
    migrate_guard(mdm_admin, runtime_role="clean_application")
    with mdm_admin.begin() as conn:
        policy = register_policy(conn, files.policy())
        register_dataset(conn, PERSON, "1", files.mdm_contract(SOURCE, PERSON))
        conn.exec_driver_sql("GRANT USAGE ON SCHEMA mdm TO bk_verifier")
        conn.exec_driver_sql("GRANT SELECT ON ALL TABLES IN SCHEMA mdm TO bk_verifier")
    mdm_reader = create_engine(mdm_admin.url.set(username="bk_verifier", password="test"))
    old.say(stage="provisioned", policy=policy, bundles=names)

    url = lambda engine: engine.url.render_as_string(hide_password=False)  # noqa: E731
    env = {**_stores(databases), "BOOKKEEPING_MANIFEST_ROOT": (tmp_path / "control").as_uri()}
    worker = {**env, "MDM_DATABASE_URL": url(mdm_app), "MDM_APPLICATION_ROLE": "clean_application"}
    verifier = {**env, "BOOKKEEPING_DATABASE_URL": url(databases.verifier), "MDM_DATABASE_URL": url(mdm_reader)}
    entry = ("-c", "import sys; from edgar_warehouse.cli import main; sys.exit(main(sys.argv[1:]))")

    def cli(*args, env=env):
        done = _run(python, "-m", "edgar_warehouse.cli", *args, env=env, cwd=root)
        assert done.returncode == 0, done.stderr[-4000:]
        return done.stdout

    def prepare(name: str, folder: str = "first", *extra: str) -> dict:
        report = json.loads(cli(
            "mdm", "prepare-capture", "--source", SOURCE, "--capture", str(company.CAPTURE),
            "--documents", str(WORK / f"documents-{name}.json"), "--capture-run", CAPTURE_RUN,
            "--output", str(tmp_path / folder / name), "--as-of", AS_OF, "--revision", "0", *extra))
        assert report["policy_digest"] == policy, (report["policy_digest"], policy)
        return report

    reports = {name: prepare(name) for name in names}
    # A fresh journal: every document is new. A journal that already holds them names none.
    assert all(r["manifest"] for r in reports.values()), "the journal already holds these documents: use --all"
    saved = databases.rules.save("pipeline", PIPELINE["pipeline"], "1", PIPELINE)
    databases.rules.prove("pipeline", PIPELINE["pipeline"], "1",
                          {"digest": saved["digest"], "batch_hash": reports[names[0]]["manifest"]["sha256"],
                           "passed": True})
    approve(databases.approver, "pipeline", PIPELINE["pipeline"], "1")
    databases.rules.activate("pipeline", PIPELINE["pipeline"], "1")

    def submit(target: str, manifest: dict) -> str:
        return json.loads(cli("rules", "run", "--pipeline", PIPELINE["pipeline"], "--target", target,
                              "--input-manifest", manifest["uri"], "--input-sha256", manifest["sha256"]))["run"]["run_id"]

    def items(run_id: str) -> list[dict]:
        return json.loads(cli("bookkeeping", "status", run_id))["items"]

    def drive(run_id: str, profiles: tuple[str, ...], steps: set[str] | None = None) -> None:
        deadline = time.monotonic() + 3600
        while True:
            for profile in profiles:
                cli("workers", "work", profile, run_id, "--limit", company.LIMIT, env=worker)
                cli("workers", "verify", profile, run_id, "--reports", (tmp_path / "reports").as_uri(),
                    "--limit", company.LIMIT, env=verifier)
            mine = [i for i in items(run_id) if steps is None or i["step"] in steps]
            if mine and all(i["state"] == "verified" for i in mine):
                return
            assert time.monotonic() < deadline, [i for i in mine if i["state"] != "verified"][:3]
            time.sleep(2)

    def finalize(run_id: str) -> None:
        cli("bookkeeping", "finalize", run_id)
        assert json.loads(cli("bookkeeping", "status", run_id))["run"]["state"] == "complete"

    def snapshot() -> tuple[dict, str]:
        with mdm_reader.connect() as conn:
            return old.counts(conn), old.bindings(conn)

    def writes() -> dict:
        """Rows each MDM table holds: what a pass wrote."""
        with mdm_reader.connect() as conn:
            return {t: conn.execute(text(f"SELECT count(*) FROM mdm.{t}")).scalar() for t in (
                "batch", "source_reading", "decision", "current_record", "outbox", "checkpoint", "set_aside_record")}

    runs = {name: submit("person", reports[name]["manifest"]) for name in names}

    def prepared(name: str) -> str:
        drive(runs[name], ("source.read", "mdm.prepare"), {"read", "records"})
        old.say(bundle=name, prepared=True, minutes=minutes())
        return name

    recovery: dict = {}
    with ThreadPoolExecutor(2) as pool:
        for name in pool.map(prepared, names):
            if not recovery:
                recovery = company.kill_and_recover(python, entry, worker, root, runs[name], items, snapshot)
            drive(runs[name], ("mdm.merge", "journal.record"))
            finalize(runs[name])
            old.say(bundle=name, merged=True, minutes=minutes())
    resumed = next(i for i in items(runs[names[0]]) if i["unit_key"] == recovery["item_at_kill"]["unit_key"])
    recovery["resumed_attempts"] = resumed["attempts"]
    assert resumed["state"] == "verified" and resumed["attempts"] == recovery["item_at_kill"]["attempts"] + 1
    first, first_bindings = snapshot()
    first_writes = writes()
    # Ticket 22: the same documents again name no file and start no run; --all names them all.
    unchanged = {name: prepare(name, "unchanged") for name in names}
    forced = {name: prepare(name, "forced", "--all") for name in names}
    changed_data = {
        "unchanged_named": {n: r["scope"]["documents"] for n, r in unchanged.items()},
        "unchanged_runs": sum(r["manifest"] is not None for r in unchanged.values()),
        "forced_named": {n: r["scope"]["documents"] for n, r in forced.items()},
        "listed": {n: r["scope"]["listed"] for n, r in unchanged.items()},
    }
    # A forced run of the same documents runs to the end on the installed workers and changes nothing.
    for name in names:
        forced_run = submit("person", forced[name]["manifest"])
        drive(forced_run, ("source.read", "mdm.prepare", "mdm.merge", "journal.record"))
        finalize(forced_run)
    changed_data["forced_runs_changed_nothing"] = snapshot() == (first, first_bindings)
    with databases.ledger_admin.connect() as conn:  # the runtime reads only through functions
        changed_data["journal_events"] = dict(conn.execute(text(
            "SELECT event_type, count(*) FROM journal.event WHERE producer = 'change-propagation' GROUP BY 1")).all())
    old.say(stage="changed data", **changed_data)
    first_minutes = minutes()
    old.say(stage="first pass", **first)

    for name in names:
        source, target = tmp_path / "first" / name / "records", tmp_path / "second" / name
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("manifest.json"))
        manifest = json.loads((source / "manifest.json").read_text())
        for batch in manifest["batches"]:
            batch["batch_id"], batch["consumer"] = f"{batch['batch_id']}:second", f"{batch['consumer']}:second"
        ref = store.put_bytes((target / "manifest.json").as_uri(), json.dumps(manifest).encode())
        units = store.put(tmp_path.as_uri(), {"version": 2, "steps": {"merge": [
            {"keys": {"batch_id": f"second-{name}", "consumer": f"{PERSON}:second-{name}"}, "input": ref,
             "output": (tmp_path / "second" / f"merged-{name}.json").as_uri(), "cursor": {}}]}})
        run_id = submit("person-replay", units)
        drive(run_id, ("mdm.merge",))
        finalize(run_id)
    second, second_bindings = snapshot()
    second_writes = writes()

    report = {
        "goal": "Issue 20 20d: installed empty-store Person proof on the mastering target",
        "bundles": names, "policy": policy, "after_first_pass": first, "bindings": first_bindings,
        "second_pass_changed_nothing": first == second and first_bindings == second_bindings,
        "writes": {"after_first_pass": first_writes, "after_second_pass": second_writes},
        "recovery": recovery, "minutes_first_pass": first_minutes, "minutes": minutes(),
        "changed_data": changed_data,
    }
    out.write_text(json.dumps(report, sort_keys=True, indent=1) + "\n")
    old.say(stage="report", **report)
    for key, expected in EXPECTED.items():
        assert first[key] == expected, (key, first[key], expected)
    assert report["second_pass_changed_nothing"]
    assert changed_data["unchanged_runs"] == 0 and set(changed_data["unchanged_named"].values()) == {0}
    assert changed_data["forced_named"] == changed_data["listed"]
    assert changed_data["forced_runs_changed_nothing"]
    assert changed_data["journal_events"] == {"file.processed": 1000, "files.forced": len(names)}
    # Only changed data (migration 017): merging the same records again queues no publication work.
    assert second_writes["outbox"] == first_writes["outbox"], (first_writes, second_writes)
