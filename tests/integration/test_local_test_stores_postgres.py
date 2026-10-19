"""Real Docker PG16: six stores, independent agents, restart and exact restore."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from edgar_warehouse.control_contract import Blocked
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

from tests.unit.test_local_test_stores import local


def test_five_store_initialization_runs_separate_workers_and_keeps_their_evidence(tmp_path):
    """The generated connections really run work; silver is never created."""
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.rules import files
    from edgar_warehouse.rules.db import Rules
    from edgar_warehouse.workers import PROFILES
    from tests.integration.test_configured_bookkeeping_postgres import config

    stores = local.LocalStores(tmp_path / "stores", tmp_path / "worktree")
    name, copy = "core-" + uuid4().hex[:10], "copy-" + uuid4().hex[:10]
    engines = []

    def engine(database, login):
        value = stores.engine(name, database, login)
        engines.append(value)
        return value

    def environment(filename):
        values = {**os.environ, "PYTHONPATH": str(Path(local.__file__).parents[2])}
        for line in (stores.folder(name) / filename).read_text().splitlines():
            parts = shlex.split(line)
            if parts[0] == "unset":
                for key in parts[1:]:
                    values.pop(key, None)
            else:
                key, value = parts[1].split("=", 1)
                values[key] = value
        return values

    def cli(duty, *args, success=True):
        result = subprocess.run([sys.executable, "-c", "from edgar_warehouse.cli import main; raise SystemExit(main())", *args],
                                env=environment(duty + ".env"), capture_output=True, text=True, timeout=30)
        # Driver errors may include connection details: never print output here.
        assert (result.returncode == 0) == success, f"CLI status {result.returncode} for {args[0]}"
        return json.loads(result.stdout) if success and result.stdout else None

    try:
        with stores.locked(name):
            stores.start(name)
        assert set(stores.stores(name)) == set(local.STORES)
        admin = engine("postgres", "postgres")
        with admin.connect() as conn:
            assert not conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname='silver')"))
            assert not conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='silver_runtime')"))
        for filename in ("connection.env", "worker.env", "verifier.env", "governance.env"):
            assert (stores.folder(name) / filename).stat().st_mode & 0o777 == 0o600
        worker, verifier, governance = (environment(f + ".env") for f in ("worker", "verifier", "governance"))
        assert "SILVER_DATABASE_URL" not in worker
        assert "MDM_MIGRATION_DATABASE_URL" not in worker
        book = engine("bookkeeping", "postgres")
        with book.connect() as conn:
            for profile in PROFILES:
                for login, allowed, denied in (("bookkeeping_runtime", "worker", "verifier"),
                                              ("bookkeeping_verifier", "verifier", "worker")):
                    assert conn.scalar(text("SELECT pg_has_role(:l,bookkeeping.profile_role(:p,:d),'MEMBER')"),
                                       {"l": login, "p": profile, "d": allowed})
                    assert not conn.scalar(text("SELECT pg_has_role(:l,bookkeeping.profile_role(:p,:d),'MEMBER')"),
                                           {"l": login, "p": profile, "d": denied})
        # Governance can register a genuinely validated invented policy, while
        # workers and verifiers cannot insert master state directly.
        policy = {"version": 1, "required_consumers": ["export", "graph"], "automatic_rules": []}
        rules = Rules(engine("rules", "rules_governance"))
        saved = rules.save("merge", "platform", "invented", policy)
        proof = {"digest": saved["digest"], "batch_hash": "a" * 64, "passed": True}
        rules.prove("merge", "platform", "invented", proof)
        pending = rules.pending()[0]
        rules.approve("merge", "platform", "invented", evidence=pending["evidence_hash"],
                      by="invented operator", words="Approved invented fixture")
        rules.activate("merge", "platform", "invented", mdm_engine=engine("mdm", "mdm_governance"))
        # A source that declares no feed of its own (it reads files another source's feed
        # captures) switches on its pipes and registers its datasets (operator, 2026-10-19).
        person = files.source("sec.submissions.person")
        assert "acquisition" not in person
        saved = rules.save("source", "sec.submissions.person", "invented", person)
        rules.prove("source", "sec.submissions.person", "invented",
                    {"digest": saved["digest"], "batch_hash": "b" * 64, "passed": True})
        waiting = next(p for p in rules.pending() if p["name"] == "sec.submissions.person")
        rules.approve("source", "sec.submissions.person", "invented", evidence=waiting["evidence_hash"],
                      by="invented operator", words="Approved invented fixture")
        rules.activate("source", "sec.submissions.person", "invented", mdm_engine=engine("mdm", "mdm_governance"))
        with engine("mdm", "mdm_governance").connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM mdm.dataset_mapping WHERE source_code=:c"),
                               {"c": "sec.submissions.person.v1"}) == 1
        # Another source cannot register over a dataset Person owns.
        other = {**person, "source": "invented.other"}
        saved = rules.save("source", "invented.other", "invented", other)
        rules.prove("source", "invented.other", "invented",
                    {"digest": saved["digest"], "batch_hash": "c" * 64, "passed": True})
        waiting = next(p for p in rules.pending() if p["name"] == "invented.other")
        rules.approve("source", "invented.other", "invented", evidence=waiting["evidence_hash"],
                      by="invented operator", words="Approved invented fixture")
        with pytest.raises(Blocked, match="belongs to source sec.submissions.person"):
            rules.activate("source", "invented.other", "invented", mdm_engine=engine("mdm", "mdm_governance"))
        for login in ("mdm_runtime", "mdm_verifier", "mdm_governance"):
            reader = engine("mdm", login)
            with reader.connect() as conn:
                assert conn.scalar(text("SELECT count(*) FROM mdm.policy")) == 1
                assert not conn.scalar(text("SELECT has_schema_privilege(current_user,'mdm','CREATE')"))
            with pytest.raises(DBAPIError):
                with reader.begin() as conn:
                    conn.execute(text("DELETE FROM mdm.master_entity WHERE false"))
        application = engine("mdm", "mdm_runtime")
        def lease(until):
            return json.dumps([{"resource": "invented", "token": 1, "run_id": str(uuid4()),
                                "attempt": str(uuid4()), "expires_at": until.isoformat()}])
        with application.begin() as conn:
            conn.execute(text("SELECT bookkeeping_guard.authorize(CAST(:p AS jsonb))"),
                         {"p": lease(datetime.now(timezone.utc) + timedelta(minutes=2))})
        with pytest.raises(DBAPIError):
            with application.begin() as conn:
                conn.execute(text("SELECT bookkeeping_guard.authorize(CAST(:p AS jsonb))"),
                             {"p": lease(datetime.now(timezone.utc) - timedelta(minutes=1))})
        # Run a real offline copy using the generated worker/verifier files.
        artifacts = Artifacts()
        inp = artifacts.put(tmp_path.as_uri() + "/inputs", {"invented": 1})
        output = (tmp_path / "copied.json").as_uri()
        manifest = artifacts.put(tmp_path.as_uri() + "/manifests", {"version": 1, "units": [
            {"keys": {"id": "one", "destination": output}, "input": inp, "output": output, "cursor": None}]})
        body = config()
        body["bookkeeping"]["targets"]["load"] = body["bookkeeping"]["targets"].pop("silver")
        saved = rules.save("pipeline", "invented-local-load", "1", body)
        rules.prove("pipeline", "invented-local-load", "1", {"digest": saved["digest"],
                    "batch_hash": manifest["sha256"], "passed": True})
        rules.activate("pipeline", "invented-local-load", "1")
        result = cli("worker", "rules", "run", "--pipeline", "invented-local-load", "--target", "load",
                     "--input-manifest", manifest["uri"], "--input-sha256", manifest["sha256"])
        run_id = str(result["run"]["run_id"])
        cli("verifier", "workers", "work", "artifact.copy", run_id, success=False)
        cli("worker", "workers", "work", "artifact.copy", run_id)
        cli("worker", "workers", "verify", "artifact.copy", run_id, "--reports", (tmp_path / "reports").as_uri(), success=False)
        cli("verifier", "workers", "verify", "artifact.copy", run_id, "--reports", (tmp_path / "reports").as_uri())
        cli("worker", "bookkeeping", "finalize", run_id)
        status = cli("worker", "bookkeeping", "status", run_id)
        assert status["run"]["state"] == "complete" and status["pending_deliveries"] == 0
        assert (tmp_path / "copied.json").read_bytes() == artifacts.read(inp["uri"])
        for value in engines:
            value.dispose()
        expected = stores.contents(name)
        with stores.locked(name):
            stores.start(name)
        assert stores.contents(name) == expected
        # Every generated login is paused/restored by backups, not just workers.
        active = engine("mdm", "mdm_verifier")
        with active.connect():
            with pytest.raises(ValueError, match="connections are active"):
                stores.backup(name)
        active.dispose()
        with stores.locked(name):
            snapshot = stores.backup(name)
        assert len(json.loads((snapshot / "manifest.json").read_text())["files"]) == 5
        with stores.locked(copy):
            stores.restore(copy, snapshot)
        assert stores.contents(copy) == expected
        with book.begin() as conn:
            role = conn.scalar(text("SELECT bookkeeping.profile_role('artifact.copy','worker')"))
            conn.exec_driver_sql(f'GRANT "{role}" TO bookkeeping_verifier')
        with pytest.raises(ValueError, match="duties overlap"):
            with stores.locked(name):
                stores.start(name)
    finally:
        for value in engines:
            value.dispose()
        for selected in (name, copy):
            if not (stores.folder(selected) / "identity.json").exists():
                continue
            container, volume = stores.owned(selected, stores.identity(selected))
            if stores.resource("container", container):
                stores.docker("rm", "-f", container)
            if stores.resource("volume", volume):
                stores.docker("volume", "rm", volume)


def test_two_agents_keep_their_data_and_restore_all_six_stores(tmp_path):
    root = tmp_path / "stores"
    first = local.LocalStores(root, tmp_path / "first-worktree")
    second = local.LocalStores(root, tmp_path / "second-worktree")
    one, two = "one-" + uuid4().hex[:10], "two-" + uuid4().hex[:10]
    restored = "copy-" + uuid4().hex[:10]
    try:
        with first.locked(one):
            first.start(one, include_silver=True)
            first.start(one, include_silver=True)  # repeated provisioning changes no rows
        with second.locked(two):
            second.start(two, include_silver=True)
        # Each store has its own restricted login; it cannot create tables.
        for database, (_, schema) in local.ALL_STORES.items():
            runtime = first.engine(one, database, database + "_runtime")
            try:
                with runtime.connect() as conn:
                    assert conn.scalar(text(f"SELECT has_schema_privilege(current_user,'{schema}','USAGE')"))
                    assert not conn.scalar(text(f"SELECT has_schema_privilege(current_user,'{schema}','CREATE')"))
                    assert not conn.scalar(text("SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls FROM pg_roles WHERE rolname=current_user"))
            finally:
                runtime.dispose()
        # Invented MDM records use the existing Merge Stage fixture; do not touch a baseline.
        from tests.integration import test_clean_mdm_postgres as mdm
        from tests.integration.test_clean_entity_context_postgres import load_group
        owner = first.engine(one, "mdm")
        @event.listens_for(owner, "connect")
        def owner_role(connection, _):
            with connection.cursor() as cur:
                cur.execute("SET ROLE mdm_owner")
            connection.commit()
        app = first.engine(one, "mdm", "mdm_runtime")
        try:
            from tests.support.rules_authority import register_dataset
            version = str(uuid4())
            with owner.begin() as conn:
                policy = mdm.register_policy(conn, {"version": 1, "required_consumers": ["export", "graph"],
                    "automatic_rules": [], "fields": {"company": {"name": {"sources": ["fixture.primary", "fixture.secondary"]}}}})
                for code in ("fixture.primary", "fixture.secondary"):
                    register_dataset(conn, code, version, {"provider": "test", "family": "fixture",
                        "publication_families": ["golden_copy", "opencorporates"], "schema_version": "1",
                        "record_key": "key", "publication_key": "version", "effective_time": "effective_at", "semantics": "patch"})
            database = mdm.Database(owner, app, policy, version)
            ids = load_group(database)
        finally:
            owner.dispose()
            app.dispose()
        rdm = first.engine(one, "rdm", "rdm_runtime")
        try:
            with rdm.begin() as conn:
                conn.execute(text("INSERT INTO rdm.code_set(code_set,name) VALUES ('invented','Invented test codes')"))
        finally:
            rdm.dispose()
        # A real silver row retains its looked-up MDM id and an exact BIGINT.
        from edgar_warehouse.silver_writer import database as silver
        from edgar_warehouse.silver_writer.sink import PostgresSink
        from edgar_warehouse.silver_writer.writer import MdmIds, land
        from tests.unit.test_silver_writer import a_spec
        owner = first.engine(one, "silver")
        @event.listens_for(owner, "connect")
        def silver_owner(connection, _):
            with connection.cursor() as cur:
                cur.execute("SET ROLE silver_owner")
            connection.commit()
        runtime = first.engine(one, "silver", "silver_runtime")
        table = a_spec(links=[{"columns": ["member_id"], "kind": "company", "source_code": "fixture.primary",
                              "source_key": "member_id", "mdm_id_column": "member_id_mdm_id", "inclusion": 1.0}])
        mdm_reader = first.engine(one, "mdm", "mdm_runtime")
        try:
            silver.register(owner, table, runtime_role="silver_runtime")
            result = land(PostgresSink(runtime), "visit", [{"visit_id": 2**53 + 1, "member_id": "b", "amount": "1.25", "visited_on": None, "tags": None}], MdmIds(mdm_reader))
            assert result["mdm_keys_found"] == 1
            with runtime.connect() as conn:
                row = conn.execute(text("SELECT visit_id, member_id_mdm_id FROM silver.visit")).one()
                assert row == (2**53 + 1, ids['b'])
        finally:
            owner.dispose()
            runtime.dispose()
            mdm_reader.dispose()
        expected = first.contents(one)
        reader = first.engine(one, "mdm", "mdm_runtime")
        try:
            with reader.connect() as conn:
                assert conn.scalar(text("SELECT count(*) FROM mdm.current_entity")) == 3
        finally:
            reader.dispose()
        assert expected['silver.silver.visit']['rows'] == 1
        assert second.contents(two)['rdm.rdm.code_set']['rows'] == 0
        # Old environments predate the selection field; a core-only reinit must
        # leave their silver data intact and include it in recovery snapshots.
        identity = first.identity(one)
        identity.pop("stores")
        local.private_write(first.folder(one) / "identity.json", json.dumps(identity))
        with pytest.raises(ValueError, match="another worktree"):
            second.start(one)
        with first.locked(one):
            first.stop(one)
            first.start(one)
        assert first.contents(one) == expected
        # Simulate a process dying after it fenced logins but before finally ran.
        local.private_write(first.folder(one) / "backup-paused.json",
                            json.dumps({d + "_runtime": True for d in local.ALL_STORES}))
        admin = first.engine(one)
        try:
            with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                for d in local.ALL_STORES:
                    conn.exec_driver_sql(f'ALTER ROLE "{d}_runtime" NOLOGIN')
        finally:
            admin.dispose()
        with first.locked(one):
            first.stop(one)
            first.start(one)
        assert not (first.folder(one) / "backup-paused.json").exists()
        runtime = first.engine(one, "silver", "silver_runtime")
        try:
            with runtime.connect() as conn:
                assert conn.scalar(text("SELECT count(*) FROM silver.visit")) == 1
        finally:
            runtime.dispose()
        # Active writers block a baseline copy; the login is restored after refusal.
        active = first.engine(one, "rdm", "rdm_runtime")
        try:
            with active.connect():
                with pytest.raises(ValueError, match="connections are active"):
                    first.backup(one)
        finally:
            active.dispose()
        with first.locked(one):
            snapshot = first.publish_baseline(one)
        assert Path((root / 'baseline').read_text().strip()) == snapshot
        with second.locked(restored):
            second.restore(restored, snapshot)
        assert second.contents(restored) == expected
        # Restored contents alone do not prove the runtime can use the tables.
        runtime = second.engine(restored, "silver", "silver_runtime")
        mdm_reader = second.engine(restored, "mdm", "mdm_runtime")
        try:
            with runtime.connect() as conn:
                assert conn.execute(text("SELECT visit_id,member_id_mdm_id FROM silver.visit")).one() == (2**53 + 1, ids['b'])
            result = land(PostgresSink(runtime), "visit", [{"visit_id": 2**53 + 2, "member_id": "b", "amount": "2.50", "visited_on": None, "tags": None}], MdmIds(mdm_reader))
            assert result["inserted"] == 1 and result["mdm_keys_found"] == 1
            with runtime.begin() as conn:
                conn.execute(text("DELETE FROM silver.visit WHERE visit_id=:i"), {"i": 2**53 + 2})
        finally:
            runtime.dispose()
            mdm_reader.dispose()
        assert second.contents(restored) == expected
        with pytest.raises(ValueError, match="existing data is never overwritten"):
            second.restore(restored, snapshot)
        assert first.contents(one) == expected
        assert second.contents(two)['rdm.rdm.code_set']['rows'] == 0
        assert (first.folder(one) / "connection.env").stat().st_mode & 0o777 == 0o600
    finally:
        # These are disposable targets created by this test, with these exact labels.
        for manager in (first, second):
            folders = root / "environments"
            for path in folders.iterdir() if folders.exists() else []:
                identity_path = path / "identity.json"
                if not identity_path.exists() or json.loads(identity_path.read_text())["owner"] != manager.owner:
                    continue
                container, volume = manager.owned(path.name, manager.identity(path.name))
                if manager.resource("container", container):
                    manager.docker("rm", "-f", container)
                if manager.resource("volume", volume):
                    manager.docker("volume", "rm", volume)
