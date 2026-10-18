"""A rules version's test run, on this machine, from files already captured (ticket 14).

`rules test` runs a source's declared `mastering` target the way production runs
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

This first version takes sources whose reading keeps each captured document
whole (`capture_prepare`); other sources need their target's input manifest
declared first (ticket 14, the generic writer).
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text

from edgar_warehouse.mdm.clean.store import digest

from . import files

TARGET = "mastering"
DUTIES = ("worker", "verifier", "governance")


class TestRunError(ValueError):
    """A test run that cannot start or did not complete, with the reason."""


def duties(stores: Path) -> dict[str, dict[str, str | None]]:
    """Each duty's connection settings, from the local stores' private env files, line by
    line: a key the file unsets is None, so no login leaks in from the caller's shell."""
    found = {}
    for duty in DUTIES:
        path = stores / f"{duty}.env"
        if not path.is_file():
            raise TestRunError(f"{path} is missing: start the stores with infra/scripts/local-test-stores.py up <name>")
        values = {}
        for number, line in enumerate(path.read_text().splitlines(), 1):
            try:
                parts = shlex.split(line)
                if parts and parts[0] == "unset":
                    values.update(dict.fromkeys(parts[1:]))
                elif parts and parts[0] == "export":
                    key, _, value = parts[1].partition("=")
                    values[key] = value
            except (ValueError, IndexError):
                raise TestRunError(f"{path} line {number} is not an export or unset line") from None
        found[duty] = values
    return found


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


def counts(engine) -> dict:
    """What MDM holds, as the Proving Runs count it: masters per kind, staged records per
    source, waiting and open reviews and set-aside records per reason, decisions, and
    identifier values on two masters. Counts only."""
    def grouped(sql):
        return {str(k): v for k, v in conn.execute(text(sql)).all() if v}
    with engine.connect() as conn:
        return {
            "masters": grouped("SELECT kind, count(*) FROM mdm.master_entity GROUP BY kind"),
            "stage_records": grouped("SELECT source_code, count(*) FROM mdm.stage_record GROUP BY 1"),
            "waiting": grouped("SELECT coalesce(reason,'(none)'), count(*) FROM mdm.stage_waiting GROUP BY 1"),
            "open_reviews": grouped("SELECT coalesce(body->>'reason','(none)'), count(*) FROM mdm.current_record "
                                    "WHERE object_type='review' AND body->'open'='true'::jsonb GROUP BY 1"),
            "set_aside": grouped("SELECT coalesce(body->>'reason','(none)'), count(*) FROM mdm.set_aside_record GROUP BY 1"),
            "decisions": grouped("SELECT operation, count(*) FROM mdm.decision GROUP BY 1"),
            "changes": grouped("SELECT 'batch_change', count(*) FROM mdm.batch_change "
                               "UNION ALL SELECT 'outbox', count(*) FROM mdm.outbox"),
            # Every current record's body, hashed: a rewrite moves it even when no count moves.
            "current_records_md5": conn.scalar(text(
                "SELECT md5(coalesce(string_agg(object_type || ':' || object_id || ':' || body::text, "
                "',' ORDER BY object_type, object_id), '')) FROM mdm.current_record")),
            "identifiers_on_two_masters": grouped(
                "SELECT n, count(*) FROM (SELECT n, v FROM mdm.current_record e, "
                "jsonb_each(e.body->'identifiers') i(n, vs), jsonb_array_elements_text(vs) v "
                "WHERE e.object_type='entity' AND coalesce(e.body->>'status','') <> 'alias' "
                "GROUP BY n, v HAVING count(DISTINCT e.object_id) > 1) t GROUP BY n"),
        }


class _Commands:
    """The platform's own commands, each run as its duty's login in its own process."""

    def __init__(self, env: dict[str, dict[str, str | None]], reports: str, *, deadline: float, log: Path):
        self.env, self.reports, self.deadline, self.log = env, reports, deadline, log

    def __call__(self, duty: str, *args: str) -> str:
        environment = {**os.environ, **self.env[duty]}
        environment = {key: value for key, value in environment.items() if value is not None}
        # The platform's command in its own process, on this interpreter: the same code.
        command = [sys.executable, "-c", "from edgar_warehouse.cli import main; raise SystemExit(main())"]
        try:
            done = subprocess.run([*command, *args], env=environment, capture_output=True, text=True,
                                  timeout=max(1.0, self.deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise TestRunError(f"{' '.join(args[:3])} did not finish before the deadline") from None
        if done.returncode not in (0, 3):
            # Its message can hold a login or an address: it goes to a private file, never the screen.
            self.log.parent.mkdir(parents=True, exist_ok=True)
            with os.fdopen(os.open(self.log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a") as out:
                out.write(f"$ {' '.join(args)}\n{done.stderr}\n")
            raise TestRunError(f"{' '.join(args[:3])} failed with status {done.returncode}; its message is in {self.log}")
        return done.stdout

    def status(self, run_id: str) -> dict:
        return json.loads(self("worker", "bookkeeping", "status", run_id, "--limit", "1000"))

    def drive(self, run_id: str, steps: list[dict]) -> dict:
        """Each step's worker, then its verifier, in step order, until nothing is left."""
        for step in steps:
            profile = step["operation"]
            while time.monotonic() < self.deadline:
                self("worker", "workers", "work", profile, run_id, "--limit", "100")
                self("verifier", "workers", "verify", profile, run_id, "--reports", self.reports, "--limit", "100")
                items = [i for i in self.status(run_id)["items"] if i["step"] == step["name"]]
                if items and all(i["state"] == "verified" for i in items):
                    break
                if any(i["state"] == "waiting" for i in items):
                    raise TestRunError(f"step {step['name']} is waiting: a unit failed its checks")
            else:
                raise TestRunError(f"step {step['name']} did not finish before the deadline")
        return json.loads(self("worker", "bookkeeping", "finalize", run_id))


def run(*, source: str, capture: Path, documents: Path, capture_run: str, as_of: str, stores: Path,
        out: Path, minutes: float = 60) -> dict:
    """Two runs of the source's `mastering` target on the capture; the report, written to `out`."""
    from edgar_warehouse.change_journal.store import ChangeJournal
    from edgar_warehouse.mdm.clean.capture_prepare import write_capture_manifest
    from edgar_warehouse.mdm.clean.store import register_dataset, register_policy
    from edgar_warehouse.rules.db import Rules

    env = duties(stores)
    document = files.source(source)
    target = ((document.get("bookkeeping") or {}).get("targets") or {}).get(TARGET)
    if target is None:
        raise TestRunError(f"{source} declares no `{TARGET}` target in its source.yaml")
    mdm = create_engine(env["governance"]["RULES_MDM_ACTIVATION_DATABASE_URL"])
    rules_engine = create_engine(env["governance"]["RULES_DATABASE_URL"])
    journal_engine = create_engine(env["worker"]["CHANGE_JOURNAL_DATABASE_URL"])
    try:
        with mdm.connect() as conn:
            if conn.scalar(text("SELECT (SELECT count(*) FROM mdm.stage_record) + (SELECT count(*) FROM mdm.current_record)")):
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
        name, version = f"rules-test.{source}.{uuid4().hex[:8]}", "1"
        body = {"source": name, "bookkeeping": document["bookkeeping"]}
        manifest_root = env["worker"]["BOOKKEEPING_MANIFEST_ROOT"]
        root = Path(manifest_root.removeprefix("file://")) / name
        journal = ChangeJournal(journal_engine)
        commands = _Commands(env, (root / "reports").as_uri(), deadline=time.monotonic() + minutes * 60,
                             log=stores / "rules-test-errors.log")
        passes = []
        for number, force in ((1, False), (2, True)):
            began = time.monotonic()
            report = write_capture_manifest(source=source, capture=str(capture), documents=str(documents),
                                            capture_run=capture_run, output=str(root / f"pass-{number}"),
                                            as_of=as_of, revision=0, force=force, journal=journal)
            if report["manifest"] is None:
                raise TestRunError("Every document is recorded as processed already: nothing to test")
            if number == 1:
                saved = rules.save("source", name, version, body)
                rules.prove("source", name, version, {"digest": saved["digest"], "passed": True,
                                                     "batch_hash": report["manifest"]["sha256"]})
                rules.activate("source", name, version)
            output = commands("worker", "rules", "run", "--source", name, "--target", TARGET,
                              "--input-manifest", report["manifest"]["uri"],
                              "--input-sha256", report["manifest"]["sha256"])
            run_id = str(json.loads(output)["run"]["run_id"])
            final = commands.drive(run_id, target["steps"])
            if final["run"]["state"] != "complete":
                raise TestRunError(f"pass {number} ended {final['run']['state']}, not complete")
            held = counts(mdm)
            passes.append({"run_counts": final.get("counts"), "mdm": held,
                           # A held-back record is set aside and has a review: count it once.
                           "records_in_mdm": sum(sum(held[part].values()) for part in ("stage_records", "set_aside")),
                           "seconds": round(time.monotonic() - began, 1)})
        result = {
            "test_run": f"{source}, target {TARGET}, on a local capture",
            "source": source,
            "rules_digest": digest(document),
            "policy_digest": policy_digest,
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
        out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
        return result
    finally:
        for engine in (mdm, rules_engine, journal_engine):
            engine.dispose()

