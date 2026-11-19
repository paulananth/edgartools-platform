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


def test_installed_rules_and_real_workers_complete_and_resume_one_run(installed, database_factory, store_databases):
    python, root = installed
    with ExitStack() as stack:
        _, reader, reader_role = stack.enter_context(database_factory())
        owner, worker, role = stack.enter_context(database_factory())
        # Each store is its own database, named for the store behind this test's prefix; one runtime login reaches them all.
        prefix, stores = stack.enter_context(store_databases(owner, "bookkeeping", "change_journal", "rules"))
        none = lambda engine: engine.url.set(database=None).render_as_string(hide_password=False)
        owner_url, worker_url = none(owner), none(worker)
        env = {"BOOKKEEPING_MANIFEST_ROOT": (root / "runs").as_uri(), "DB_PREFIX": prefix}
        def command(*args, verifier=False, report=True):
            selected = {**env, "DB_URL": worker_url}
            if args[:2] in (("rules", "init"), ("bookkeeping", "init"), ("change-journal", "init"), ("bookkeeping", "grant-profile")):
                selected["DB_URL"] = owner_url
            elif verifier:
                selected["DB_URL"] = none(reader)
            result = _run(python, "-m", "edgar_warehouse.cli", *args, env=selected, cwd=root)
            if result.returncode:
                (root / "private-control-pipeline.log").write_text(result.stdout + "\n" + result.stderr)
            assert result.returncode == 0, "Installed pipeline failed; private diagnostic retained"
            return json.loads(result.stdout) if report else None
        command("rules", "init", "--agent-role", role)
        command("bookkeeping", "init", "--runtime-role", role, "--database-name", prefix + "bookkeeping")
        command("bookkeeping", "init", "--runtime-role", reader_role, "--database-name", prefix + "bookkeeping")
        command("change-journal", "init", "--runtime-role", role, "--database-name", prefix + "change_journal")
        with owner.connect() as conn:
            known = set(conn.scalars(text("SELECT User FROM mysql.user" if owner.dialect.name == "mysql" else "SELECT rolname FROM pg_roles")))
        groups = []
        try:
            for profile in ("artifact.copy", "jsonl.count"):
                granted = command("bookkeeping", "grant-profile", "--profile", profile, "--worker", role)
                groups += [item["role"] for item in granted.values() if item["role"] not in known]
            body = config(steps=2)
            body["bookkeeping"]["targets"]["silver"]["steps"][1]["operation"] = "jsonl.count"
            from edgar_warehouse.rules import files
            files.LAYOUT["pipeline"][1](body, root / "rules-root" / "pipelines" / "invented.installed-control" / "pipeline.yaml")
            artifacts = Artifacts()
            source = artifacts.put(root.as_uri() + "/inputs", {"invented": 10**50})
            copied, counted = (root / "copied.json").as_uri(), (root / "counted.json").as_uri()
            inputs = artifacts.put(root.as_uri() + "/manifests", {"version": 2, "steps": {
                "s0": [{"keys": {"id": "0", "destination": copied}, "input": source, "output": copied, "cursor": {}}],
                "s1": [{"keys": {"id": "0", "destination": counted}, "input": {"from": {"step": "s0", "key": "0"}}, "output": counted, "cursor": {}}]}})
            selection = ["--pipeline", "invented.installed-control", "--root", str(root / "rules-root")]
            run = command("rules", "run", *selection, "--target", "silver", "--input-manifest", inputs["uri"], "--input-sha256", inputs["sha256"])
            rid = run["run"]["run_id"]
            for profile in ("artifact.copy", "jsonl.count"):
                command("workers", "work", profile, rid, "--reports", (root / "reports").as_uri(), report=False)
            final = command("bookkeeping", "finalize", rid)
            assert final["run"]["state"] == "complete" and final["counts"] == {"verified": 2}
            assert command("change-journal", "status")["events"] == 2
            command("rules", "run", *selection, "--target", "silver", "--resume-run-id", rid)
            for profile in ("artifact.copy", "jsonl.count"):
                command("workers", "work", profile, rid, "--reports", (root / "reports").as_uri(), report=False)
            assert command("bookkeeping", "finalize", rid)["counts"] == {"verified": 2}
            assert command("change-journal", "status")["events"] == 2
        finally:
            with owner.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                for group in groups:
                    principal = "'" + group + "'@'%'" if owner.dialect.name == "mysql" else conn.dialect.identifier_preparer.quote(group)
                    conn.execute(text("DROP ROLE " + principal))
