"""Issue 20 slice 20c part 4: the installed empty-store Company proof on the `mastering` target.

The 2026-10-10 proof (`.planning/workstreams/whole-source-census/installed_proof.py`)
merged bundles the in-process preparation had written. Here the installed
bundle's workers prepare them too: each bundle is one run of the Company
`mastering` target (main, keys, catalog, census, combine, records, merge), its
input manifest written by the installed `mdm prepare-clean-company`. Workers
and verifiers run in separate processes under their own logins; the checkout
only provisions (stores, policy, contracts, the proof pipeline).

Inputs, on this machine only (no provider request):
- SEC: the raw capture `all-76230`, the 2026-10-10 population and its Name
  Census, and 14 document lists of at most 512 (chunks 1-7 of company
  mastering ticket 27: 6,726 Company documents), in `<work>/`;
- GLEIF: the Golden Copy of 2026-09-11 16:00 (Level 1), as in the 2026-10-10 proof.

Passes: each bundle prepared (two bundles at a time) and merged one at a time
in bundle order; the first bundle's merge worker is killed while it holds the
item and a later worker finishes it. Then the GLEIF target. Then the second
pass: the first pass's verified records of every bundle merged again under new
batch ids and consumers (preparing again would give the same batch ids, which
MDM skips as already merged), and the GLEIF reading prepared and merged again.
Expected: 6,726 SEC documents prepared, 6,414 SEC records staged and bound (312 more wait
as classification deferred), 6,414 Companies, 3,052 GLEIF records bound, the
second pass changes nothing, and the bindings equal the checkout replay's
(`/private/tmp/counts-pin-20261009.json`, 9216cc18…).

    PG16_SERVER=pgserver COMPANY_PROOF_OUT=<report.json> PATH="$HOME/.cargo/bin:$PATH" \\
      uv run --extra mdm --with pgserver pytest -q -s -p no:randomly \\
      .scratch/mastering-to-done/proof/installed_mastering_proof.py

Optional: COMPANY_PROOF_WORK (default ~/.local/share/edgartools/clean-mdm/proving/cm27-raw),
COMPANY_PROOF_BUNDLES=1-1,1-2 (a subset; the count checks then do not apply),
COMPANY_PROOF_ONLY=sec (the SEC target alone).
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
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

import importlib.util

_OLD = importlib.util.spec_from_file_location(
    "census_proof", Path(__file__).resolve().parents[3] / ".planning/workstreams/whole-source-census/installed_proof.py")
old = importlib.util.module_from_spec(_OLD)
_OLD.loader.exec_module(old)  # counts, bindings, the GLEIF inputs and steps: unchanged from 2026-10-10

WORK = Path(os.environ.get("COMPANY_PROOF_WORK", "~/.local/share/edgartools/clean-mdm/proving/cm27-raw")).expanduser()
CAPTURE = Path("~/.local/share/edgartools/clean-mdm/captures/sec.submissions.company/all-76230").expanduser()
CATALOG = "warehouse/bronze/reference/sec/company_tickers_exchange/2026/09/02/company_tickers_exchange.json"
OBSERVED_AT, CATALOG_RUN = "2026-09-30T02:20:28+00:00", "local-cm27-tickers-20260902"
SEC, GLEIF = old.SEC, old.GLEIF
PROFILES = ("source.read", "source.combine", "mdm.prepare")
LIMIT = "1000"  # a worker claims one unit at a time, up to this many
MIN_FREE = 3 * 1024**3
PIN = json.loads(Path("/private/tmp/counts-pin-20261009.json").read_text())  # the checkout replay's counts

MASTERING = files.source("sec.submissions.company")["bookkeeping"]["targets"]["mastering"]["steps"]
assert [s["name"] for s in MASTERING][-2:] == ["merge", "processed"]  # ticket 22: then the Change Journal
MERGE = next(s for s in MASTERING if s["name"] == "merge")
PIPELINE = {"pipeline": "installed-mastering-proof", "bookkeeping": {"version": 1, "targets": {
    **old.PIPELINE["bookkeeping"]["targets"],
    "sec": old.TARGET(MASTERING),
    "sec-replay": old.TARGET([{**MERGE, "requires": []}])}}}


def bundles() -> list[str]:
    found = sorted(p.name.removeprefix("documents-").removesuffix(".json") for p in WORK.glob("documents-*.json"))
    wanted = os.environ.get("COMPANY_PROOF_BUNDLES")
    return [b for b in found if not wanted or b in wanted.split(",")]


def test_installed_company_mastering(installed, databases, tmp_path):  # noqa: F811
    python, root = installed
    store = Artifacts()
    out = Path(os.environ["COMPANY_PROOF_OUT"])
    only = os.environ.get("COMPANY_PROOF_ONLY")
    names = bundles()
    whole = not os.environ.get("COMPANY_PROOF_BUNDLES")
    started = time.monotonic()
    timings: dict[str, float] = {}

    def minutes() -> float:
        return round((time.monotonic() - started) / 60, 1)

    def disk() -> None:
        free = shutil.disk_usage(tmp_path).free
        assert free > MIN_FREE, f"disk: {free / 1024**3:.1f} GB free"

    # Provisioning (harness): an empty MDM store with its fence, the policy and the two contracts.
    for profile in (*PROFILES, "mdm.merge", "journal.record"):
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
    old.say(stage="provisioned", policy=policy, bundles=names)

    url = lambda engine: engine.url.render_as_string(hide_password=False)  # noqa: E731
    env = {**_stores(databases), "BOOKKEEPING_MANIFEST_ROOT": (tmp_path / "control").as_uri()}
    worker = {**env, "MDM_DATABASE_URL": url(mdm_app), "MDM_APPLICATION_ROLE": "clean_application"}
    verifier = {**env, "BOOKKEEPING_CLEAN_DATABASE_URL": url(databases.verifier), "MDM_DATABASE_URL": url(mdm_reader)}
    entry = ("-c", "import sys; from edgar_warehouse.cli import main; sys.exit(main(sys.argv[1:]))")

    calls: dict[str, list[float]] = {}

    def cli(*args, env=env):
        began = time.monotonic()
        done = _run(python, "-m", "edgar_warehouse.cli", *args, env=env, cwd=root)
        kind = " ".join(args[:3]) if args[0] == "workers" else " ".join(args[:2])
        calls.setdefault(kind, []).append(time.monotonic() - began)
        assert done.returncode == 0, done.stderr[-4000:]
        return done.stdout

    # Each bundle's input manifest, written by the installed CLI into this attempt's folder.
    def prepare_manifest(name: str, folder: str = "sec-first") -> dict:
        report = json.loads(cli(
            "mdm", "prepare-clean-company", "--capture", str(CAPTURE), "--documents", str(WORK / f"documents-{name}.json"),
            "--population", str(WORK / "population.json"), "--name-census", str(WORK / "census.json"),
            "--catalog", CATALOG, "--capture-run", f"local-cm27-chunk{name.split('-')[0]}", "--catalog-run", CATALOG_RUN,
            "--observed-at", OBSERVED_AT, "--output", str(tmp_path / folder / name),
            "--as-of", old.AS_OF, "--revision", "0"))
        assert report["policy_digest"] == policy, (report["policy_digest"], policy)
        return report

    with ThreadPoolExecutor(4) as pool:
        reports = dict(zip(names, pool.map(prepare_manifest, names)))
    timings["manifests"] = minutes()
    old.say(stage="manifests", minutes=minutes())

    gleif_first, scope = (None, 0)
    if only != "sec":
        gleif_first, scope = _gleif(old, store, tmp_path, policy)
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
        """Work and verify each profile in turn until every item (of `steps`) is verified."""
        deadline = time.monotonic() + 4 * 3600
        while True:
            disk()
            for profile in profiles:
                cli("workers", "work", profile, run_id, "--limit", LIMIT, env=worker)
                cli("workers", "verify", profile, run_id, "--reports", (tmp_path / "reports").as_uri(),
                    "--limit", LIMIT, env=verifier)
            mine = [i for i in items(run_id) if steps is None or i["step"] in steps]
            if mine and all(i["state"] == "verified" for i in mine):
                return
            failed = [i for i in mine if i["state"] in ("failed", "rejected")]
            assert not failed, failed[:3]
            assert time.monotonic() < deadline, [i for i in mine if i["state"] != "verified"][:3]
            time.sleep(2)

    def finalize(run_id: str) -> None:
        cli("bookkeeping", "finalize", run_id)
        assert json.loads(cli("bookkeeping", "status", run_id))["run"]["state"] == "complete"

    def snapshot() -> tuple[dict, str]:
        with mdm_reader.connect() as conn:
            return old.counts(conn), old.bindings(conn)

    def writes() -> dict:
        """Rows each MDM table and the change journal hold: what a pass wrote."""
        with mdm_reader.connect() as conn:
            found = {t: conn.execute(text(f"SELECT count(*) FROM mdm.{t}")).scalar() for t in (
                "batch", "source_reading", "decision", "company", "current_record", "outbox", "checkpoint",
                "match_proposal", "set_aside_record")}
        journal = create_engine(databases.admin.url.set(database=databases.ledger.engine.url.database))
        with journal.connect() as conn:
            found["journal_events"] = conn.execute(text("SELECT count(*) FROM journal.event")).scalar()
        return found

    # First SEC pass: preparation two bundles at a time; merges one at a time, in bundle order.
    runs = {name: submit("sec", reports[name]["manifest"]) for name in names}
    preparation = [step["name"] for step in MASTERING[:-1]]

    def prepared(name: str) -> str:
        drive(runs[name], PROFILES, set(preparation))
        units = {}
        for i in items(runs[name]):
            units[i["step"]] = units.get(i["step"], 0) + 1
        old.say(bundle=name, prepared=True, minutes=minutes(), units=units,
                calls={k: {"n": len(v), "seconds": round(sum(v), 1)} for k, v in calls.items()})
        return name

    recovery: dict = {}
    with ThreadPoolExecutor(2) as pool:
        for name in pool.map(prepared, names):
            run_id = runs[name]
            if not recovery:  # the first bundle's merge worker is killed while it holds the item
                recovery = kill_and_recover(python, entry, worker, root, run_id, items, snapshot)
            drive(run_id, ("mdm.merge", "journal.record"))
            finalize(run_id)
            old.say(bundle=name, merged=True, minutes=minutes())
    resumed = next(i for i in items(runs[names[0]]) if i["unit_key"] == recovery["item_at_kill"]["unit_key"])
    recovery["resumed_attempts"] = resumed["attempts"]
    assert resumed["state"] == "verified" and resumed["attempts"] == recovery["item_at_kill"]["attempts"] + 1, resumed
    timings["sec_first"] = minutes()
    if only != "sec":
        gleif_run = submit("gleif", gleif_first)
        drive(gleif_run, ("source.read", "mdm.prepare", "mdm.merge"))
        finalize(gleif_run)
        timings["gleif_first"] = minutes()
    first, first_bindings = snapshot()
    first_writes = writes()
    old.say(stage="first pass", writes=first_writes, **first)

    # Ticket 22: the same documents prepared again name no file and start no run.
    with ThreadPoolExecutor(4) as pool:
        again = dict(zip(names, pool.map(lambda n: prepare_manifest(n, "sec-again"), names)))
    changed_data = {"listed": sum(r["scope"]["listed"] for r in again.values()),
                    "named_again": sum(r["scope"]["selected_records"] for r in again.values()),
                    "runs_started_again": sum(1 for r in again.values() if r["manifest"]),
                    "named_first": sum(r["scope"]["selected_records"] for r in reports.values())}
    journal = create_engine(databases.admin.url.set(database=databases.ledger.engine.url.database))
    with journal.connect() as conn:
        changed_data["file_processed_events"] = conn.execute(text(
            "SELECT count(*) FROM journal.event WHERE producer='change-propagation' "
            "AND event_key LIKE 'file.processed:%'")).scalar()
    journal.dispose()
    old.say(stage="changed data", **changed_data)
    timings["changed_data"] = minutes()

    # Second pass: every bundle's verified records merged again under new batch ids and consumers.
    for name in names:
        source, target = tmp_path / "sec-first" / name / "records", tmp_path / "sec-second" / name
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("manifest.json"))  # written below
        manifest = json.loads((source / "manifest.json").read_text())
        for batch in manifest["batches"]:
            batch["batch_id"], batch["consumer"] = f"{batch['batch_id']}:sec-second", f"{batch['consumer']}:sec-second"
        ref = store.put_bytes((target / "manifest.json").as_uri(), json.dumps(manifest).encode())
        units = store.put(tmp_path.as_uri(), {"version": 2, "steps": {"merge": [
            {"keys": {"batch_id": f"sec-second-{name}", "consumer": f"{SEC}:sec-second-{name}"}, "input": ref,
             "output": (tmp_path / "sec-second" / f"merged-{name}.json").as_uri(), "cursor": {}}]}})
        run_id = submit("sec-replay", units)
        drive(run_id, ("mdm.merge",))
        finalize(run_id)
    if only != "sec":
        replay = old_replay(store, tmp_path, policy)
        run_id = submit("gleif-replay", replay)
        drive(run_id, ("mdm.prepare", "mdm.merge"))
        finalize(run_id)
    second, second_bindings = snapshot()
    second_writes = writes()
    old.say(stage="second pass", writes=second_writes)
    timings["second_pass"] = minutes()

    report = {
        "goal": "Issue 20 20c part 4: installed empty-store Company proof on the mastering target",
        "only": only, "bundles": names, "policy": policy, "gleif_scope_leis": scope,
        "after_first_pass": first, "bindings": first_bindings,
        "second_pass_changed_nothing": first == second and first_bindings == second_bindings,
        "writes": {"after_first_pass": first_writes, "after_second_pass": second_writes},
        "recovery": recovery, "changed_data": changed_data, "minutes_since_start": timings,  # cumulative: each stage's end
        "bindings_equal_checkout_replay": first_bindings == old.CHECKOUT_BINDINGS if only != "sec" and whole else None,
        "checkout_replay": {k: v for k, v in PIN["after_first_pass"].items() if k in first},
        "minutes": minutes(),
    }
    out.write_text(json.dumps(report, sort_keys=True, indent=1) + "\n")
    old.say(stage="report", **report)
    assert report["second_pass_changed_nothing"]
    # Only changed data (017): merging the same records again queues no publication work.
    assert second_writes["outbox"] == first_writes["outbox"], (first_writes, second_writes)
    assert changed_data["named_again"] == 0 and changed_data["runs_started_again"] == 0, changed_data
    assert changed_data["file_processed_events"] == changed_data["named_first"], changed_data
    if whole:
        assert first["stage_records"].get(f"{SEC}:company") == 6414, first["stage_records"]
        assert first["stage_bound"].get(SEC) == 6414
        assert report["bindings_equal_checkout_replay"] in (True, None)
        if only != "sec":
            assert first["companies_open"] == 6414 and first["stage_bound"].get(GLEIF) == 3052
            assert report["bindings_equal_checkout_replay"] is True
            replay = PIN["after_first_pass"]
            for key in ("companies_open", "stage_records", "stage_bound", "decisions_by_rule"):
                assert first[key] == replay[key], key
            # The replay counted the records GLEIF cannot bind apart; here they are open reviews.
            assert first["open_reviews"] == {**replay["open_reviews"], **PIN["gleif_set_aside"]}


def kill_and_recover(python, entry, worker, root, run_id, items, snapshot) -> dict:
    """Start a merge worker, kill it while it holds the item, and let its lease lapse.
    Where the kill lands inside the item (before or after its one MDM transaction
    commits) is timing; either way the item must be verified on its next attempt."""
    killed = subprocess.Popen([str(python), "-I", *entry, "workers", "work", "mdm.merge", run_id, "--limit", LIMIT],
                              env={**os.environ, **worker}, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = time.monotonic() + 600
    held = None
    while killed.poll() is None and time.monotonic() < deadline:
        held = next((i for i in items(run_id) if i["state"] == "running"), None)
        if held:
            killed.send_signal(signal.SIGKILL)
            break
        time.sleep(0.2)
    stdout, stderr = killed.communicate()
    recovery = {"killed_worker_exit": killed.returncode, "item_at_kill": held, "rows_at_kill": snapshot()[0]["stage_records"]}
    if killed.returncode != -signal.SIGKILL:
        recovery["worker_output"] = {"stdout": stdout.decode()[-2000:], "stderr": stderr.decode()[-2000:],
                                     "items": [i for i in items(run_id) if i["step"] == "merge"]}
    old.say(stage="worker killed", **recovery)
    assert killed.returncode == -signal.SIGKILL, "the worker finished before it was killed"
    time.sleep(old.LEASE_SECONDS + 5)  # its lease lapses; the run resumes under a new worker
    return recovery


def _gleif(old, store, tmp_path, policy) -> tuple[dict, int]:
    """The 2026-10-10 GLEIF units: the Level 1 reading with its approved scope filled."""
    (cache,) = Path("~/.local/share/edgartools/clean-mdm/proving/cm27").expanduser().glob("gleif-rows-*.jsonl")
    leis = sorted({json.loads(line)[1]["LEI"]["$"] for line in cache.open()})
    contract = files.load(files.ROOT / "sources/gleif/level1-json.yaml")
    contract["read"]["references"]["approved_scope"] = {lei: {"selected": True} for lei in leis}
    contract_ref = store.put(tmp_path.as_uri(), contract)
    raw = {"uri": old.GOLDEN.as_uri(), "sha256": old.GOLDEN_SHA256}
    context = store.put(tmp_path.as_uri(), {"version": 1, "input": raw,
                                            "values": {"publication_count": old.PUBLICATION_COUNT}})
    reading = store.put(tmp_path.as_uri(), {"version": 2, "contract": contract_ref,
                                            "artifacts": [{"input": raw, "context": context}]})
    keys = {"batch_id": "gleif-first-level1", "consumer": f"{GLEIF}:gleif-first"}
    base = tmp_path / "gleif-first"
    return store.put(tmp_path.as_uri(), {"version": 2, "steps": {
        "read": [{"keys": keys, "input": reading, "output": (base / "reading.json").as_uri(), "cursor": {}}],
        "prepare": [{"keys": {**keys, "table": "level1", "dataset": GLEIF, "record_column": "record",
                              "policy": policy, "as_of": old.AS_OF},
                     "input": {"from": {"step": "read", "key": keys["batch_id"]}},
                     "output": (base / "mdm" / "manifest.json").as_uri(), "cursor": {}}],
        "merge": [{"keys": keys, "input": {"from": {"step": "prepare", "key": keys["batch_id"]}},
                   "output": (base / "merged.json").as_uri(), "cursor": {}}]}}), len(leis)


def old_replay(store, tmp_path, policy) -> dict:
    """The first pass's verified Golden Copy reading, prepared and merged again under its own consumer."""
    import hashlib
    reading = tmp_path / "gleif-first" / "reading.json"
    ref = {"uri": reading.as_uri(), "sha256": hashlib.sha256(reading.read_bytes()).hexdigest()}
    keys = {"batch_id": "gleif-second-level1", "consumer": f"{GLEIF}:gleif-second"}
    base = tmp_path / "gleif-second"
    return store.put(tmp_path.as_uri(), {"version": 2, "steps": {
        "prepare": [{"keys": {**keys, "table": "level1", "dataset": GLEIF, "record_column": "record",
                              "policy": policy, "as_of": old.AS_OF},
                     "input": ref, "output": (base / "mdm" / "manifest.json").as_uri(), "cursor": {}}],
        "merge": [{"keys": keys, "input": {"from": {"step": "prepare", "key": keys["batch_id"]}},
                   "output": (base / "merged.json").as_uri(), "cursor": {}}]}})
