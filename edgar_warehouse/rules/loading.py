"""`edgar-warehouse load`: load a captured delivery through one source's target (ticket 136).

One command for every source and target, with nothing named after either:

1. Finish first: a run of this source and target that is still running or waiting
   is driven to the end before anything new is submitted. A run that cannot be finished
   (its retry fails) is named and left as it is: a replacement needs a new run, and the
   Change Journal, which holds only what was verified, loads its documents again.
2. The documents are the capture's receipts the target reads: those matching its
   first step's `files` pattern (all of them when it names none).
3. They are cut into bundles of the source's `execution.max_artifacts`. Each bundle
   is prepared (`mdm prepare-capture`: the Change Journal leaves out what is already
   processed under these rules), submitted (`rules run`) and driven to `complete`,
   `--bundles` at once: bundles of one target are one wave, not a queue.

Stopping is safe: run the same command again and it carries on where it stopped.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.control_contract import digest
from edgar_warehouse.mdm import raw_capture

from . import files
from .driving import Commands, RunStopped, duties, manifest_root, run_steps
from .preparation import prepare_load

OPEN = ("running", "waiting")


def documents(reading: dict, target: str, capture: Path) -> list[str]:
    """The capture's receipt keys the target's first step reads, in key order."""
    steps = reading["bookkeeping"]["targets"][target]["steps"]
    pattern = (steps[0].get("input") or {}).get("files", "*") if steps else "*"
    _, receipts = raw_capture.receipts(capture)
    return sorted(key for key in receipts if fnmatch.fnmatchcase(key, pattern))


def shared_documents(reading: dict, target: str, capture: Path) -> list[str]:
    """The capture's receipt keys that steps with `input.always` read in every bundle (an exchange catalog)."""
    patterns = [(step.get("input") or {})["files"] for step in reading["bookkeeping"]["targets"][target]["steps"]
                if (step.get("input") or {}).get("always")]
    _, receipts = raw_capture.receipts(capture)
    return sorted(key for key in receipts if any(fnmatch.fnmatchcase(key, p) for p in patterns))


def cut_bundles(reading: dict, target: str, capture: Path) -> list[list[str]]:
    """The target's documents in bundles of the source's limit; each bundle also holds the shared documents,
    which count in its size."""
    shared = shared_documents(reading, target, capture)
    size = reading["execution"]["max_artifacts"] - len(shared)
    if shared and size < 1:
        raise RunStopped(f"A bundle of {reading['execution']['max_artifacts']} cannot hold the {len(shared)} shared "
                         "documents every bundle reads and one more")
    mine = [key for key in documents(reading, target, capture) if key not in shared]
    return [sorted([*part, *shared]) for part in bundles(mine, size)]


def bundles(keys: list[str], size: int) -> list[list[str]]:
    """The documents in bundles of at most `size`, in key order."""
    if size < 1:
        raise RunStopped("A bundle holds at least one document")
    return [keys[start:start + size] for start in range(0, len(keys), size)]


def target_of(source: str, target: str) -> dict:
    reading = files.source(source)
    if target not in ((reading.get("bookkeeping") or {}).get("targets") or {}):
        raise RunStopped(f"{source} declares no `{target}` target: see the targets in rules/sources/{source}/source.yaml")
    return reading


def silver_specs(source: str, reading: dict, target: str) -> list[Path]:
    """The spec file of each silver table the target writes: `silver-*.yaml` beside the source's rules, or in
    `rules/silver` when several sources share the table, whose `table` a silver step names."""
    steps = reading["bookkeeping"]["targets"][target]["steps"]
    wanted = [((step.get("input") or {}).get("keys") or {}).get("silver") for step in steps
              if step.get("operation") in ("silver.land", "silver.derive")]
    held = {}
    for path in [*sorted((files.ROOT / "sources" / source).glob("silver-*.yaml")),
                 *sorted((files.ROOT / "silver").glob("silver-*.yaml"))]:
        held[(files.load(path) or {}).get("table")] = path
    missing = sorted(table for table in wanted if table and table not in held)
    if missing:
        raise RunStopped(f"{source} {target} lands silver table(s) {', '.join(missing)} with no silver-*.yaml spec "
                         f"in rules/sources/{source}")
    return [held[table] for table in dict.fromkeys(wanted) if table]


class Loader:
    """One source's target over one capture, on the stores one environment folder names."""

    def __init__(self, *, source: str, target: str, stores: Path, workers: int, minutes: float, at_a_time: int = 1,
                 say=lambda line: print(line, file=sys.stderr, flush=True)):
        if at_a_time < 1:
            raise RunStopped("At least one bundle at a time")
        self.source, self.target, self.say, self.at_a_time = source, target, say, at_a_time
        self.reading = target_of(source, target)
        self.runtimes: dict[str, str] = {}
        env = self.env = duties(stores)
        lands = [step["name"] for step in self.reading["bookkeeping"]["targets"][target]["steps"]
                 if step.get("operation") in ("silver.land", "silver.derive")]
        bare = [duty for duty in ("worker", "verifier") if lands and not env[duty].get("SILVER_DATABASE_URL")]
        if bare:
            raise RunStopped(f"{source} {target} lands silver (steps {', '.join(lands)}) but the {' and '.join(bare)} "
                             f"env file has no silver login: start the stores with infra/scripts/local-test-stores.py up <name>")
        self.root = manifest_root(env) / "load" / source / target
        self.commands = Commands(env, (self.root / "reports").as_uri(), deadline=time.monotonic() + minutes * 60,
                                 log=stores / "load-errors.log", workers=workers)

    def register_silver(self) -> list[str]:
        """Create each silver table this target lands, before anything is submitted. Registering is idempotent
        (the same spec changes nothing; a changed spec for a registered table is refused), so every load does it
        and no one prepares a store by hand. It runs as the stores' migration login, for the silver runtime role."""
        specs = silver_specs(self.source, self.reading, self.target)
        if not specs:
            return []
        if "migration" not in self.env:
            raise RunStopped(f"{self.source} {self.target} lands silver but the stores folder has no connection.env "
                             f"(the migration login that creates a silver table)")
        role = make_url(self.env["worker"]["SILVER_DATABASE_URL"]).username
        for spec in specs:
            self.commands("migration", "silver", "register", str(spec), "--runtime-role", role)
            self.say(f"Silver table of {spec.name} is registered")
        return [spec.name for spec in specs]

    def mine(self, state: str) -> list[dict]:
        listed = json.loads(self.commands("worker", "bookkeeping", "runs", "--state", state, "--limit", "1000"))
        return [r for r in listed if (r.get("name"), r.get("target")) == (self.source, self.target)]

    def runtime(self, profile: str) -> str:
        """This checkout's worker runtime digest for a profile, the one a run pins on first use."""
        if profile not in self.runtimes:
            self.runtimes[profile] = json.loads(self.commands("worker", "workers", "describe", profile))["runtime"]
        return self.runtimes[profile]

    def open_runs(self) -> tuple[list[str], dict[str, str]]:
        """Runs of this source and target to finish first, oldest first, and the runs left as they
        are, each with why. A blocked run under the active rules version stops the load: its
        documents would otherwise be submitted again. A blocked run under a retired version, or
        an open run pinned to other worker code (which this checkout cannot finish), stays as it
        is: the Change Journal loads its documents again in a new run."""
        listed = json.loads(self.commands("worker", "rules", "status", "--source", self.source))
        self.active_rules = next((v for v in listed if v.get("status") == "active"), None)
        active = self.active_rules["version"] if self.active_rules else None
        left = {}
        for run in self.mine("blocked"):
            version = self.commands.status(str(run["run_id"]))["run"]["submission"].get("rule_version")
            if version == active:
                raise RunStopped(f"Run {run['run_id']} of {self.source} {self.target} is blocked: read "
                                 f"bookkeeping status {run['run_id']}, and recover it (bookkeeping RECOVERY.md) "
                                 "before loading more")
            left[str(run["run_id"])] = f"blocked under retired rules version {version}"
        unfinished = []
        for run in sorted((r for state in OPEN for r in self.mine(state)), key=lambda r: str(r["created_at"])):
            pinned = self.commands.status(str(run["run_id"]))["run"].get("runtimes") or {}
            other = sorted(p for p, digest in pinned.items() if not p.startswith("verify:") and digest != self.runtime(p))
            if other:
                left[str(run["run_id"])] = f"pinned to other worker code ({', '.join(other)})"
            else:
                unfinished.append(str(run["run_id"]))
        return unfinished, left

    def drive(self, run_id: str) -> dict:
        """Drive a run by the steps it was frozen with, which a later rules version cannot change."""
        submission = self.commands.status(run_id)["run"]["submission"]
        frozen = run_steps(Artifacts().json(submission["rules"])["body"], self.target)
        began = time.monotonic()
        final = self.commands.drive(run_id, frozen)
        state = final["run"]["state"]
        if state != "complete":
            raise RunStopped(f"Run {run_id} ended {state}, not complete; its checks: {final['run'].get('checks')}")
        self.say(f"  run {run_id} complete in {round((time.monotonic() - began) / 60, 1)} min")
        return final

    def bundle(self, number: int, total: int, keys: list[str], *, folder: Path, capture: Path, capture_run: str,
               as_of: str, revision: int, extra: list[str]) -> dict:
        """Prepare one bundle, then submit and drive it unless every document is loaded already."""
        where = folder / f"bundle-{number:03d}"
        where.mkdir(parents=True, exist_ok=True)
        (where / "documents.json").write_text(json.dumps(keys))
        prepared = json.loads(self.commands(
            "worker", "mdm", "prepare-capture", "--source", self.source, "--target", self.target,
            "--capture", str(capture), "--documents", str(where / "documents.json"), "--capture-run", capture_run,
            "--as-of", as_of, "--revision", str(revision), "--output", str(where / "manifest"), *extra))
        fresh = prepared["scope"]["documents"]
        entry = {"bundle": number, "documents": len(keys), "new": fresh, "run_id": None}
        if prepared["manifest"] is None:
            self.say(f"Bundle {number}/{total}: all {len(keys)} documents already loaded")
            return entry
        self.say(f"Bundle {number}/{total}: {fresh} of {len(keys)} documents to load")
        submitted = json.loads(self.commands(
            "worker", "rules", "run", "--source", self.source, "--target", self.target,
            "--input-manifest", prepared["manifest"]["uri"], "--input-sha256", prepared["manifest"]["sha256"]))
        entry["run_id"] = str(submitted["run"]["run_id"])
        entry["counts"] = self.drive(entry["run_id"]).get("counts")
        return entry

    def at_once(self, work: list[tuple[str, object]]) -> list:
        """Each named piece of work (a function of no arguments), `self.at_a_time` at once, results in
        order. A piece that stops does not stop the others. Once the deadline has passed, a piece
        not yet started is not started. Every stop and every piece not started is named at the end."""
        late = []

        def guarded(name, piece):
            if time.monotonic() >= self.commands.deadline:
                late.append(name)
                return None
            try:
                return piece()
            except Exception as error:  # one piece's failure, named; the others go on
                return RunStopped(f"{name}: {error}")
        with ThreadPoolExecutor(self.at_a_time) as pool:
            done = list(pool.map(lambda named: guarded(*named), work))
        stopped = [str(d) for d in done if isinstance(d, RunStopped)]
        if late:
            stopped.append(f"the deadline passed before {len(late)} started ({', '.join(sorted(late))})")
        if stopped:
            raise RunStopped(f"{len(stopped)} of {len(done)} did not finish: " + " | ".join(stopped))
        return done

    def cut(self, capture: Path) -> list[list[str]]:
        """The capture's documents this target reads, in bundles of the source's limit."""
        return cut_bundles(self.reading, self.target, capture)

    def plan(self, *, capture: Path) -> dict:
        """What `load` would do, read-only: no bundle is prepared, no run submitted or driven. The runs it
        would finish, the runs it would leave and why (their documents then load again in new runs), a
        blocked run that would stop it, and the documents and bundles."""
        plan = {"source": self.source, "target": self.target, "blocked": None}
        try:
            plan["finishable_runs"], plan["left_as_they_are"] = self.open_runs()
        except RunStopped as stopped:
            # The blocked run stopped the listing: the other runs are unknown (None), not none.
            plan["blocked"], plan["finishable_runs"], plan["left_as_they_are"] = str(stopped), None, None
        cut = self.cut(capture)
        plan.update(documents=len({k for b in cut for k in b}), bundle_size=self.reading["execution"]["max_artifacts"],
                    bundles=len(cut))
        preparation = self.reading["bookkeeping"]["targets"][self.target].get("preparation")
        if preparation:
            plan["preparation"] = preparation
        return plan

    def derived_files(self, given: list[str], *, folder: Path) -> list[str]:
        """The run files the target derives and the caller did not give, built from the store now: each one is
        named as `name=path`, with what it holds and why it is made."""
        from edgar_warehouse.bookkeeping.clean.config import run_inputs
        from edgar_warehouse.mastering.store import open_store
        from edgar_warehouse.mdm.connections import engine_from_environment
        from edgar_warehouse.rules import derivations

        derived = run_inputs(self.reading["bookkeeping"]["targets"][self.target])["derived"]
        named = {entry.split("=", 1)[0] for entry in given}
        wanted = {name: how for name, how in derived.items() if name not in named}
        if not wanted:
            return []
        engine = engine_from_environment("MDM_DATABASE_URL", self.env["worker"], restricted=True)
        store = open_store(engine)
        made = []
        try:
            for name, how in wanted.items():
                path, count = derivations.derive(how["method"], name, folder=folder, store=store)
                self.say(f"Derived {name} by {how['method']}: {count} values. Purpose: {how['purpose']} Why: {how['why']}")
                made.append(f"{name}={path}")
        finally:
            store.close()
            engine.dispose()
        return made

    def load(self, *, capture: Path, capture_run: str, as_of: str, facts: list[str], run_files: list[str],
             revision: int = 0, force: bool = False) -> dict:
        result = {"source": self.source, "target": self.target, "finished_open_runs": [], "bundles": []}
        result["silver_registered"] = self.register_silver()
        unfinished, result["left_as_they_are"] = self.open_runs()
        for run_id, why in result["left_as_they_are"].items():
            self.say(f"Run {run_id} is left as it is: {why}")
        for run_id in unfinished:
            self.say(f"Finishing run {run_id}, left open before")
        result["finished_open_runs"] = []

        def finish(run_id: str) -> None:
            """A run that cannot be finished (a conflicting output, say) cannot be resumed, and a replacement
            needs a new run (bookkeeping RECOVERY.md): name it and go on. The Change Journal holds only what was
            verified, so its documents load again below. It stays in Bookkeeping as evidence."""
            try:
                self.drive(run_id)
            except RunStopped as stopped:
                result["left_as_they_are"][run_id] = f"could not be finished: {stopped}"
                self.say(f"Run {run_id} could not be finished and is left as it is: {stopped}")
            else:
                result["finished_open_runs"].append(run_id)
        self.at_once([(f"run {run_id}", lambda run_id=run_id: finish(run_id)) for run_id in unfinished])
        result["finished_open_runs"] = [run_id for run_id in unfinished if run_id in result["finished_open_runs"]]
        if self.reading["bookkeeping"]["targets"][self.target].get("preparation"):
            if not self.active_rules or self.active_rules.get("digest") != digest(self.reading):
                raise RunStopped("Automatic preparation requires this source's current Rules digest to be active")
        result["preparation"] = prepare_load(reading=self.reading, target=self.target, capture=capture,
                                              folder=self.root / "preparation", facts=facts, as_of=as_of,
                                              deadline=self.commands.deadline, say=self.say,
                                              environment=self.env["worker"])
        cut = self.cut(capture)
        self.say(f"{self.source} {self.target}: {sum(len(b) for b in cut)} documents in {len(cut)} bundles, "
                 f"{self.at_a_time} at once")
        run_files = [*run_files, *self.derived_files(run_files, folder=self.root / "derived")]
        extra = [*(a for fact in facts for a in ("--fact", fact)), *(a for f in run_files for a in ("--file", f))]
        if force:
            # Force publish (operator, 2026-11-10): ignore the Change Journal and process every document of the source
            # again, as a new publication of this capture run; the journal records the run as forced.
            capture_run = f"{capture_run}+force-{re.sub(r'[^0-9]', '', as_of)}"
            extra.append("--all")
            self.say(f"Force publish: every document of {self.source} is processed again as run {capture_run}")
        folder = self.root / as_of.replace(":", "")
        result["bundles"] = self.at_once([
            (f"bundle {number}", lambda number=number, keys=keys: self.bundle(
                number, len(cut), keys, folder=folder, capture=capture, capture_run=capture_run, as_of=as_of,
                revision=revision, extra=extra))
            for number, keys in enumerate(cut, 1)])
        self.say(f"Done: {sum(b['new'] for b in result['bundles'])} documents loaded, "
                 f"{sum(b['documents'] - b['new'] for b in result['bundles'])} already loaded before")
        return result


def _handle(args) -> int:
    try:
        loader = Loader(source=args.source, target=args.target, stores=args.stores.expanduser(),
                        workers=args.workers, minutes=args.minutes, at_a_time=args.bundles)
        if args.plan:
            print(json.dumps(loader.plan(capture=args.capture.expanduser()), indent=1, sort_keys=True))
            return 0
        if not args.capture_run:
            raise RunStopped("--capture-run is required unless --plan")
        result = loader.load(capture=args.capture.expanduser(), capture_run=args.capture_run,
                             as_of=args.as_of or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                             facts=args.fact or [], run_files=args.file or [], revision=args.revision, force=args.force)
    except (RunStopped, ValueError) as error:
        print(f"Load stopped: {error}", file=sys.stderr)
        print("Run the same command again to carry on from here.", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "load", help="Load a captured delivery through one source's target, start to finish (safe to rerun)",
        description=__doc__.split("\n\n", 1)[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="The source, a folder under rules/sources/")
    parser.add_argument("--target", default="mastering", help="Its Bookkeeping target (default mastering)")
    parser.add_argument("--capture", required=True, type=Path, help="The capture folder (receipts.jsonl and its files)")
    parser.add_argument("--capture-run", help="The capture's approved run ID (not needed with --plan)")
    parser.add_argument("--plan", action="store_true",
                        help="Print what this load would do (runs it would finish or leave and why, documents, "
                             "bundles) and change nothing")
    parser.add_argument("--stores", required=True, type=Path,
                        help="The stores' environment folder, holding worker.env, verifier.env and governance.env")
    parser.add_argument("--workers", type=int, default=1, help="Worker processes on each step of a run (one verifier a run)")
    parser.add_argument("--bundles", type=int, default=1,
                        help="Bundles loaded at once, each its own run with its own verifier (default 1)")
    parser.add_argument("--minutes", type=float, default=120, help="Stop after this long; rerun to carry on")
    parser.add_argument("--as-of", help="The load's time, UTC (YYYY-MM-DDTHH:MM:SSZ); default now")
    parser.add_argument("--revision", type=int, default=0,
                        help="The source publication's order (default 0): a delivery whose inputs changed (a new Name "
                             "Count, say) is a new publication and needs a higher revision than the one loaded before")
    parser.add_argument("--force", action="store_true",
                        help="Force publish: ignore the Change Journal and process every document of the source again, "
                             "as a new publication of the capture run (the journal records it as forced). Use it when "
                             "the result must be made again whatever the journal holds")
    parser.add_argument("--fact", action="append", help="A run fact the target declares: name=value (repeat)")
    parser.add_argument("--file", action="append", help="A run file the target declares: name=path (repeat)")
    parser.set_defaults(handler=_handle)
