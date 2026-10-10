"""Whole-source census goal: the installed empty-store Company proof.

One empty PostgreSQL 16 MDM store, loaded only by the installed bundle's
workers, each step checked by a verifier in a separate process with its own
logins; the checkout is never imported by either. The harness (this file)
only provisions: it creates the stores, registers the Company policy and the
two Dataset Contracts, and saves, proves and switches on the proof pipeline in
the disposable Rules database, as the installed-bundle acceptance test (G3)
does.

Inputs, on this machine only (no provider request):
- SEC: the seven prepared Company bundles of company mastering ticket 27
  (`<work>/bundles/chunk1..7`, version-2 manifests, 6,414 Companies and 586
  controls), each a unit of the `mdm.merge` step;
- GLEIF: the Golden Copy of 2026-09-11 16:00 (Level 1, 927,550,946 bytes,
  3,428,477 records), read by `rules/sources/gleif/level1-json.yaml` with its
  approved scope filled with the 3,755 LEIs the Name Frequency names for the
  cohort, then `mdm.prepare` and `mdm.merge`.

Passes: the SEC target with a recovery (its first worker is killed mid-run and
a later worker finishes the same run), then the GLEIF target, then both again
as new runs: the SEC bundles again, and the GLEIF reading the first pass
verified, prepared and merged again under its own consumer. Expected: 6,414 Companies, 3,052 GLEIF Level 1 records bound, the
second pass changes nothing, and the bindings equal the checkout replay's
(`/private/tmp/counts-pin-20261009.json`, 9216cc18…).

    PG16_SERVER=pgserver COMPANY_PROOF_OUT=<report.json> PATH="$HOME/.cargo/bin:$PATH" \\
      uv run --extra mdm --with pgserver pytest -q -s -p no:randomly \\
      .planning/workstreams/whole-source-census/installed_proof.py

Optional: COMPANY_PROOF_WORK (default ~/.local/share/edgartools/clean-mdm/proving/cm27),
COMPANY_PROOF_ONLY=sec (the SEC target alone, to check the plumbing).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from sqlalchemy import create_engine, text

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.database import grant_profile
from edgar_warehouse.bookkeeping.clean.destinations import migrate_guard
from edgar_warehouse.mdm.clean.store import digest, migrate, register_policy
from edgar_warehouse.rules import files
from tests.engine.test_data_skill_bundle_postgres import _run, _stores, installed  # noqa: F401
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401
from tests.support.rules_approval import approve
from tests.support.rules_authority import register_dataset

WORK = Path(os.environ.get("COMPANY_PROOF_WORK", "~/.local/share/edgartools/clean-mdm/proving/cm27")).expanduser()
GOLDEN = Path("~/.local/share/edgartools/clean-mdm/research/gleif-20260911-1600/"
              "01-20260911-1600-gleif-goldencopy-lei2-golden-copy.json.zip").expanduser()
GOLDEN_SHA256 = "1b6cd9cda3f94269fd406ee481842ea042b699e95eb5b8124b1496d4fda36a6a"
PUBLICATION_COUNT = 3428477
SEC, GLEIF = "sec.submissions.company.v1", "gleif.level1.v1"
CHECKOUT_BINDINGS = "9216cc18292f1c683f4767dfb86ae89c14a72f7df050df08e3800ce1e305b85b"
AS_OF = "2026-09-29T15:00:00+00:00"
LEASE_SECONDS = 30
TARGET = lambda steps: {"lease_seconds": LEASE_SECONDS, "heartbeat_seconds": 10,  # noqa: E731
                        "retry": {"attempts": 5, "base_ms": 100, "cap_ms": 5000}, "allow_zero_work": False,
                        "steps": steps, "checks": ["manifest.hash", "work.accounting", "journal.delivered"]}
MERGE = {"name": "merge", "operation": "mdm.merge", "requires": [], "key": "{batch_id}",
         "leases": ["mdm:consumer:{consumer}"], "checks": ["input.hash", "output.receipt", "mdm.committed"]}
PIPELINE = {"pipeline": "installed-company-proof", "bookkeeping": {"version": 1, "targets": {
    "sec": TARGET([MERGE]),
    "gleif": TARGET([
        {"name": "read", "operation": "source.read", "requires": [], "key": "{batch_id}",
         "leases": ["source-output:{batch_id}"], "checks": ["input.hash", "output.receipt", "source.output"]},
        {"name": "prepare", "operation": "mdm.prepare", "requires": ["read"], "key": "{batch_id}",
         "leases": ["mdm-prepare:{batch_id}"], "checks": ["input.hash", "output.receipt", "mdm.prepared"]},
        {**MERGE, "requires": ["prepare"]}]),
    # The second GLEIF pass: the same verified reading prepared and merged again.
    "gleif-replay": TARGET([
        {"name": "prepare", "operation": "mdm.prepare", "requires": [], "key": "{batch_id}",
         "leases": ["mdm-prepare:{batch_id}"], "checks": ["input.hash", "output.receipt", "mdm.prepared"]},
        {**MERGE, "requires": ["prepare"]}])}}}


def counts(conn) -> dict:
    one = lambda sql: conn.execute(text(sql)).scalar()  # noqa: E731
    group = lambda sql: {str(k): v for k, v in conn.execute(text(sql)).all()}  # noqa: E731
    return {
        "companies_open": one("SELECT count(*) FROM mdm.current_entity WHERE kind='company' AND status<>'alias'"),
        "stage_records": group("SELECT source_code||':'||kind, count(*) FROM mdm.stage_record GROUP BY 1"),
        "stage_bound": group("SELECT source_code, count(*) FROM mdm.stage_record WHERE entity_id IS NOT NULL GROUP BY 1"),
        "open_reviews": group("SELECT coalesce(body->>'reason','(none)'), count(*) FROM mdm.current_record "
                              "WHERE object_type='review' AND body->'open'='true'::jsonb GROUP BY 1"),
        "decisions_by_rule": group("SELECT coalesce(body->>'rule_id', body->'rule'->>'rule_id', '(none)'), count(*) "
                                   "FROM mdm.decision GROUP BY 1"),
    }


def bindings(conn) -> str:
    """Which record is bound to which master, as one digest (masters renumber per run)."""
    groups: dict[str, list[str]] = {}
    for entity, subject in conn.execute(text(
            "SELECT entity_id::text, subject FROM mdm.stage_record WHERE entity_id IS NOT NULL")):
        groups.setdefault(entity, []).append(subject)
    return digest(sorted(sorted(g) for g in groups.values()))


def say(**fields) -> None:
    print(json.dumps({"at": time.strftime("%H:%M:%S"), **fields}), flush=True)


def test_installed_company_population(installed, databases, tmp_path):  # noqa: F811
    python, root = installed
    store = Artifacts()
    out = Path(os.environ["COMPANY_PROOF_OUT"])
    only = os.environ.get("COMPANY_PROOF_ONLY")
    started = time.monotonic()

    # Provisioning (harness): an empty MDM store with its fence, the policy and the two contracts.
    for profile in ("source.read", "mdm.prepare", "mdm.merge"):
        grant_profile(databases.admin, profile=profile, worker="bk_runtime", verifier="bk_verifier")
    with databases.admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql("CREATE DATABASE mdm_proof")
    mdm_admin = create_engine(databases.admin.url.set(database="mdm_proof"))
    mdm_app = create_engine(mdm_admin.url.set(username="clean_application", password="test"))
    migrate(mdm_admin, application_role="clean_application")
    migrate_guard(mdm_admin, runtime_role="clean_application")
    with mdm_admin.begin() as conn:
        policy = register_policy(conn, files.policy())
        register_dataset(conn, SEC, "1", files.mdm_contract("sec.submissions.company", SEC))
        register_dataset(conn, GLEIF, "1", files.mdm_contract("gleif", GLEIF))
        conn.exec_driver_sql("GRANT USAGE ON SCHEMA mdm TO bk_verifier")
        conn.exec_driver_sql("GRANT SELECT ON ALL TABLES IN SCHEMA mdm TO bk_verifier")
        assert conn.execute(text("SELECT count(*) FROM mdm.stage_record")).scalar() == 0
    mdm_reader = create_engine(mdm_admin.url.set(username="bk_verifier", password="test"))
    say(stage="provisioned", policy=policy)

    # SEC: each bundle a copy naming today's policy (a manifest reads only files inside its folder).
    def sec_units(tag: str) -> dict:
        merge = []
        for n in range(1, 8):
            source, target = WORK / "bundles" / f"chunk{n}", tmp_path / tag / f"chunk{n}"
            target.mkdir(parents=True)
            for item in source.iterdir():
                if item.name != "manifest.json":
                    shutil.copy2(item, target / item.name)
            manifest = json.loads((source / "manifest.json").read_text())
            manifest["policy_digest"] = policy
            # Each pass's batches are its own, as a fresh capture's would be: a repeat of the
            # first pass's batch ids would be skipped as already merged, never mastered again.
            for batch in manifest["batches"]:
                batch["batch_id"], batch["consumer"] = f"{batch['batch_id']}:{tag}", f"{batch['consumer']}:{tag}"
            ref = store.put_bytes((target / "manifest.json").as_uri(), json.dumps(manifest).encode())
            merge.append({"keys": {"batch_id": f"{tag}-chunk{n}", "consumer": "sec.submissions.company.v1"},
                          "input": ref, "output": (tmp_path / tag / f"merged-chunk{n}.json").as_uri(), "cursor": {}})
        return store.put(tmp_path.as_uri(), {"version": 2, "steps": {"merge": merge}})

    # GLEIF: the Level 1 reading with its approved scope filled; one artifact, the whole archive.
    def gleif_units(tag: str) -> tuple[dict, int]:
        (cache,) = WORK.glob("gleif-rows-*.jsonl")
        leis = sorted({json.loads(line)[1]["LEI"]["$"] for line in cache.open()})
        contract = files.load(files.ROOT / "sources/gleif/level1-json.yaml")
        contract["read"]["references"]["approved_scope"] = {lei: {"selected": True} for lei in leis}
        contract_ref = store.put(tmp_path.as_uri(), contract)
        raw = {"uri": GOLDEN.as_uri(), "sha256": GOLDEN_SHA256}
        context = store.put(tmp_path.as_uri(), {"version": 1, "input": raw,
                                                "values": {"publication_count": PUBLICATION_COUNT}})
        reading = store.put(tmp_path.as_uri(), {"version": 2, "contract": contract_ref,
                                                "artifacts": [{"input": raw, "context": context}]})
        # Each unit's consumer is its own, from checkpoint 0 (`mdm_prepare.py`): the second
        # pass re-applies the same records as a new consumer, never rewinds the first one's.
        keys = {"batch_id": f"{tag}-level1", "consumer": f"gleif.level1.v1:{tag}"}
        base = tmp_path / tag
        return store.put(tmp_path.as_uri(), {"version": 2, "steps": {
            "read": [{"keys": keys, "input": reading, "output": (base / "reading.json").as_uri(), "cursor": {}}],
            "prepare": [{"keys": {**keys, "table": "level1", "dataset": GLEIF, "record_column": "record",
                                  "policy": policy, "as_of": AS_OF},
                         "input": {"from": {"step": "read", "key": keys["batch_id"]}},
                         "output": (base / "mdm" / "manifest.json").as_uri(), "cursor": {}}],
            "merge": [{"keys": keys, "input": {"from": {"step": "prepare", "key": keys["batch_id"]}},
                       "output": (base / "merged.json").as_uri(), "cursor": {}}]}}), len(leis)

    def replay_units(tag: str, first: str) -> dict:
        """The first pass's verified Golden Copy reading, prepared and merged again under its own consumer.
        Reading the 13 GB archive again would only repeat what `source.read`'s verifier recomputed."""
        reading = tmp_path / first / "reading.json"
        ref = {"uri": reading.as_uri(), "sha256": hashlib.sha256(reading.read_bytes()).hexdigest()}
        keys = {"batch_id": f"{tag}-level1", "consumer": f"gleif.level1.v1:{tag}"}
        base = tmp_path / tag
        return store.put(tmp_path.as_uri(), {"version": 2, "steps": {
            "prepare": [{"keys": {**keys, "table": "level1", "dataset": GLEIF, "record_column": "record",
                                  "policy": policy, "as_of": AS_OF},
                         "input": ref, "output": (base / "mdm" / "manifest.json").as_uri(), "cursor": {}}],
            "merge": [{"keys": keys, "input": {"from": {"step": "prepare", "key": keys["batch_id"]}},
                       "output": (base / "merged.json").as_uri(), "cursor": {}}]}})

    sec_first = sec_units("sec-first")
    gleif_first, scope = gleif_units("gleif-first") if only != "sec" else (None, 0)
    saved = databases.rules.save("pipeline", PIPELINE["pipeline"], "1", PIPELINE)
    databases.rules.prove("pipeline", PIPELINE["pipeline"], "1",
                          {"digest": saved["digest"], "batch_hash": sec_first["sha256"], "passed": True})
    approve(databases.approver, "pipeline", PIPELINE["pipeline"], "1")
    databases.rules.activate("pipeline", PIPELINE["pipeline"], "1")

    url = lambda engine: engine.url.render_as_string(hide_password=False)  # noqa: E731
    env = {**_stores(databases), "BOOKKEEPING_MANIFEST_ROOT": (tmp_path / "control").as_uri()}
    worker = {**env, "MDM_DATABASE_URL": url(mdm_app), "MDM_APPLICATION_ROLE": "clean_application"}
    verifier = {**env, "BOOKKEEPING_CLEAN_DATABASE_URL": url(databases.verifier), "MDM_DATABASE_URL": url(mdm_reader)}
    entry = ("-c", "import sys; from edgar_warehouse.cli import main; sys.exit(main(sys.argv[1:]))")

    def cli(*args, env=env):
        done = _run(python, "-m", "edgar_warehouse.cli", *args, env=env, cwd=root)
        assert done.returncode == 0, done.stderr[-4000:]
        return done.stdout

    def submit(target: str, units: dict) -> str:
        return json.loads(cli("rules", "run", "--pipeline", PIPELINE["pipeline"], "--target", target,
                              "--input-manifest", units["uri"], "--input-sha256", units["sha256"]))["run"]["run_id"]

    def finish(run_id: str, profiles: tuple[str, ...]) -> None:
        """Work and verify each step until its units are verified; then finalize."""
        for profile in profiles:
            deadline = time.monotonic() + 4 * 3600
            while True:
                cli("workers", "work", profile, run_id, "--limit", "100", env=worker)
                cli("workers", "verify", profile, run_id, "--reports", (tmp_path / "reports").as_uri(),
                    "--limit", "100", env=verifier)
                status = json.loads(cli("bookkeeping", "status", run_id))
                mine = [i for i in status["items"] if i["step"] == profile.split(".")[-1] or i.get("operation") == profile]
                if mine and all(i["state"] == "verified" for i in mine):
                    break
                assert time.monotonic() < deadline, status
                time.sleep(5)
            say(run=run_id, step=profile, verified=True, minutes=round((time.monotonic() - started) / 60, 1))
        cli("bookkeeping", "finalize", run_id)
        assert json.loads(cli("bookkeeping", "status", run_id))["run"]["state"] == "complete"

    def snapshot() -> tuple[dict, str]:
        with mdm_reader.connect() as conn:
            return counts(conn), bindings(conn)

    # First SEC pass, with a recovery: the first worker is killed while it holds an item
    # after an earlier item has committed (an item's rows land in one transaction, on commit).
    run_id = submit("sec", sec_first)
    killed = subprocess.Popen([str(python), "-I", *entry, "workers", "work", "mdm.merge", run_id, "--limit", "100"],
                              env={**os.environ, **worker}, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = time.monotonic() + 600
    held = None
    while killed.poll() is None and time.monotonic() < deadline:
        items = json.loads(cli("bookkeeping", "status", run_id))["items"]
        held = next((i for i in items if i["state"] == "running"), None)
        if held and snapshot()[0]["stage_records"]:
            killed.send_signal(signal.SIGKILL)
            break
        time.sleep(0.2)
    killed.wait()
    recovery = {"killed_worker_exit": killed.returncode, "item_at_kill": held,
                "rows_at_kill": snapshot()[0]["stage_records"]}
    say(stage="worker killed", **recovery)
    assert killed.returncode == -signal.SIGKILL, "the worker finished before it was killed"
    assert recovery["rows_at_kill"], "no earlier item had committed when the worker was killed"
    time.sleep(LEASE_SECONDS + 5)  # its lease lapses; the run resumes under a new worker
    finish(run_id, ("mdm.merge",))
    resumed = next(i for i in json.loads(cli("bookkeeping", "status", run_id))["items"]
                   if i["unit_key"] == held["unit_key"])
    recovery["resumed_attempts"] = resumed["attempts"]
    assert resumed["state"] == "verified" and resumed["attempts"] == held["attempts"] + 1, resumed
    if only != "sec":
        finish(submit("gleif", gleif_first), ("source.read", "mdm.prepare", "mdm.merge"))
    first, first_bindings = snapshot()
    say(stage="first pass", **first)

    # Second pass: new runs over the same inputs.
    finish(submit("sec", sec_units("sec-second")), ("mdm.merge",))
    if only != "sec":
        finish(submit("gleif-replay", replay_units("gleif-second", "gleif-first")), ("mdm.prepare", "mdm.merge"))
    second, second_bindings = snapshot()

    report = {
        "goal": "whole-source census: installed empty-store Company proof",
        "only": only, "policy": policy, "gleif_scope_leis": scope,
        "after_first_pass": first, "bindings": first_bindings,
        "second_pass_changed_nothing": first == second and first_bindings == second_bindings,
        "recovery": recovery,
        "bindings_equal_checkout_replay": first_bindings == CHECKOUT_BINDINGS if only != "sec" else None,
        "minutes": round((time.monotonic() - started) / 60, 1),
    }
    out.write_text(json.dumps(report, sort_keys=True, indent=1) + "\n")
    say(stage="report", **report)
    assert report["second_pass_changed_nothing"]
    assert first["stage_bound"].get(SEC) == 6414
    assert report["bindings_equal_checkout_replay"] in (True, None)
    if only != "sec":
        assert first["companies_open"] == 6414 and first["stage_bound"].get(GLEIF) == 3052
