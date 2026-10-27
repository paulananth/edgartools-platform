"""A rules version's test run, on this machine, from files already captured (ticket 14).

`rules test` runs one declared target of a source (`--target`, default `mastering`) as production runs
it: `rules run` submits it to Bookkeeping, each step's worker and verifier run as
their own processes with their own logins, and `bookkeeping finalize` closes the
run. It runs on the disposable local stores (`infra/scripts/local-test-stores.py
up <name>`), whose duty files name each login, and never on a store that already
holds MDM records. A second run names every document again: the Merge Stage must
change nothing. The report holds counts and digests only.

Inside those disposable stores the version is registered as a sandbox: a Rules
version holding only the source's Bookkeeping target, and the source's Dataset
Contracts and the Mastering Policy registered in MDM under a sandbox authority
that names the capture. Neither is an approval: the operator approves the real
version on this report (APPROVE.md).

The target's input manifest comes from the source's own declaration
(`target_manifest`, Bookkeeping section version 2): a source whose section
states no units and input is refused there.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine

from edgar_warehouse.mdm.clean.store import digest

from . import files
from .driving import Commands, RunStopped, duties, manifest_root

TARGET = "mastering"

# A test run's stop is the run driver's: one error the command line reports.
TestRunError = RunStopped


def sandbox_authority(source: str, code: str, contract: dict, capture_sha256: str) -> dict:
    """The authority a disposable MDM registers a Dataset Contract under: it names the
    capture the test reads, and says it is a sandbox. Never an approval."""
    name = f"rules-test.{source}"
    feed = {"family": contract["family"], "datasets": [code], "scope": ["rules-test"],
            "capabilities": {"capture": "provider.capture", "fetch": "http.conditional"},
            "completeness": {"format": "json", "required": [], "allow_empty": True, "max_bytes": 1024},
            "required_producers": ["rules-test"], "url_prefixes": ["https://rules-test.invalid/"]}
    document = {"source": name, "acquisition": {"version": 1, "feeds": {"capture": feed}},
                "mdm": {code: {"contract": contract}}}
    content = digest(document)
    proof = {"passed": True, "digest": content, "acquisition": {"capture": {
        "manifest": {"uri": "file:///rules-test/capture-receipts.json", "sha256": capture_sha256},
        "counts": {"rules-test": {"expected": 0, "verified": 0}}, "checks": {"rules-test": True}}}}
    return {"kind": "source", "name": name, "version": "sandbox", "digest": content, "body": document,
            "status": "active", "proof": proof,
            "approval": {"digest": content, "by": "rules-test sandbox", "at": "1970-01-01T00:00:00Z"}}


def _records_md5(engine) -> str:
    """The governed current-record byte digest; historical SQL hashes remain historical."""
    return counts(engine)["current_records_md5"]


def counts(engine) -> dict:
    """Count the governed store on one snapshot, through its indexed record pages."""
    from edgar_warehouse.mdm.clean.inspection import counts as inspect_counts

    return inspect_counts(engine)


def quality(folder: Path, mdm) -> dict:
    """What the data quality rule did to one pass's prepared records, per fix, flag, withheld value
    and exception: the Merge Stage's own reader (`batch_input`) and its count (`quality.counts`)."""
    from edgar_warehouse.mdm.clean.execution import batch_input
    from edgar_warehouse.mdm.clean.quality import counts as quality_counts
    from edgar_warehouse.mdm.clean.store import Store

    manifest = json.loads((folder / "manifest.json").read_text())
    assertions, deferred = [], []
    for batch in manifest["batches"]:
        found = batch_input(batch, folder, Store(mdm), policy_digest=manifest["policy_digest"])
        assertions += found["assertions"]
        deferred += found["deferred"]
    return quality_counts(assertions, deferred)


def recording(source: str, version: str, document: dict, sandbox: str):
    """The operator's Rules Database to record this test run in, checked before the run: the saved
    version is the rules on disk. A source that declares acquisition records its test run too: it
    switches on the pipes over captured data, and its live acquisition is proved apart (operator,
    2026-10-19)."""
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import ArgumentError

    from edgar_warehouse.control_contract import Blocked

    from .db import Rules

    url = os.environ.get("RULES_DATABASE_URL")
    if not url:
        raise TestRunError("Set RULES_DATABASE_URL to the operator's Rules Database in your own terminal to record")
    def place(address):
        try:
            found = make_url(address)
        except ArgumentError:
            return address
        return found.host, found.port, found.database

    if place(url) == place(sandbox):
        raise TestRunError("The local stores' Rules Database is the test's sandbox; record into the operator's")
    rules = Rules(create_engine(url))
    try:
        saved = rules.version("source", source, version)
    except Blocked as error:
        raise TestRunError(f"{source} has no saved version {version}: save it first (`rules save`)") from error
    if saved["digest"] != digest(document):
        raise TestRunError(f"Version {version} is not the rules on disk: save the files tested, or test that version")
    return rules


def record(rules, result: dict, *, source: str, version: str) -> dict:
    """The report as the version's test run (`Rules.prove`): passing or not, with its counts."""
    proof = {"digest": result["rules_digest"], "batch_hash": result["batch_hash"], "passed": result["passed"],
             "evidence": {key: result[key] for key in ("passes", "second_pass_changed_nothing", "capture",
                                                       "policy_digest", "contract_digests", "target",
                                                       "run_inputs")},
             "note": result["test_run"]}
    from edgar_warehouse.control_contract import Blocked

    try:
        rules.prove("source", source, version, proof)
    except Blocked as error:
        raise TestRunError(f"The test run was not recorded: {error}") from error
    return proof


def run(*, source: str, capture: Path, documents: Path, capture_run: str, as_of: str, stores: Path,
        out: Path, minutes: float = 60, target: str = TARGET, version: str | None = None,
        facts: dict | None = None, run_files: dict | None = None) -> dict:
    """Two runs of one of the source's targets (default `mastering`) on the capture; the report, written to `out`."""
    from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
    from edgar_warehouse.change_journal.store import ChangeJournal
    from edgar_warehouse.mdm.clean.store import register_dataset, register_policy
    from edgar_warehouse.mdm.clean.target_manifest import write_manifest
    from edgar_warehouse.rules.db import Rules

    env = duties(stores)
    document = files.source(source)
    declared = ((document.get("bookkeeping") or {}).get("targets") or {}).get(target)
    if declared is None:
        raise TestRunError(f"{source} declares no `{target}` target in its source.yaml")
    from edgar_warehouse.mdm.clean.target_manifest import plan

    try:
        plan(document, target)  # the declaration the writer will read, refused before any store is touched
    except ValueError as error:
        raise TestRunError(str(error)) from error
    prepare = next((step for step in declared["steps"] if step["operation"] == "mdm.prepare"), None)
    code = ((prepare or {}).get("input") or {}).get("keys", {}).get("dataset")
    if code not in (document.get("mdm") or {}):
        raise TestRunError(f"Target {target} prepares none of {source}'s Dataset Contracts")
    recorder = recording(source, version, document, env["governance"]["RULES_DATABASE_URL"]) if version else None
    mdm = create_engine(env["governance"]["RULES_MDM_ACTIVATION_DATABASE_URL"])
    rules_engine = create_engine(env["governance"]["RULES_DATABASE_URL"])
    journal_engine = create_engine(env["worker"]["CHANGE_JOURNAL_DATABASE_URL"])
    # Another run a step reads (ticket 120) is one in the test's own stores.
    bookkeeping = Bookkeeping(create_engine(env["worker"]["BOOKKEEPING_DATABASE_URL"]))
    try:
        held = counts(mdm)
        if any(held[part] for part in ("masters", "stage_records", "set_aside")):
            raise TestRunError("The MDM store already holds records: test on fresh stores "
                               "(local-test-stores.py copy <name> restores the empty baseline)")
        receipts = capture / "receipts.jsonl"
        if not receipts.is_file():
            raise TestRunError(f"{receipts} is missing: a capture names each of its files in receipts.jsonl")
        capture_sha = hashlib.sha256(receipts.read_bytes()).hexdigest()
        policy = files.policy()
        with mdm.begin() as conn:  # the sandbox registration: never an approval
            policy_digest = register_policy(conn, policy)
            for code, entry in (document.get("mdm") or {}).items():
                register_dataset(conn, code, entry["contract"],
                                 rules_authority=sandbox_authority(source, code, entry["contract"], capture_sha))
        rules = Rules(rules_engine)
        name, sandbox_version = f"rules-test.{source}.{uuid4().hex[:8]}", "1"
        body = {"source": name, "bookkeeping": document["bookkeeping"]}
        root = manifest_root(env) / name
        journal = ChangeJournal(journal_engine)
        commands = Commands(env, (root / "reports").as_uri(), deadline=time.monotonic() + minutes * 60,
                             log=stores / "rules-test-errors.log")
        passes = []
        for number, force in ((1, False), (2, True)):
            began = time.monotonic()
            try:
                report = write_manifest(source=source, target=target, capture=str(capture), documents=str(documents),
                                        capture_run=capture_run, output=str(root / f"pass-{number}"),
                                        as_of=as_of, revision=0, force=force, journal=journal,
                                        facts=facts, run_files=run_files, bookkeeping=bookkeeping)
            except ValueError as error:  # the declaration or the bundle refused: a stop, not a traceback
                raise TestRunError(str(error)) from error
            if report["manifest"] is None:
                raise TestRunError("Every document is recorded as processed already: nothing to test")
            if number == 1:
                saved = rules.save("source", name, sandbox_version, body)
                rules.prove("source", name, sandbox_version, {"digest": saved["digest"], "passed": True,
                                                             "batch_hash": report["manifest"]["sha256"]})
                rules.activate("source", name, sandbox_version)
            output = commands("worker", "rules", "run", "--source", name, "--target", target,
                              "--input-manifest", report["manifest"]["uri"],
                              "--input-sha256", report["manifest"]["sha256"])
            run_id = str(json.loads(output)["run"]["run_id"])
            final = commands.drive(run_id, declared["steps"])
            if final["run"]["state"] != "complete":
                raise TestRunError(f"pass {number} ended {final['run']['state']}, not complete")
            held = counts(mdm)
            passes.append({"run_counts": final.get("counts"), "mdm": held,
                           # A held-back record is set aside and has a review: count it once.
                           "records_in_mdm": sum(sum(held[part].values()) for part in ("stage_records", "set_aside")),
                           "manifest_sha256": report["manifest"]["sha256"],
                           "quality": quality(root / f"pass-{number}" / prepare["name"], mdm),
                           "seconds": round(time.monotonic() - began, 1)})
        result = {
            "test_run": f"{source}, target {target}, on a local capture",
            "target": target,
            "source": source,
            "rules_digest": digest(document),
            "batch_hash": passes[0]["manifest_sha256"],
            "policy_digest": policy_digest,
            "contract_digests": {code: digest(entry["contract"]) for code, entry in (document.get("mdm") or {}).items()},
            # The run's own inputs: each fact, and each file by its sha256.
            "run_inputs": {"facts": dict(facts or {}), "files": {
                name: hashlib.sha256(Path(path).read_bytes()).hexdigest() for name, path in (run_files or {}).items()}},
            "capture": {"receipts_sha256": capture_sha, "documents_sha256": hashlib.sha256(documents.read_bytes()).hexdigest(),
                        "capture_run": capture_run},
            "passes": passes,
            "second_pass_changed_nothing": passes[0]["mdm"] == passes[1]["mdm"],
            # Passed: records reached MDM, no identifier sits on two masters, and the second
            # pass changed nothing. How many bind or wait is the evidence the operator reads.
            "passed": passes[0]["records_in_mdm"] > 0 and passes[0]["mdm"] == passes[1]["mdm"]
                      and not any(passes[0]["mdm"]["identifiers_on_two_masters"].values()),
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")  # the evidence first, recorded or not
        if recorder is not None:
            record(recorder, result, source=source, version=version)
            result["recorded"] = {"version": version}
            out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
        return result
    finally:
        for engine in (mdm, rules_engine, journal_engine, bookkeeping.engine,
                       *([recorder.engine] if recorder else [])):
            engine.dispose()

