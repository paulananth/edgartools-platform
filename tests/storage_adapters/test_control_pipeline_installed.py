"""Installed Rules submission, real worker processes and controller handoffs."""
from contextlib import ExitStack
import json
import os

import pytest
from sqlalchemy import text

from tests.engine.test_data_skill_bundle_postgres import installed, _run  # noqa: F401
from tests.integration.test_configured_bookkeeping_postgres import config
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts

pytestmark = pytest.mark.skipif(os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql",
                                reason="Full SQL Server control lifecycle follows PostgreSQL/MySQL")


def test_installed_rules_and_real_workers_complete_and_resume_one_run(installed, database_factory):
    python, root = installed
    with ExitStack() as stack:
        _, _, approval_role = stack.enter_context(database_factory())
        _, reader, reader_role = stack.enter_context(database_factory())
        rules_owner, rules_runtime, rules_role = stack.enter_context(database_factory())
        owner, worker, role = stack.enter_context(database_factory())
        journal_owner, journal, journal_role = stack.enter_context(database_factory())
        env = {"RULES_MIGRATION_DATABASE_URL": rules_owner.url.render_as_string(hide_password=False),
               "RULES_DATABASE_URL": rules_runtime.url.render_as_string(hide_password=False),
               "RULES_MDM_ACTIVATION_DATABASE_URL": "",
               "BOOKKEEPING_MIGRATION_DATABASE_URL": owner.url.render_as_string(hide_password=False),
               "BOOKKEEPING_DATABASE_URL": worker.url.render_as_string(hide_password=False),
               "BOOKKEEPING_MANIFEST_ROOT": (root / "runs").as_uri(),
               "CHANGE_JOURNAL_MIGRATION_DATABASE_URL": journal_owner.url.render_as_string(hide_password=False),
               "CHANGE_JOURNAL_DATABASE_URL": journal.url.render_as_string(hide_password=False)}
        def command(*args, verifier=False, report=True):
            selected = {**env, **({"BOOKKEEPING_DATABASE_URL": reader.url.set(database=owner.url.database).render_as_string(hide_password=False)} if verifier else {})}
            result = _run(python, "-m", "edgar_warehouse.cli", *args, env=selected, cwd=root)
            if result.returncode:
                (root / "private-control-pipeline.log").write_text(result.stdout + "\n" + result.stderr)
            assert result.returncode == 0, "Installed pipeline failed; private diagnostic retained"
            return json.loads(result.stdout) if report else None
        command("rules", "init", "--agent-role", rules_role, "--approver-role", approval_role, "--database-name", rules_owner.url.database)
        command("bookkeeping", "init", "--runtime-role", role, "--database-name", owner.url.database)
        command("bookkeeping", "migrate", "--runtime-role", reader_role, "--database-name", owner.url.database)
        command("change-journal", "init", "--runtime-role", journal_role, "--database-name", journal_owner.url.database)
        with owner.connect() as conn:
            known = set(conn.scalars(text("SELECT User FROM mysql.user" if owner.dialect.name == "mysql" else "SELECT rolname FROM pg_roles")))
        groups = []
        try:
            for profile in ("artifact.copy", "jsonl.count"):
                granted = command("bookkeeping", "grant-profile", "--profile", profile, "--worker", role, "--verifier", reader_role)
                groups += [item["role"] for item in granted.values() if item["role"] not in known]
            body = config(steps=2)
            body["bookkeeping"]["targets"]["silver"]["steps"][1]["operation"] = "jsonl.count"
            path = root / "pipeline.json"
            path.write_text(json.dumps(body))
            artifacts = Artifacts()
            source = artifacts.put(root.as_uri() + "/inputs", {"invented": 10**50})
            copied, counted = (root / "copied.json").as_uri(), (root / "counted.json").as_uri()
            inputs = artifacts.put(root.as_uri() + "/manifests", {"version": 2, "steps": {
                "s0": [{"keys": {"id": "0", "destination": copied}, "input": source, "output": copied, "cursor": {}}],
                "s1": [{"keys": {"id": "0", "destination": counted}, "input": {"from": {"step": "s0", "key": "0"}}, "output": counted, "cursor": {}}]}})
            selection = ["--pipeline", "invented.installed-control"]
            saved = command("rules", "save", *selection, "--version", "v1", str(path))
            proof = artifacts.put(root.as_uri() + "/proof", {"digest": saved["digest"], "passed": True, "batch_hash": inputs["sha256"]})
            command("rules", "record-proof", *selection, "--version", "v1", "--proof-uri", proof["uri"], "--proof-sha256", proof["sha256"])
            evidence = command("rules", "pending")[0]["evidence_hash"]
            command("rules", "approve", *selection, "--version", "v1", "--evidence", evidence, "--by", "invented operator", "--words", "Approve the tested pipeline")
            command("rules", "activate", *selection, "--version", "v1")
            run = command("rules", "run", *selection, "--target", "silver", "--input-manifest", inputs["uri"], "--input-sha256", inputs["sha256"])
            rid = run["run"]["run_id"]
            for profile in ("artifact.copy", "jsonl.count"):
                command("workers", "work", profile, rid, report=False)
                command("workers", "verify", profile, rid, "--reports", (root / "reports").as_uri(), verifier=True, report=False)
            final = command("bookkeeping", "finalize", rid)
            assert final["run"]["state"] == "complete" and final["counts"] == {"verified": 2}
            assert command("change-journal", "status")["events"] == 2
            command("rules", "run", *selection, "--target", "silver", "--resume-run-id", rid)
            for profile in ("artifact.copy", "jsonl.count"):
                command("workers", "work", profile, rid, report=False)
            assert command("bookkeeping", "finalize", rid)["counts"] == {"verified": 2}
            assert command("change-journal", "status")["events"] == 2
        finally:
            with owner.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                for group in groups:
                    principal = "'" + group + "'@'%'" if owner.dialect.name == "mysql" else conn.dialect.identifier_preparer.quote(group)
                    conn.execute(text("DROP ROLE " + principal))
