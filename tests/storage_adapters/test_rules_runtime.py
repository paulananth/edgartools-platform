"""The normal Rules lifecycle under restricted, selected-engine roles."""
import json

import pytest
from sqlalchemy import create_engine

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules.db import Rules, migrate
from tests.integration.test_rules_approval_postgres import pipeline, proof


def test_normal_rules_lifecycle_and_populated_migration(database_factory, tmp_path, monkeypatch, capsys):
    # The outer role survives until the inner database and its grants are gone.
    with database_factory() as (_, approver_login, approver_role):
        if approver_login.dialect.name == "mssql":
            pytest.skip("Full SQL Server Rules qualification follows PostgreSQL/MySQL")
        with database_factory() as (owner, runtime, role):
            approval = create_engine(approver_login.url.set(database=owner.url.database), hide_parameters=True)
            try:
                checksums = migrate(owner, agent_role=role, approver_role=approver_role,
                                    database_name=owner.url.database)
                rules, approver = Rules(runtime), Rules(approval)
                body = pipeline()
                saved = rules.save("pipeline", "invented.pipeline", "v1", body)
                assert saved["status"] == "draft" and saved["approved_by"] is None
                assert rules.save("pipeline", "invented.pipeline", "v1", body)["digest"] == saved["digest"]
                rules.prove("pipeline", "invented.pipeline", "v1", proof(saved))
                pending = rules.pending()
                assert [(r["name"], r["version"], r["passed"]) for r in pending] == [("invented.pipeline", "v1", True)]
                approved = approver.approve("pipeline", "invented.pipeline", "v1", evidence=pending[0]["evidence_hash"],
                                            by="invented operator", words="Approve this exact tested version")
                assert approved["approved_words"] == "Approve this exact tested version"
                from sqlalchemy.exc import DBAPIError
                with pytest.raises(DBAPIError, match="[Pp]roof.*immutable"):
                    rules.prove("pipeline", "invented.pipeline", "v1", proof(saved, batch_hash="2" * 64))
                assert rules.version("pipeline", "invented.pipeline", "v1") == approved
                rules.activate("pipeline", "invented.pipeline", "v1")
                before = rules.version("pipeline", "invented.pipeline", "v1")
                assert before["status"] == "active" and before["approval_evidence"] == pending[0]["evidence_hash"]
                assert json.loads(before["body"]) == body
                ref = rules.resolve("pipeline", "invented.pipeline", root=(tmp_path / "exports").as_uri())
                exported = Artifacts().json(ref)
                assert exported["body"] == body and exported["status"] == "active"
                assert migrate(owner, agent_role=role, approver_role=approver_role,
                               database_name=owner.url.database) == checksums
                assert rules.version("pipeline", "invented.pipeline", "v1") == before
                rules.activate("pipeline", "invented.pipeline", "v1")
                assert rules.version("pipeline", "invented.pipeline", "v1") == before
                from edgar_warehouse.cli import main
                monkeypatch.setenv("RULES_DATABASE_URL", runtime.url.render_as_string(hide_password=False))
                assert main(["rules", "status", "--pipeline", "invented.pipeline"]) == 0
                reported = json.loads(capsys.readouterr().out)
                assert [(row["version"], row["status"]) for row in reported] == [("v1", "active")]
            finally:
                approval.dispose()


def test_direct_proof_write_cannot_bypass_acquisition_completeness(database_factory):
    from sqlalchemy import update
    from sqlalchemy.exc import DBAPIError
    from edgar_warehouse.rules.storage import versions, identity
    with database_factory() as (_, approval, approval_role):
        if approval.dialect.name == "mssql":
            pytest.skip("Full SQL Server Rules qualification follows PostgreSQL/MySQL")
        with database_factory() as (owner, runtime, role):
            migrate(owner, agent_role=role, approver_role=approval_role, database_name=owner.url.database)
            rules = Rules(runtime)
            body = {"source": "invented-acquisition", "acquisition": {"version": 1, "feeds": {"input": {
                "family": "invented", "datasets": ["invented.v1"], "scope": ["invented"],
                "capabilities": {"capture": "provider.capture", "fetch": "http.conditional"},
                "completeness": {"format": "json", "required": [], "allow_empty": True, "max_bytes": 1024},
                "required_producers": ["capture"], "url_prefixes": ["https://invented.invalid/"]}}}}
            saved = rules.save("source", "invented-acquisition", "v1", body)
            invalid = proof(saved, acquisition={"input": {"manifest": {
                "uri": "file:///invented/not-opened.json", "sha256": "0" * 64},
                "counts": {"capture": {"expected": 3, "verified": 1}}, "checks": {"complete": False}}})
            table = versions(runtime.dialect.name)
            with pytest.raises(DBAPIError, match="acquisition"):
                with runtime.begin() as conn:
                    conn.execute(update(table).where(identity(table, conn.dialect.name, "source", "invented-acquisition", "v1")).values(
                        status="proven", proof=invalid, batch_hash=invalid["batch_hash"]))
            assert rules.version("source", "invented-acquisition", "v1")["status"] == "draft"


@pytest.mark.parametrize("altered", [False, True])
def test_mysql_empty_marker_recovery_requires_its_original_shape(database_factory, monkeypatch, altered):
    import os
    from sqlalchemy import text
    from sqlalchemy.engine import Connection
    from edgar_warehouse.control_contract import Blocked
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") != "mysql":
        pytest.skip("MySQL implicit-DDL recovery only")
    with database_factory() as (_, approval, approval_role):
        with database_factory() as (owner, runtime, role):
            execute = Connection.execute
            def interrupted(conn, statement, *args, **kwargs):
                if str(statement).startswith("INSERT INTO rules_migrations"):
                    raise RuntimeError("Invented marker interruption")
                return execute(conn, statement, *args, **kwargs)
            with monkeypatch.context() as patch:
                patch.setattr(Connection, "execute", interrupted)
                with pytest.raises(RuntimeError, match="marker interruption"):
                    migrate(owner, agent_role=role, approver_role=approval_role, database_name=owner.url.database)
            if altered:
                with owner.begin() as conn:
                    conn.execute(text("ALTER TABLE rules_migrations ADD surprise BIGINT"))
                with pytest.raises(Blocked, match="Untracked Rules migration metadata"):
                    migrate(owner, agent_role=role, approver_role=approval_role, database_name=owner.url.database)
            else:
                assert migrate(owner, agent_role=role, approver_role=approval_role, database_name=owner.url.database)
                assert Rules(runtime).save("pipeline", "invented.recovered", "v1", pipeline())["status"] == "draft"


def test_rules_activation_reuses_the_actual_selected_master_reading(database_factory):
    from edgar_warehouse.mdm.clean import catalog
    from edgar_warehouse.mdm.clean.store import migrate as migrate_master, current_reading
    with database_factory() as (_, approval_login, approval_role):
        if approval_login.dialect.name == "mssql":
            pytest.skip("Full SQL Server Rules qualification follows PostgreSQL/MySQL")
        with database_factory() as (owner, runtime, role):
            approval = create_engine(approval_login.url.set(database=owner.url.database), hide_parameters=True)
            try:
                migrate(owner, agent_role=role, approver_role=approval_role, database_name=owner.url.database)
                with database_factory() as (master_owner, master_runtime, master_role):
                    migrate_master(master_owner, application_role=master_role, prepared=True)
                    rules, approver = Rules(runtime), Rules(approval)
                    contract = {"provider": "invented", "family": "invented-family", "schema_version": "1",
                                "record_key": "key", "publication_key": "version", "effective_time": "effective_at",
                                "semantics": "patch", "adapter": {"kind": catalog.CATALOG["kinds"][0], "record_key": ["key"]}}
                    body = {"source": "invented-handoff", "bronze": {"family": "invented-family"},
                            "mdm": {"invented.dataset": {"contract": contract}}}
                    previous = None
                    for version in ("v1", "v2"):
                        saved = rules.save("source", "invented-handoff", version, body)
                        rules.prove("source", "invented-handoff", version, proof(saved))
                        evidence = next(r["evidence_hash"] for r in rules.pending() if r["version"] == version)
                        approver.approve("source", "invented-handoff", version, evidence=evidence,
                                         by="invented operator", words="Approve this exact source handoff")
                        rules.activate("source", "invented-handoff", version, mdm_engine=master_owner)
                        with master_owner.connect() as conn:
                            reading = current_reading(conn, "invented.dataset")
                        assert reading[0] == 1
                        if previous is not None:
                            assert reading == previous
                        previous = reading
                        active = rules.version("source", "invented-handoff", version)
                        assert active["status"] == "active" and active["clean_mdm"]["datasets"]["invented.dataset"]["mapping_version"] == 1
                    assert [(r["version"], r["status"]) for r in rules.history("source", "invented-handoff")] == [("v1", "retired"), ("v2", "active")]
            finally:
                approval.dispose()


@pytest.mark.parametrize("corruption", ["future", "state"])
def test_mysql_refuses_unknown_migration_history(database_factory, corruption):
    import os
    from sqlalchemy import text
    from edgar_warehouse.control_contract import Blocked
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") != "mysql":
        pytest.skip("MySQL migration marker only")
    with database_factory() as (_, _, approval_role):
        with database_factory() as (owner, _, role):
            options = dict(agent_role=role, approver_role=approval_role, database_name=owner.url.database)
            migrate(owner, **options)
            with owner.begin() as conn:
                if corruption == "future":
                    conn.execute(text("INSERT INTO rules_migrations SELECT 2,checksum,1,guard_checksum FROM rules_migrations WHERE id=1"))
                else:
                    conn.execute(text("UPDATE rules_migrations SET complete=7 WHERE id=1"))
            with pytest.raises(Blocked, match="migration history"):
                migrate(owner, **options)


def test_runtime_cannot_rewrite_rules_content_or_history(database_factory):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    with database_factory() as (_, _, approval_role):
        with database_factory() as (owner, runtime, role):
            if runtime.dialect.name == "mssql":
                pytest.skip("Full SQL Server Rules qualification follows PostgreSQL/MySQL")
            migrate(owner, agent_role=role, approver_role=approval_role, database_name=owner.url.database)
            rules = Rules(runtime)
            rules.save("pipeline", "invented.protected", "v1", pipeline())
            table = "rules.rule_version" if runtime.dialect.name == "postgresql" else "rule_version"
            for sql in (f"UPDATE {table} SET body='{{}}'", f"DELETE FROM {table}",
                        f"ALTER TABLE {table} ADD forged BIGINT"):
                with pytest.raises(DBAPIError):
                    with runtime.begin() as conn:
                        conn.execute(text(sql))
            assert rules.version("pipeline", "invented.protected", "v1")["status"] == "draft"


def test_mysql_populated_recovery_revokes_cached_runtime_before_guard_rebuild(database_factory, monkeypatch):
    import os
    from sqlalchemy import text
    from sqlalchemy.engine import Connection
    from sqlalchemy.exc import DBAPIError
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") != "mysql":
        pytest.skip("MySQL implicit-DDL recovery only")
    with database_factory() as (_, _, approval_role):
        with database_factory() as (owner, runtime, role):
            options = dict(agent_role=role, approver_role=approval_role, database_name=owner.url.database)
            migrate(owner, **options)
            rules = Rules(runtime)
            saved = rules.save("pipeline", "invented.recovery", "v1", pipeline())
            rules.prove("pipeline", "invented.recovery", "v1", proof(saved))
            before = rules.version("pipeline", "invented.recovery", "v1")
            with runtime.connect() as cached:
                cached.execute(text("SELECT 1"))
                cached.commit()
                with owner.begin() as conn:
                    conn.execute(text("UPDATE rules_migrations SET complete=0 WHERE id=1"))
                execute = Connection.execute
                def interrupted(conn, statement, *args, **kwargs):
                    if str(statement).startswith("DROP TRIGGER IF EXISTS rules_insert"):
                        for sql in ("SELECT * FROM rule_version", "UPDATE rule_version SET status='proven'"):
                            with pytest.raises(DBAPIError):
                                execute(cached, text(sql))
                            cached.rollback()
                        raise RuntimeError("Invented populated interruption")
                    return execute(conn, statement, *args, **kwargs)
                with monkeypatch.context() as patch:
                    patch.setattr(Connection, "execute", interrupted)
                    with pytest.raises(RuntimeError, match="populated interruption"):
                        migrate(owner, **options)
                with pytest.raises(DBAPIError):
                    execute(cached, text("SELECT * FROM rule_version"))
                cached.rollback()
                migrate(owner, **options)
                assert rules.version("pipeline", "invented.recovery", "v1") == before


def test_concurrent_activation_keeps_one_active_version_and_immutable_proof(database_factory):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import update
    from sqlalchemy.exc import DBAPIError
    from edgar_warehouse.rules.storage import versions, identity
    from edgar_warehouse.control_contract import Blocked
    with database_factory() as (_, _, approval_role):
        with database_factory() as (owner, runtime, role):
            if runtime.dialect.name == "mssql":
                pytest.skip("Full SQL Server Rules qualification follows PostgreSQL/MySQL")
            migrate(owner, agent_role=role, approver_role=approval_role, database_name=owner.url.database)
            rules = Rules(runtime)
            for label in ("v1", "v2"):
                saved = rules.save("pipeline", "invented.concurrent", label, pipeline())
                rules.prove("pipeline", "invented.concurrent", label, proof(saved))
            with pytest.raises(Blocked, match="differs"):
                rules.approve("pipeline", "invented.concurrent", "v1", evidence="0" * 64,
                              by="invented operator", words="Approve this tested version")
            table = versions(runtime.dialect.name)
            with pytest.raises(DBAPIError, match="[Pp]roof.*immutable"):
                with runtime.begin() as conn:
                    conn.execute(update(table).where(identity(table, conn.dialect.name, "pipeline", "invented.concurrent", "v1")).values(
                        proof={"digest": saved["digest"], "passed": True, "batch_hash": "2" * 64}, batch_hash="2" * 64))
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = [pool.submit(rules.activate, "pipeline", "invented.concurrent", label) for label in ("v1", "v2")]
                for result in results:
                    result.result(timeout=40)
            assert sorted(row["status"] for row in rules.history("pipeline", "invented.concurrent")) == ["active", "retired"]


@pytest.mark.parametrize("drift", ["trigger", "index"])
def test_mysql_completed_installation_refuses_guard_drift_and_revokes_runtime(database_factory, drift):
    import os
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from edgar_warehouse.control_contract import Blocked
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") != "mysql":
        pytest.skip("MySQL completed-DDL qualification only")
    with database_factory() as (_, _, approval_role):
        with database_factory() as (owner, runtime, role):
            options = dict(agent_role=role, approver_role=approval_role, database_name=owner.url.database)
            migrate(owner, **options)
            Rules(runtime).save("pipeline", "invented.drift", "v1", pipeline())
            with owner.begin() as conn:
                conn.execute(text("DROP TRIGGER rules_update" if drift == "trigger" else "ALTER TABLE rule_version DROP INDEX one_active"))
            with pytest.raises(Blocked, match="storage differs"):
                migrate(owner, **options)
            with pytest.raises(DBAPIError):
                Rules(runtime).save("pipeline", "invented.drift", "v2", pipeline())


def test_postgres_rejects_migration_owner_as_approval_principal(database_factory):
    import os
    from edgar_warehouse.control_contract import Blocked
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") != "postgresql":
        pytest.skip("PostgreSQL principal attributes only")
    with database_factory() as (owner, _, role):
        with pytest.raises(Blocked, match="[Rr]estricted"):
            migrate(owner, agent_role=role, approver_role=owner.url.username, database_name=owner.url.database)
