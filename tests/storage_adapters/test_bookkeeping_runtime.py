"""Normal control lifecycle on the selected engine, with separate real duties."""
import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from edgar_warehouse.bookkeeping.clean.database import migrate, grant_profile
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.control_contract import digest
from tests.integration.test_configured_bookkeeping_postgres import config
from tests.support.bookkeeping_protocol import complete

pytestmark = pytest.mark.skipif(os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql",
                                reason="Full SQL Server control lifecycle follows PostgreSQL/MySQL")


@pytest.fixture
def control(database_factory):
    with database_factory() as (_, verifier_login, verifier_role):
        with database_factory() as (owner, worker, worker_role):
            verifier = create_engine(verifier_login.url.set(database=owner.url.database), hide_parameters=True)
            try:
                checksums = migrate(owner, runtime_role=worker_role, database_name=owner.url.database)
                assert migrate(owner, runtime_role=verifier_role, database_name=owner.url.database, existing_only=True) == checksums
                profile = "invented." + uuid4().hex
                granted = grant_profile(owner, profile=profile, worker=worker_role, verifier=verifier_role)
                book = Bookkeeping(worker)
                book.profile = profile
                book.granted = granted
                book.verifier = Bookkeeping(verifier, book.artifacts)
                try:
                    yield owner, worker_role, verifier_role, book, checksums
                finally:
                    with owner.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                        for duty in granted.values():
                            quote = conn.dialect.identifier_preparer.quote_identifier
                            principal = "'" + duty["role"] + "'@'%'" if conn.dialect.name == "mysql" else quote(duty["role"])
                            conn.execute(text("DROP ROLE " + principal))
            finally:
                verifier.dispose()


def submission(book, tmp_path, *, count=2, body=None, cursor=None, key=None):
    body = body or config()
    for step in body["bookkeeping"]["targets"]["silver"]["steps"]:
        step["operation"] = book.profile
    artifacts = book.artifacts
    units = []
    for n in range(count):
        source = artifacts.put(tmp_path.as_uri() + "/inputs", {"position": n, "exact": 10**50})
        output = (tmp_path / f"output-{n}").as_uri()
        units.append({"keys": {"id": key(n) if key else str(n), "destination": output}, "input": source, "output": output,
                      "cursor": cursor(n) if cursor else {"offset": n}})
    inputs = artifacts.put(tmp_path.as_uri() + "/manifests", {"version": 1, "units": units})
    export = {"kind": "pipeline", "name": "invented.control", "version": "v1", "digest": digest(body),
              "body": body, "status": "active", "approval": None, "registration": None,
              "proof": {"digest": digest(body), "batch_hash": inputs["sha256"], "passed": True}}
    rules = artifacts.put(tmp_path.as_uri() + "/rules", export)
    run_id = book.start(rules_ref=rules, inputs_ref=inputs, target="silver", scope={"invented": True})
    return run_id, rules, inputs


def test_normal_control_initialization_start_and_unchanged_retry(control, tmp_path):
    owner, worker_role, verifier_role, book, checksums = control
    run_id, rules, inputs = submission(book, tmp_path)
    before = book.status(run_id)
    assert before["counts"] == {"pending": 2}
    assert book.start(rules_ref=rules, inputs_ref=inputs, target="silver", scope={"invented": True}, run_id=run_id) == run_id
    assert book.status(run_id) == before
    for role in (worker_role, verifier_role):
        assert migrate(owner, runtime_role=role, database_name=owner.url.database, existing_only=True) == checksums
    assert book.status(run_id) == before


def test_normal_control_renew_report_verify_complete_and_deliver(control, database_factory, tmp_path):
    from edgar_warehouse.change_journal import ChangeJournal
    from edgar_warehouse.change_journal.database import migrate as migrate_journal
    _, _, _, book, _ = control
    run_id, _, _ = submission(book, tmp_path)
    claim = book.claim(run_id, "s0", "0")
    assert claim is not None and book.heartbeat(claim).proof
    book.wait(claim, "invented voluntary retry")
    complete(book, run_id, "1", profile=book.profile)
    assert book.status(run_id)["checkpoints"][0]["ordinal"] == -1
    complete(book, run_id, "0", profile=book.profile)
    assert book.status(run_id)["checkpoints"][0]["ordinal"] == 1
    with database_factory() as (journal_owner, journal_runtime, journal_role):
        migrate_journal(journal_owner, runtime_role=journal_role, database_name=journal_owner.url.database)
        journal = ChangeJournal(journal_runtime)
        assert book.deliver_all(journal, run_id, limit=1) == 2
        assert book.deliver_all(journal, run_id, limit=1) == 0
        final = book.finalize(run_id)
        assert final["run"]["state"] == "complete" and final["counts"] == {"verified": 2}
        assert book.resume(run_id)["run"]["state"] == "running"
        assert book.finalize(run_id)["run"]["state"] == "complete"


def test_normal_cli_uses_configured_database_and_default_driver(control, monkeypatch, capsys):
    from edgar_warehouse.cli import main
    from edgar_warehouse.bookkeeping.clean.database import get_engine
    owner, role, _, book, _ = control
    bare = book.engine.url.set(drivername=book.engine.dialect.name)
    engine = get_engine(bare.render_as_string(hide_password=False))
    try:
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT 1")) == 1
    finally:
        engine.dispose()
    monkeypatch.setenv("BOOKKEEPING_MIGRATION_DATABASE_URL", owner.url.render_as_string(hide_password=False))
    assert main(["bookkeeping", "migrate", "--runtime-role", role, "--database-name", owner.url.database]) == 0
    assert json.loads(capsys.readouterr().out)


def test_real_duties_fencing_and_report_bindings(control, tmp_path):
    from dataclasses import replace
    from sqlalchemy.exc import DBAPIError
    from edgar_warehouse.workers import copy
    from tests.support.bookkeeping_protocol import RUNTIME, verification_for, verification_report
    owner, worker_role, _, book, _ = control
    run_id, _, _ = submission(book, tmp_path, count=1)
    with pytest.raises(DBAPIError, match="role"):
        book.verifier.claim(run_id, "s0", "0")
    claim = book.claim(run_id, "s0", "0")
    for invalid in ([], [{**entry, "token": entry["token"] + 1} for entry in claim.proof]):
        with pytest.raises(DBAPIError, match="[Pp]roof|[Ll]ease"):
            book.heartbeat(replace(claim, proof=invalid))
    envelope = book.envelope(claim)
    candidate = copy.execute(envelope, book.artifacts)
    with pytest.raises(DBAPIError, match="role"):
        book.verifier.report(envelope, candidate, RUNTIME)
    book.report(envelope, candidate, RUNTIME)
    book.report(envelope, candidate, RUNTIME)  # lost acknowledgement
    with pytest.raises(DBAPIError, match="[Cc]onflicting"):
        book.report(envelope, {**candidate, "sha256": "b" * 64}, RUNTIME)
    with pytest.raises(DBAPIError, match="role"):
        book.verifications(run_id, book.profile)
    quote = owner.dialect.identifier_preparer.quote_identifier
    group = "'" + book.granted["verifier"]["role"] + "'@'%'" if owner.dialect.name == "mysql" else quote(book.granted["verifier"]["role"])
    login = "'" + worker_role + "'@'%'" if owner.dialect.name == "mysql" else quote(worker_role)
    with owner.begin() as conn:
        conn.execute(text("GRANT " + group + " TO " + login))
    try:
        with pytest.raises(DBAPIError, match="own report"):
            book.verifications(run_id, book.profile)
    finally:
        with owner.begin() as conn:
            conn.execute(text("REVOKE " + group + " FROM " + login))
    verification = verification_for(book, run_id, "s0", "0", book.profile)
    report = verification_report(book, verification, copy)
    book.verifier.admit(verification, report)
    before = book.status(run_id)
    book.verifier.admit(verification, report)
    assert book.status(run_id) == before and before["counts"] == {"verified": 1}


def test_exact_cursor_and_journal_time_survive_completion(control, tmp_path):
    from datetime import UTC, datetime
    from edgar_warehouse.bookkeeping.clean import storage
    _, _, _, book, _ = control
    cursor = {"position": 10**50, "label": "Invented clé 雪  ", "nullable": None}
    run_id, _, _ = submission(book, tmp_path, count=1, cursor=lambda _: cursor)
    complete(book, run_id, "0", profile=book.profile)
    assert book.status(run_id)["checkpoints"][0]["cursor"] == cursor
    event = storage.pending_events(book.engine, run_id, 1)[0]
    expected = event["created_at"]
    if expected.tzinfo is None:
        expected = expected.replace(tzinfo=UTC)
    assert datetime.fromisoformat(book.journal_event(event)["occurred_at"]) == expected


def test_resource_checkpoint_is_atomic_and_survives_populated_migrate(control, tmp_path):
    owner, role, _, book, checksums = control
    resource = "invented.resource." + uuid4().hex
    run_id, _, _ = submission(book, tmp_path, body=config(resource=resource), cursor=lambda n: {
        "resource_checkpoint": {"resource": resource, "revision": n, "position": n - 1}, "exact": 10**50})
    for n in range(2):
        complete(book, run_id, str(n), profile=book.profile)
        checkpoint = book.resource_checkpoint(resource)
        assert checkpoint["revision"] == n + 1 and checkpoint["ordinal"] == n and checkpoint["cursor"]["exact"] == 10**50
    before = book.status(run_id)
    assert migrate(owner, runtime_role=role, database_name=owner.url.database, existing_only=True) == checksums
    assert book.status(run_id) == before


def test_generated_children_and_parent_intent_commit_together(control, tmp_path):
    _, _, _, book, _ = control
    body = config(steps=2)
    body["bookkeeping"]["targets"]["silver"]["allow_zero_work"] = True
    for step in body["bookkeeping"]["targets"]["silver"]["steps"]:
        step["operation"] = book.profile
    output = (tmp_path / "parent.json").as_uri()
    child_output = (tmp_path / "child.json").as_uri()
    child = {"keys": {"id": "c1", "destination": child_output},
             "input": book.artifacts.put(tmp_path.as_uri() + "/inputs", {"invented": True}),
             "output": child_output, "cursor": {"exact": 10**50}}
    parent = {"step": "s0", "key": "0", "generated_step": "s1", "ordinal_base": 0}
    expansion = book.artifacts.put(tmp_path.as_uri() + "/expansion", {"version": 1, "parent": parent, "children": [child]})
    manifest = book.artifacts.put(tmp_path.as_uri() + "/manifests", {"version": 2, "steps": {
        "s0": [{"keys": {"id": "0", "destination": output}, "input": expansion, "output": output,
                "cursor": {"generated_step": "s1", "ordinal_base": 0}}], "s1": []}})
    export = {"kind": "pipeline", "name": "invented.generated", "version": "v1", "digest": digest(body),
              "body": body, "status": "active", "approval": None,
              "proof": {"digest": digest(body), "batch_hash": manifest["sha256"], "passed": True}}
    rules = book.artifacts.put(tmp_path.as_uri() + "/rules", export)
    run_id = book.start(rules_ref=rules, inputs_ref=manifest, target="silver", scope={})
    complete(book, run_id, "0", step="s0", profile=book.profile)
    state = book.status(run_id)
    assert state["run"]["expected_count"] == 2 and state["counts"] == {"verified": 1, "pending": 1}
    assert len(state["deliveries"]) == 1
    complete(book, run_id, "c1", step="s1", profile=book.profile)
    assert book.status(run_id)["counts"] == {"verified": 2}


def test_concurrent_claim_and_cross_run_takeover_preserve_fencing(control, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.exc import DBAPIError
    from edgar_warehouse.bookkeeping.clean import storage
    owner, _, _, book, _ = control
    resource = "invented.shared." + uuid4().hex
    first, _, _ = submission(book, tmp_path / "first", count=1, body=config(resource=resource))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(book.claim, first, "s0", "0", sleep=lambda _: None) for _ in range(2)]
        claims = [future.result(timeout=30) for future in futures]
    assert sum(claim is not None for claim in claims) == 1
    original = next(claim for claim in claims if claim is not None)
    second, _, _ = submission(book, tmp_path / "second", count=1, body=config(resource=resource))
    assert book.claim(second, "s0", "0", sleep=lambda _: None) is None
    table = storage.tables(owner.dialect.name)["lease"]
    from datetime import UTC, datetime, timedelta
    with owner.begin() as conn:
        conn.execute(table.update().where(table.c.run_id == first).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    replacement = book.claim(second, "s0", "0", sleep=lambda _: None)
    assert replacement is not None and replacement.proof[0]["token"] > original.proof[0]["token"]
    with pytest.raises(DBAPIError, match="[Ss]tale"):
        book.heartbeat(original)


def test_mysql_expiry_during_completion_rolls_back_every_effect(control, tmp_path):
    from sqlalchemy.exc import DBAPIError
    from edgar_warehouse.workers import copy
    from tests.support.bookkeeping_protocol import RUNTIME, verification_for, verification_report
    owner, _, _, book, _ = control
    if owner.dialect.name != "mysql":
        pytest.skip("MySQL procedure-owned commit; retained PostgreSQL deferred-commit tests cover its boundary")
    run_id, _, _ = submission(book, tmp_path, count=1, body=config(seconds=2))
    envelope = book.tasks(run_id, book.profile)[0]
    book.report(envelope, copy.execute(envelope, book.artifacts), RUNTIME)
    verification = verification_for(book, run_id, "s0", "0", book.profile)
    report = verification_report(book, verification, copy)
    before = book.status(run_id)
    with owner.begin() as conn:
        conn.execute(text("CREATE TRIGGER invented_expiry BEFORE UPDATE ON bookkeeping_work_item FOR EACH ROW BEGIN IF NEW.state='verified' THEN DO SLEEP(3); END IF; END"))
    try:
        with pytest.raises(DBAPIError, match="[Ee]xpired"):
            book.verifier.admit(verification, report)
        assert book.status(run_id) == before
    finally:
        with owner.begin() as conn:
            conn.execute(text("DROP TRIGGER invented_expiry"))
    renewed = verification_for(book, run_id, "s0", "0", book.profile)
    assert renewed["claim"]["proof"][0]["token"] > verification["claim"]["proof"][0]["token"]
    book.verifier.admit(renewed, verification_report(book, renewed, copy))
    assert book.status(run_id)["counts"] == {"verified": 1}


def test_long_exact_control_keys_and_indexed_resource_read(control, tmp_path):
    from sqlalchemy import event
    owner, _, _, book, _ = control
    opaque = "Invented clé 雪 " * 400 + "  "
    run_id, _, _ = submission(book, tmp_path, count=1, body=config(resource=opaque),
                              key=lambda _: opaque, cursor=lambda _: {"resource_checkpoint": {
                                  "resource": opaque, "revision": 0, "position": -1}})
    complete(book, run_id, opaque, profile=book.profile)
    recorded = []
    def observe(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and "checkpoint" in statement:
            recorded.append((statement, parameters))
    event.listen(book.engine, "before_cursor_execute", observe)
    try:
        assert book.resource_checkpoint(opaque)["resource"] == opaque
        assert book.resource_checkpoint(opaque.rstrip()) is None
    finally:
        event.remove(book.engine, "before_cursor_execute", observe)
    if owner.dialect.name == "mysql":
        sql, params = recorded[0]
        with owner.connect() as conn:
            plan = list(conn.exec_driver_sql("EXPLAIN " + sql, params).mappings())
        assert any(row["key"] == "one_resource_checkpoint" and row["type"] in ("const", "ref", "eq_ref") for row in plan)


def test_mysql_pending_migration_denies_cached_normal_mutation(control, tmp_path):
    from sqlalchemy.exc import DBAPIError
    owner, _, _, book, _ = control
    if owner.dialect.name != "mysql":
        pytest.skip("MySQL nontransactional DDL only")
    run_id, _, _ = submission(book, tmp_path, count=1)
    before = book.status(run_id)
    with owner.begin() as conn:
        conn.execute(text("UPDATE bookkeeping_migrations SET complete=0 WHERE id=1"))
    with pytest.raises(DBAPIError, match="migration incomplete"):
        book.claim(run_id, "s0", "0")
    assert book.status(run_id) == before


def test_mysql_populated_interruption_revokes_both_cached_duties_and_recovers(control, tmp_path, monkeypatch):
    from sqlalchemy.exc import DBAPIError
    from edgar_warehouse.bookkeeping.clean import run_storage
    owner, worker_role, verifier_role, book, checksums = control
    if owner.dialect.name != "mysql":
        pytest.skip("MySQL nontransactional DDL only")
    run_id, _, _ = submission(book, tmp_path)
    complete(book, run_id, "0", profile=book.profile)
    before = book.status(run_id)
    with book.engine.connect() as worker, book.verifier.engine.connect() as verifier:
        for conn in (worker, verifier):
            conn.execute(text("SELECT * FROM bookkeeping_pipeline_run"))
            conn.commit()
        with owner.begin() as conn:
            conn.execute(text("UPDATE bookkeeping_migrations SET complete=0 WHERE id=1"))
        original = run_storage.execute_ddl
        def interrupted(conn, statement):
            if statement.startswith("DROP PROCEDURE IF EXISTS bookkeeping_start_run"):
                for cached in (worker, verifier):
                    with pytest.raises(DBAPIError):
                        cached.execute(text("SELECT * FROM bookkeeping_pipeline_run"))
                    cached.rollback()
                original(conn, statement)
                raise RuntimeError("Invented owner interruption")
            return original(conn, statement)
        with monkeypatch.context() as patch:
            patch.setattr(run_storage, "execute_ddl", interrupted)
            with pytest.raises(RuntimeError, match="owner interruption"):
                migrate(owner, runtime_role=worker_role, database_name=owner.url.database)
        for cached in (worker, verifier):
            with pytest.raises(DBAPIError):
                cached.execute(text("SELECT * FROM bookkeeping_pipeline_run"))
            cached.rollback()
        for role in (worker_role, verifier_role):
            assert migrate(owner, runtime_role=role, database_name=owner.url.database) == checksums
        assert book.status(run_id) == before
        assert book.verifier.status(run_id) == before
    complete(book, run_id, "1", profile=book.profile)
    assert book.status(run_id)["counts"] == {"verified": 2}


@pytest.mark.parametrize("drift", ["procedure", "index", "table", "trigger"])
def test_mysql_completed_control_refuses_drift_without_recreating_storage(control, drift):
    from sqlalchemy.exc import DBAPIError
    from edgar_warehouse.control_contract import Blocked
    owner, role, _, book, _ = control
    if owner.dialect.name != "mysql":
        pytest.skip("MySQL completed owner readback only")
    sql = {"procedure": "DROP PROCEDURE bookkeeping_claim",
           "index": "ALTER TABLE bookkeeping_checkpoint DROP INDEX one_resource_checkpoint",
           "table": "DROP TABLE bookkeeping_checkpoint",
           "trigger": "CREATE TRIGGER invented_untracked BEFORE UPDATE ON bookkeeping_work_item FOR EACH ROW SET NEW.error=NEW.error"}[drift]
    with owner.begin() as conn:
        conn.execute(text(sql))
    with pytest.raises(Blocked, match="differs|differ"):
        migrate(owner, runtime_role=role, database_name=owner.url.database)
    with pytest.raises(DBAPIError):
        book.runs()
    if drift == "table":
        from sqlalchemy import inspect
        assert not inspect(owner).has_table("bookkeeping_checkpoint")


@pytest.mark.parametrize("altered", [False, True])
def test_mysql_initial_marker_recovery_requires_original_metadata(database_factory, monkeypatch, altered):
    from sqlalchemy.engine import Connection
    from edgar_warehouse.control_contract import Blocked
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") != "mysql":
        pytest.skip("MySQL first-DDL interruption only")
    with database_factory() as (owner, _, role):
        original = Connection.execute
        def interrupted(conn, statement, *args, **kwargs):
            if str(statement).startswith("INSERT INTO bookkeeping_migrations"):
                raise RuntimeError("Invented marker interruption")
            return original(conn, statement, *args, **kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(Connection, "execute", interrupted)
            with pytest.raises(RuntimeError, match="marker interruption"):
                migrate(owner, runtime_role=role, database_name=owner.url.database)
        if altered:
            with owner.begin() as conn:
                conn.execute(text("ALTER TABLE bookkeeping_migrations ADD surprise BIGINT"))
            with pytest.raises(Blocked, match="Untracked control migration"):
                migrate(owner, runtime_role=role, database_name=owner.url.database)
        else:
            assert migrate(owner, runtime_role=role, database_name=owner.url.database)


def test_mysql_legacy_caller_held_guard_is_explicitly_unsupported(database_factory):
    from types import SimpleNamespace
    from sqlalchemy import inspect
    from edgar_warehouse.control_contract import Blocked
    from edgar_warehouse.bookkeeping.clean.destinations import guard, migrate_guard
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") != "mysql":
        pytest.skip("The legacy PostgreSQL deferred-commit guard remains qualified separately")
    with database_factory() as (owner, runtime, role):
        before = inspect(owner).get_table_names()
        with pytest.raises(Blocked, match="PostgreSQL"):
            migrate_guard(owner, runtime_role=role)
        with owner.connect() as conn:
            with pytest.raises(Blocked, match="PostgreSQL"):
                guard(conn, SimpleNamespace(proof=[]))
        assert inspect(owner).get_table_names() == before


def test_failed_journal_verification_retains_intent_and_retries_the_same_event(control, database_factory, tmp_path, monkeypatch):
    from edgar_warehouse.change_journal import ChangeJournal
    from edgar_warehouse.change_journal.database import migrate as migrate_journal
    _, _, _, book, _ = control
    run_id, _, _ = submission(book, tmp_path, count=1)
    complete(book, run_id, "0", profile=book.profile)
    with database_factory() as (owner, runtime, role):
        migrate_journal(owner, runtime_role=role, database_name=owner.url.database)
        journal = ChangeJournal(runtime)
        # This is a valid Python exception name and an opaque error string.
        failure = type("null", (Exception,), {})
        def unavailable(*args, **kwargs):
            raise failure("Invented unavailable readback")
        with monkeypatch.context() as patch:
            patch.setattr(journal, "verify", unavailable)
            with pytest.raises(failure):
                book.deliver(journal, run_id)
        state = book.status(run_id)
        assert state["pending_deliveries"] == 1 and state["deliveries"][0]["error"] == "null"
        assert journal.status()["events"] == 1
        assert book.deliver(journal, run_id) == 1
        assert book.deliver(journal, run_id) == 0 and journal.status()["events"] == 1


def test_worker_and_verifier_runtime_changes_rollback_without_repinning(control, tmp_path):
    from sqlalchemy.exc import DBAPIError
    from edgar_warehouse.workers import copy
    from tests.support.bookkeeping_protocol import RUNTIME, verification_for, verification_report
    _, _, _, book, _ = control
    run_id, _, _ = submission(book, tmp_path)
    complete(book, run_id, "0", profile=book.profile)
    envelope = book.tasks(run_id, book.profile)[0]
    candidate = copy.execute(envelope, book.artifacts)
    before = book.status(run_id)
    with pytest.raises(DBAPIError, match="worker runtime changed"):
        book.report(envelope, candidate, "b" * 64)
    assert book.status(run_id) == before
    book.report(envelope, candidate, RUNTIME)
    verification = verification_for(book, run_id, "s0", "1", book.profile)
    original = verification_report(book, verification, copy)
    changed = book.artifacts.put(tmp_path.as_uri() + "/reports", {**book.artifacts.json(original), "runtime": "b" * 64})
    before = book.status(run_id)
    with pytest.raises(DBAPIError, match="verifier runtime changed"):
        book.verifier.admit(verification, changed)
    assert book.status(run_id) == before
    book.verifier.admit(verification, original)
    assert book.status(run_id)["counts"] == {"verified": 2}
