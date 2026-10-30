"""Three control-only wheels, normal CLI and two external workload profiles."""
import json
import os
import subprocess

import pytest
from sqlalchemy import text

from tests.integration.test_bookkeeping_wheel_postgres import control_python, DOMAIN  # noqa: F401
from tests.integration.test_configured_bookkeeping_postgres import config
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.control_contract import digest
from edgar_warehouse.workers import copy, count
from edgar_warehouse.workers.control import report_document

pytestmark = pytest.mark.skipif(os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql",
                                reason="Full SQL Server control lifecycle follows PostgreSQL/MySQL")


def test_independent_installed_control_cli_from_empty_stores(control_python, database_factory, tmp_path):
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
            with database_factory() as (journal_owner, journal_runtime, journal_role):
                if owner.dialect.name == "mysql":
                    wheel = next((root / "dist").glob("edgartools_bookkeeping-*.whl"))
                    added = subprocess.run(["uv", "pip", "install", "--python", str(python),
                                            "edgartools-bookkeeping[mysql] @ " + wheel.as_uri()],
                                           capture_output=True, text=True, timeout=60)
                    assert added.returncode == 0, "Declared MySQL control extra failed to install"
                def url(engine):
                    return engine.url.set(drivername=engine.dialect.name).render_as_string(hide_password=False)
                environment = {**os.environ, "BOOKKEEPING_MIGRATION_DATABASE_URL": url(owner),
                               "CHANGE_JOURNAL_MIGRATION_DATABASE_URL": url(journal_owner),
                               "CHANGE_JOURNAL_DATABASE_URL": url(journal_runtime)}
                reader_url = reader.url.set(database=owner.url.database, drivername=owner.dialect.name).render_as_string(hide_password=False)
                def invoke(*arguments, document=None, verifier=False, expected=0, module="edgar_warehouse.bookkeeping"):
                    result = subprocess.run([str(python), "-I", "-m", module, *arguments],
                                            input=None if document is None else json.dumps(document), capture_output=True,
                                            text=True, cwd=tmp_path, timeout=30,
                                            env={**environment, "BOOKKEEPING_DATABASE_URL": reader_url if verifier else url(worker)})
                    if result.returncode != expected:
                        (tmp_path / "private-installed-control.log").write_text(result.stdout + "\n" + result.stderr)
                    assert result.returncode == expected, "Installed control failed; private diagnostic retained"
                    return json.loads(result.stdout)
                invoke("init", "--runtime-role", role, "--database-name", owner.url.database)
                invoke("migrate", "--runtime-role", reader_role, "--database-name", owner.url.database)
                invoke("init", "--runtime-role", journal_role, "--database-name", journal_owner.url.database,
                       module="edgar_warehouse.change_journal.cli")
                granted = []
                with owner.connect() as conn:
                    known = set(conn.scalars(text("SELECT User FROM mysql.user" if owner.dialect.name == "mysql" else "SELECT rolname FROM pg_roles")))
                try:
                    for profile in ("artifact.copy", "jsonl.count"):
                        groups = invoke("grant-profile", "--profile", profile, "--worker", role, "--verifier", reader_role)
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
                        "body": body, "digest": digest(body), "status": "active", "approval": None,
                        "proof": {"digest": digest(body), "batch_hash": inputs["sha256"], "passed": True}})
                    start = subprocess.run([str(python), "-I", "-c", '''
import json,sys
from edgar_warehouse.bookkeeping.clean.database import get_engine
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
rules,inputs=json.load(sys.stdin)
book=Bookkeeping(get_engine())
try: print(json.dumps(book.start(rules_ref=rules,inputs_ref=inputs,target="silver",scope={})))
finally: book.close()
'''], input=json.dumps([rules, inputs]), capture_output=True, text=True, timeout=30, cwd=tmp_path,
                        env={**environment, "BOOKKEEPING_DATABASE_URL": url(worker)})
                    if start.returncode:
                        (tmp_path / "private-installed-control.log").write_text(start.stdout + "\n" + start.stderr)
                    assert start.returncode == 0, "Installed start failed; private diagnostic retained"
                    run_id = json.loads(start.stdout)
                    for profile, workload in (("artifact.copy", copy), ("jsonl.count", count)):
                        envelopes = invoke("claim", run_id, "--profile", profile)
                        assert len(envelopes) == 1
                        for envelope in envelopes:
                            candidate = workload.execute(envelope, artifacts)
                            invoke("report", "--envelope", "-", "--candidate", candidate["uri"], "--sha256", candidate["sha256"],
                                   "--runtime", "a" * 64, document=envelope)
                        for verification in invoke("verifications", run_id, "--profile", profile, verifier=True):
                            checks, proofs = workload.verify(verification, artifacts)
                            report = artifacts.put(tmp_path.as_uri() + "/reports", report_document(verification, checks, proofs, "b" * 64))
                            invoke("admit", "--verification", "-", "--report", report["uri"], "--sha256", report["sha256"],
                                   document=verification, verifier=True)
                    final = invoke("finalize", run_id)
                    assert final["run"]["state"] == "complete" and final["counts"] == {"verified": 2}
                    assert invoke("finalize", run_id) == final
                    assert invoke("resume", run_id, expected=3)["run"]["state"] == "running"
                    assert invoke("finalize", run_id)["run"]["state"] == "complete"
                    assert json.loads(artifacts.verified({"uri": counted, "sha256": final["items"][1]["receipt"]["sha256"]})) == {"lines": 1}
                    invoke("migrate", "--runtime-role", role, "--database-name", owner.url.database)
                finally:
                    with owner.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                        for group in granted:
                            principal = "'" + group + "'@'%'" if owner.dialect.name == "mysql" else conn.dialect.identifier_preparer.quote(group)
                            conn.execute(text("DROP ROLE " + principal))
