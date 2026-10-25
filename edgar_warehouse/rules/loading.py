"""`edgar-warehouse load`: load a captured delivery through one source's target (ticket 136).

One command for every source and target, with nothing named after either:

1. Finish first: a run of this source and target that is still running or waiting
   is driven to the end before anything new is submitted.
2. The documents are the capture's receipts the target reads: those matching its
   first step's `files` pattern (all of them when it names none).
3. They are cut into bundles of the source's `execution.max_artifacts`. Each bundle
   is prepared (`mdm prepare-capture`: the Change Journal leaves out what is already
   processed under these rules), submitted (`rules run`) and driven to `complete`.

Stopping is safe: run the same command again and it carries on where it stopped.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean import raw_capture

from . import files
from .driving import Commands, RunStopped, duties, manifest_root

OPEN = ("running", "waiting")


def documents(reading: dict, target: str, capture: Path) -> list[str]:
    """The capture's receipt keys the target's first step reads, in key order."""
    steps = reading["bookkeeping"]["targets"][target]["steps"]
    pattern = (steps[0].get("input") or {}).get("files", "*") if steps else "*"
    _, receipts = raw_capture.receipts(capture)
    return sorted(key for key in receipts if fnmatch.fnmatchcase(key, pattern))


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


class Loader:
    """One source's target over one capture, on the stores one environment folder names."""

    def __init__(self, *, source: str, target: str, stores: Path, workers: int, minutes: float,
                 say=lambda line: print(line, file=sys.stderr, flush=True)):
        self.source, self.target, self.say = source, target, say
        self.reading = target_of(source, target)
        self.runtimes: dict[str, str] = {}
        env = duties(stores)
        self.root = manifest_root(env) / "load" / source / target
        self.commands = Commands(env, (self.root / "reports").as_uri(), deadline=time.monotonic() + minutes * 60,
                                 log=stores / "load-errors.log", workers=workers)

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
        active = next((v["version"] for v in listed if v.get("status") == "active"), None)
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
        frozen = Artifacts().json(submission["rules"])["body"]["bookkeeping"]["targets"][self.target]["steps"]
        began = time.monotonic()
        final = self.commands.drive(run_id, frozen)
        state = final["run"]["state"]
        if state != "complete":
            raise RunStopped(f"Run {run_id} ended {state}, not complete; its checks: {final['run'].get('checks')}")
        self.say(f"  run {run_id} complete in {round((time.monotonic() - began) / 60, 1)} min")
        return final

    def load(self, *, capture: Path, capture_run: str, as_of: str, facts: list[str], run_files: list[str]) -> dict:
        result = {"source": self.source, "target": self.target, "finished_open_runs": [], "bundles": []}
        unfinished, result["left_as_they_are"] = self.open_runs()
        for run_id, why in result["left_as_they_are"].items():
            self.say(f"Run {run_id} is left as it is: {why}")
        for run_id in unfinished:
            self.say(f"Finishing run {run_id}, left open before")
            self.drive(run_id)
            result["finished_open_runs"].append(run_id)
        keys = documents(self.reading, self.target, capture)
        cut = bundles(keys, self.reading["execution"]["max_artifacts"])
        self.say(f"{self.source} {self.target}: {len(keys)} documents in {len(cut)} bundles")
        folder = self.root / as_of.replace(":", "")
        for number, bundle in enumerate(cut, 1):
            where = folder / f"bundle-{number:03d}"
            where.mkdir(parents=True, exist_ok=True)
            (where / "documents.json").write_text(json.dumps(bundle))
            extra = [*(a for fact in facts for a in ("--fact", fact)), *(a for f in run_files for a in ("--file", f))]
            prepared = json.loads(self.commands(
                "worker", "mdm", "prepare-capture", "--source", self.source, "--target", self.target,
                "--capture", str(capture), "--documents", str(where / "documents.json"), "--capture-run", capture_run,
                "--as-of", as_of, "--revision", "0", "--output", str(where / "manifest"), *extra))
            fresh = prepared["scope"]["documents"]
            entry = {"bundle": number, "documents": len(bundle), "new": fresh, "run_id": None}
            if prepared["manifest"] is None:
                self.say(f"Bundle {number}/{len(cut)}: all {len(bundle)} documents already loaded")
            else:
                self.say(f"Bundle {number}/{len(cut)}: {fresh} of {len(bundle)} documents to load")
                submitted = json.loads(self.commands(
                    "worker", "rules", "run", "--source", self.source, "--target", self.target,
                    "--input-manifest", prepared["manifest"]["uri"], "--input-sha256", prepared["manifest"]["sha256"]))
                entry["run_id"] = str(submitted["run"]["run_id"])
                entry["counts"] = self.drive(entry["run_id"]).get("counts")
            result["bundles"].append(entry)
        self.say(f"Done: {sum(b['new'] for b in result['bundles'])} documents loaded, "
                 f"{sum(b['documents'] - b['new'] for b in result['bundles'])} already loaded before")
        return result


def _handle(args) -> int:
    try:
        loader = Loader(source=args.source, target=args.target, stores=args.stores.expanduser(),
                        workers=args.workers, minutes=args.minutes)
        result = loader.load(capture=args.capture.expanduser(), capture_run=args.capture_run,
                             as_of=args.as_of or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                             facts=args.fact or [], run_files=args.file or [])
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
    parser.add_argument("--capture-run", required=True, help="The capture's approved run ID")
    parser.add_argument("--stores", required=True, type=Path,
                        help="The stores' environment folder, holding worker.env, verifier.env and governance.env")
    parser.add_argument("--workers", type=int, default=1, help="Worker processes on each step (one verifier)")
    parser.add_argument("--minutes", type=float, default=120, help="Stop after this long; rerun to carry on")
    parser.add_argument("--as-of", help="The load's time, UTC (YYYY-MM-DDTHH:MM:SSZ); default now")
    parser.add_argument("--fact", action="append", help="A run fact the target declares: name=value (repeat)")
    parser.add_argument("--file", action="append", help="A run file the target declares: name=path (repeat)")
    parser.set_defaults(handler=_handle)
