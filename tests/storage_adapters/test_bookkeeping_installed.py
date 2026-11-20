"""Three control-only wheels, normal CLI and two external workload profiles."""
import json
import os
import subprocess

import pytest
from sqlalchemy import inspect, text

from tests.integration.test_bookkeeping_wheel_postgres import control_python, DOMAIN  # noqa: F401
from tests.integration.test_configured_bookkeeping_postgres import config
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.control_contract import digest
from edgar_warehouse.workers import copy, count
from edgar_warehouse.workers.control import report_document

pytestmark = pytest.mark.skipif(os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql",
                                reason="Full SQL Server control lifecycle follows PostgreSQL/MySQL")


def test_independent_installed_control_cli_from_empty_stores(control_python, database_factory, store_databases, tmp_path):
    python = control_python
    root = python.parents[2]
    probe = subprocess.run([str(python), "-I", "-c", f'''
import importlib.metadata
names = {{d.metadata["Name"].lower() for d in importlib.metadata.distributions()}}
assert not names & set({DOMAIN!r})
'''], capture_output=True, text=True, cwd=tmp_path, timeout=20)
    assert probe.returncode == 0, "Control installation has a workload dependency"
    with database_factory() as (_, reader, reader_role):
        with database_factory() as (owner, worker, role):
            # Bookkeeping and the journal share the control database; on MySQL each keeps its own (control_<store>). One login.
            mine = ("control",) if owner.dialect.name != "mysql" else ("control_bookkeeping", "control_change_journal")
            with store_databases(owner, *mine) as (prefix, stores):
                if owner.dialect.name == "mysql":
                    wheel = next((root / "dist").glob("edgartools_bookkeeping-*.whl"))
                    added = subprocess.run(["uv", "pip", "install", "--python", str(python),
                                            "edgartools-bookkeeping[mysql] @ " + wheel.as_uri()],
                                           capture_output=True, text=True, timeout=60)
                    assert added.returncode == 0, "Declared MySQL control extra failed to install"
                control = prefix + "control"

                def url(engine):  # a duty file's control URL: the login's, naming the control database
                    return engine.url.set(drivername=engine.dialect.name, database=control).render_as_string(hide_password=False)
                environment = {k: v for k, v in os.environ.items() if k not in ("DATA_URL", "CONTROL_URL")}
                journal_owner, journal_runtime, journal_role = stores[mine[-1]], worker, role
                reader_url = url(reader)
                def invoke(*arguments, document=None, verifier=False, expected=0, module="edgar_warehouse.bookkeeping"):
                    owner_command = arguments[0] in {"init", "grant-profile"}
                    owner_login = url(owner)
                    result = subprocess.run([str(python), "-I", "-m", module, *arguments],
                                            input=None if document is None else json.dumps(document), capture_output=True,
                                            text=True, cwd=tmp_path, timeout=30,
                                            env={**environment, "CONTROL_URL": owner_login if owner_command else (reader_url if verifier else url(worker))})
                    if result.returncode != expected:
                        (tmp_path / "private-installed-control.log").write_text(result.stdout + "\n" + result.stderr)
                    assert result.returncode == expected, "Installed control failed; private diagnostic retained"
                    return json.loads(result.stdout)
                invoke("init", "--runtime-role", role)
                invoke("init", "--runtime-role", reader_role)
                invoke("init", "--runtime-role", journal_role,
                       module="edgar_warehouse.change_journal.cli")
                granted = []
                with owner.connect() as conn:
                    known = set(conn.scalars(text("SELECT User FROM mysql.user" if owner.dialect.name == "mysql" else "SELECT rolname FROM pg_roles")))
                try:
                    for profile in ("artifact.copy", "jsonl.count"):
                        groups = invoke("grant-profile", "--profile", profile, "--worker", role)
                        granted.extend(item["role"] for item in groups.values() if item["role"] not in known)
                    artifacts = Artifacts()
                    body = config(steps=2)
                    body["bookkeeping"]["targets"]["silver"]["steps"][1]["operation"] = "jsonl.count"
                    source = artifacts.put(tmp_path.as_uri() + "/inputs", {"invented": 10**50})
                    copied, counted = (tmp_path / "copy.json").as_uri(), (tmp_path / "count.json").as_uri()
                    inputs = artifacts.put(tmp_path.as_uri() + "/manifests", {"version": 2, "steps": {
                        "s0": [{"keys": {"id": "0", "destination": copied}, "input": source, "output": copied, "cursor": {}}],
                        "s1": [{"keys": {"id": "0", "destination": counted}, "input": {"from": {"step": "s0", "key": "0"}},
                                "output": counted, "cursor": {}}]}})
                    rules = artifacts.put(tmp_path.as_uri() + "/rules", {"kind": "pipeline", "name": "invented.installed", "version": "v1",
                        "body": body, "digest": digest(body)})
                    start = subprocess.run([str(python), "-I", "-c", '''
import json,sys
from edgar_warehouse.bookkeeping.clean.database import get_engine
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
rules,inputs=json.load(sys.stdin)
book=Bookkeeping(get_engine())
try: print(json.dumps(book.start(rules_ref=rules,inputs_ref=inputs,target="silver",scope={})))
finally: book.close()
'''], input=json.dumps([rules, inputs]), capture_output=True, text=True, timeout=30, cwd=tmp_path,
                        env={**environment, "CONTROL_URL": url(worker)})
                    if start.returncode:
                        (tmp_path / "private-installed-control.log").write_text(start.stdout + "\n" + start.stderr)
                    assert start.returncode == 0, "Installed start failed; private diagnostic retained"
                    run_id = json.loads(start.stdout)
                    for profile, workload in (("artifact.copy", copy), ("jsonl.count", count)):
                        envelopes = invoke("claim", run_id, "--profile", profile)
                        assert len(envelopes) == 1
                        for envelope in envelopes:
                            candidate = workload.execute(envelope, artifacts)
                            candidate = {"uri": candidate["uri"], "sha256": candidate["sha256"]}
                            checks, proofs = workload.check({**envelope, "candidate": candidate}, artifacts)
                            report = artifacts.put(tmp_path.as_uri() + "/reports", report_document(envelope, candidate, checks, proofs, "a" * 64))
                            invoke("report", "--envelope", "-", "--candidate", candidate["uri"], "--sha256", candidate["sha256"],
                                   "--checks", report["uri"], "--checks-sha256", report["sha256"], document=envelope)
                    final = invoke("finalize", run_id)
                    assert final["run"]["state"] == "complete" and final["counts"] == {"verified": 2}
                    assert invoke("finalize", run_id) == final
                    assert invoke("resume", run_id, expected=3)["run"]["state"] == "running"
                    assert invoke("finalize", run_id)["run"]["state"] == "complete"
                    assert json.loads(artifacts.verified({"uri": counted, "sha256": final["items"][1]["receipt"]["sha256"]})) == {"lines": 1}
                    invoke("init", "--runtime-role", role)
                    with journal_owner.begin() as conn:
                        conn.execute(text("DROP TABLE journal.event CASCADE" if owner.dialect.name == "postgresql" else "DROP TABLE journal_event"))
                    refused = subprocess.run([str(python), "-I", "-m", "edgar_warehouse.change_journal.cli", "init",
                        "--runtime-role", journal_role],
                        capture_output=True, text=True, cwd=tmp_path, timeout=30, env={**environment, "CONTROL_URL": url(owner)})
                    assert refused.returncode != 0, "Installed Journal recreated missing history"
                    assert not inspect(journal_owner).has_table("event" if owner.dialect.name == "postgresql" else "journal_event",
                        schema="journal" if owner.dialect.name == "postgresql" else None)
                finally:
                    with owner.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                        for group in granted:
                            principal = "'" + group + "'@'%'" if owner.dialect.name == "mysql" else conn.dialect.identifier_preparer.quote(group)
                            conn.execute(text("DROP ROLE " + principal))
