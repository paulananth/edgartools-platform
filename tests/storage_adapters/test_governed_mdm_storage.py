"""Normal governed-store installation on the first-priority MDM engines."""

import copy
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from hashlib import sha256
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import event, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.schema import CreateSchema

from edgar_warehouse.mdm.clean import catalog
from edgar_warehouse.mdm.clean.store import (
    current_reading,
    migrate,
    reading_at,
    register_policy,
)
from tests.engine.test_data_skill_bundle_postgres import installed  # noqa: F401
from tests.support.rules_authority import register_dataset


@pytest.fixture
def database(database_factory):
    """Owner migrations require a clean database for every recovery case."""
    with database_factory() as isolated:
        yield isolated


def test_registry_retains_exact_configuration_numbers(database, storage_api):
    owner, _, role = database
    metadata, _ = storage_api.native_registry_model(owner.dialect.name)
    body = {
        "version": "invented-policy",
        "required_consumers": ["invented"],
        "automatic_rules": [],
        "threshold": 10**80 + 1,
    }
    digest = sha256(storage_api.canonical(body)).hexdigest()
    if owner.dialect.name == "mysql":
        from edgar_warehouse.mdm.clean.store import migrate

        migrate(owner, application_role=role)
    with owner.begin() as conn:
        if owner.dialect.name != "mysql":
            if metadata.schema:
                conn.execute(CreateSchema(metadata.schema))
            metadata.create_all(conn)
        storage_api.retain_policy(conn, body, digest)
        assert storage_api.registered_policy(conn, digest) == body
        assert storage_api.registered_policies(conn) == [body]


COMMON = [
    "registration",
    "read_only",
    "immutable",
    "interrupted_first",
    "interrupted_populated",
    "schema_drift",
    "checksum_drift",
    "column_privilege",
    "owner_is_runtime",
    "cli",
]
MYSQL = [
    "empty_marker",
    "wrong_configuration",
    "vocabulary_upgrade",
    "grant_option",
    "untracked",
    "missing_table",
    "missing_guard",
    "prepared_retention",
    "held_registry_transaction",
]
SELECTED = os.environ.get("SKILL_ADAPTER_TEST_ENGINE")
CASES = (
    COMMON + MYSQL
    if SELECTED == "mysql"
    else COMMON
    if SELECTED == "postgresql"
    else ["deferred"]
)


def seed(owner):
    policy = {
        "version": "invented-policy",
        "required_consumers": ["invented"],
        "automatic_rules": [],
        "threshold": 10**80 + 1,
    }
    contract = {
        "provider": "fixture",
        "family": "fixture",
        "schema_version": "1",
        "record_key": "key",
        "publication_key": "revision",
        "effective_time": "effective_at",
        "semantics": "patch",
    }
    with owner.begin() as conn:
        digest = register_policy(conn, policy)
        register_dataset(conn, "invented.source", str(uuid4()), contract)
        first = current_reading(conn, "invented.source")
        register_dataset(
            conn, "invented.source", str(uuid4()), {**contract, "schema_version": "2"}
        )
        second = current_reading(conn, "invented.source")
    return policy, digest, first, second


@pytest.mark.parametrize("case", CASES)
def test_normal_governed_storage(case, database, storage_api, monkeypatch):
    owner, runtime, role = database
    mysql = owner.dialect.name == "mysql"
    quote = owner.dialect.identifier_preparer.quote
    table = quote("policy") if mysql else "mdm.policy"
    principal = "'" + role + "'@'%'" if mysql else quote(role)
    if case == "deferred":
        with pytest.raises(ValueError, match="requires PostgreSQL"):
            migrate(owner, application_role=role)
        return
    if case == "owner_is_runtime":
        with pytest.raises(ValueError):
            migrate(owner, application_role=owner.url.username)
        assert inspect(owner).get_table_names(schema=None if mysql else "mdm") == []
        return
    if case == "untracked":
        with owner.begin() as conn:
            conn.execute(text("CREATE TABLE unique_untracked (id INTEGER PRIMARY KEY)"))
        with pytest.raises(ValueError, match="unrelated|untracked"):
            migrate(owner, application_role=role)
        assert inspect(owner).get_table_names() == ["unique_untracked"]
        return
    if case in {"interrupted_first", "empty_marker"}:

        def interrupt(conn, cursor, statement, params, context, many):
            needle = (
                "INSERT INTO registry_migration"
                if case == "empty_marker"
                else "CREATE TABLE policy"
                if mysql
                else "CREATE SCHEMA mdm"
            )
            if needle in statement:
                raise RuntimeError("invented installation interruption")

        event.listen(owner, "before_cursor_execute", interrupt)
        try:
            with pytest.raises(RuntimeError, match="installation interruption"):
                migrate(owner, application_role=role)
        finally:
            event.remove(owner, "before_cursor_execute", interrupt)
        if mysql:
            with pytest.raises((storage_api.AdapterError, DBAPIError)):
                with runtime.connect() as conn:
                    storage_api.registered_policies(conn)
        else:
            assert not inspect(owner).has_schema("mdm")
    first_migration = migrate(owner, application_role=role)
    assert first_migration["installed"]
    policy, digest, first, second = seed(owner)
    with runtime.connect() as opened:
        assert storage_api.registered_policy(opened, digest) == policy
        assert reading_at(opened, "invented.source", 1) == first
        opened.commit()
        if case == "registration":
            assert not migrate(owner, application_role=role)["installed"]
            assert current_reading(opened, "invented.source") == second
            assert reading_at(opened, "invented.source", 1) == first
            assert storage_api.registered_policy(opened, digest) == policy
        elif case == "held_registry_transaction":
            assert storage_api.registered_policy(opened, digest) == policy
            reached = Event()

            def observe(conn, cursor, statement, params, context, many):
                if "UPDATE registry_state SET complete" in statement:
                    reached.set()

            event.listen(owner, "before_cursor_execute", observe)
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(migrate, owner, application_role=role)
                    try:
                        assert reached.wait(10), "owner did not reach readiness barrier"
                        with pytest.raises(TimeoutError):
                            future.result(timeout=0.1)
                        assert storage_api.registered_policy(opened, digest) == policy
                    finally:
                        opened.rollback()
                    assert not future.result(timeout=30)["installed"]
            finally:
                event.remove(owner, "before_cursor_execute", observe)
        elif case == "read_only":
            with pytest.raises(DBAPIError), runtime.begin() as conn:
                register_policy(conn, {**policy, "version": "not-authorized"})
            with pytest.raises(DBAPIError), runtime.begin() as conn:
                conn.execute(text(f"DELETE FROM {table}"))
            if mysql:
                api = storage_api.Adapter(runtime, prefix="mdm_store", protocol=4)
                with pytest.raises(
                    storage_api.AdapterError, match="database_operation_failed"
                ):
                    api.claim("unqualified-normal-merge", "writer")
        elif case == "immutable":
            with pytest.raises(DBAPIError), owner.begin() as conn:
                conn.execute(text(f"UPDATE {table} SET body=body"))
            with pytest.raises(DBAPIError), owner.begin() as conn:
                conn.execute(text(f"DELETE FROM {table}"))
        elif case == "interrupted_populated":
            seen = []

            def interrupt(conn, cursor, statement, params, context, many):
                needle = (
                    "UPDATE master_kind SET enabled"
                    if mysql
                    else "REVOKE ALL ON ALL TABLES IN SCHEMA mdm"
                )
                if needle in statement:
                    if mysql:
                        with pytest.raises(storage_api.AdapterError, match="pending"):
                            storage_api.registered_policy(opened, digest)
                        opened.rollback()
                    seen.append(True)
                    raise RuntimeError("invented populated interruption")

            event.listen(owner, "before_cursor_execute", interrupt)
            try:
                with pytest.raises(RuntimeError, match="populated interruption"):
                    migrate(owner, application_role=role)
            finally:
                event.remove(owner, "before_cursor_execute", interrupt)
            assert seen
            migrate(owner, application_role=role)
        elif case == "schema_drift":
            with owner.begin() as conn:
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN invented_extra INTEGER")
                )
            with pytest.raises(ValueError, match="registry columns differ"):
                migrate(owner, application_role=role)
            if mysql:
                with pytest.raises(storage_api.AdapterError, match="pending"):
                    storage_api.registered_policy(opened, digest)
                opened.rollback()
            with owner.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} DROP COLUMN invented_extra"))
            migrate(owner, application_role=role)
        elif case in {"missing_table", "missing_guard"}:
            from registry_migration import contract

            _, _, statements, guards, _ = contract()
            with owner.begin() as conn:
                conn.execute(
                    text(
                        "DROP TABLE master_kind"
                        if case == "missing_table"
                        else "DROP TRIGGER policy_immutable_update"
                    )
                )
            # A pending retry must not disguise an installed object as new.
            for _ in range(2):
                with pytest.raises(
                    ValueError, match="registry (table|guard) is missing"
                ):
                    migrate(owner, application_role=role)
                with pytest.raises(storage_api.AdapterError, match="pending"):
                    storage_api.registered_policy(opened, digest)
                opened.rollback()
            with owner.begin() as conn:
                conn.exec_driver_sql(
                    statements["master_kind"]
                    if case == "missing_table"
                    else guards["policy_immutable_update"][3]
                )
            migrate(owner, application_role=role)
        elif case == "prepared_retention":
            from tests.storage_adapters.test_prepared_effects import batch

            adapter = storage_api.Adapter(owner, prefix="mdm_store", protocol=4)
            request = batch(
                storage_api, pins={"policy": digest, "configuration": catalog.CATALOG}
            )
            lease = adapter.claim(request.scope, "owner-fixture")
            adapter.apply(request, lease)
            retained = (
                "current",
                "history",
                "evidence",
                "outbox",
                "batch",
                "checkpoint",
                "gate",
            )

            def snapshot():
                with owner.connect() as conn:
                    return {
                        name: [
                            dict(row)
                            for row in conn.execute(
                                select(adapter.tables[name])
                            ).mappings()
                        ]
                        for name in retained
                    }

            before = snapshot()
            migrate(owner, application_role=role)
            assert snapshot() == before
            assert adapter.apply(request, lease)["duplicate"]
        elif case == "checksum_drift":
            ledger = "registry_migration" if mysql else "mdm.migration"
            predicate = "version=1" if mysql else "name='001_mdm.sql'"
            with owner.begin() as conn:
                old = conn.scalar(
                    text(f"SELECT checksum FROM {ledger} WHERE {predicate}")
                )
                if not mysql:
                    conn.execute(
                        text("ALTER TABLE mdm.migration DISABLE TRIGGER immutable_row")
                    )
                conn.execute(
                    text(f"UPDATE {ledger} SET checksum=:h WHERE {predicate}"),
                    {"h": "0" * 64},
                )
                if not mysql:
                    conn.execute(
                        text("ALTER TABLE mdm.migration ENABLE TRIGGER immutable_row")
                    )
            with pytest.raises(ValueError, match="checksum differs"):
                migrate(owner, application_role=role)
            with owner.begin() as conn:
                if not mysql:
                    conn.execute(
                        text("ALTER TABLE mdm.migration DISABLE TRIGGER immutable_row")
                    )
                conn.execute(
                    text(f"UPDATE {ledger} SET checksum=:h WHERE {predicate}"),
                    {"h": old},
                )
                if not mysql:
                    conn.execute(
                        text("ALTER TABLE mdm.migration ENABLE TRIGGER immutable_row")
                    )
            migrate(owner, application_role=role)
        elif case in {"column_privilege", "grant_option"}:
            grant = "UPDATE(body)" if case == "column_privilege" else "SELECT"
            suffix = "" if case == "column_privilege" else " WITH GRANT OPTION"
            inherited = quote(role + "_inherited") if not mysql else None
            target = inherited or principal
            with owner.begin() as conn:
                if inherited:
                    conn.execute(text(f"CREATE ROLE {inherited}"))
                    conn.execute(text(f"GRANT {inherited} TO {principal}"))
                conn.execute(text(f"GRANT {grant} ON {table} TO {target}{suffix}"))
            try:
                with pytest.raises(ValueError, match="writes|privileges"):
                    migrate(owner, application_role=role)
            finally:
                revoke = (
                    f"REVOKE {grant} ON {table} FROM {target}"
                    if case == "column_privilege"
                    else f"REVOKE GRANT OPTION ON {table} FROM {target}"
                )
                with owner.begin() as conn:
                    conn.execute(text(revoke))
                    if inherited:
                        conn.execute(text(f"REVOKE {inherited} FROM {principal}"))
                        conn.execute(text(f"DROP ROLE {inherited}"))
            migrate(owner, application_role=role)
        elif case == "wrong_configuration":
            changed = {**catalog.CATALOG, "version": "invented-different-build"}
            monkeypatch.setattr(catalog, "CATALOG", changed)
            with pytest.raises(ValueError, match="vocabulary differs"):
                register_policy(opened, {**policy, "version": "changed"})
            opened.rollback()
            monkeypatch.undo()
        elif case == "vocabulary_upgrade":
            changed = copy.deepcopy(catalog.CATALOG)
            old_kind = changed["kinds"][0]
            changed["kinds"] = [k for k in changed["kinds"] if k != old_kind] + [
                "invented-kind"
            ]
            monkeypatch.setattr(catalog, "CATALOG", changed)
            migrate(owner, application_role=role)
            with owner.connect() as conn:
                rows = dict(
                    conn.execute(text("SELECT kind,enabled FROM master_kind")).all()
                )
                assert rows[old_kind] == 0 and rows["invented-kind"] == 1
                assert conn.scalar(text("SELECT COUNT(*) FROM registry_catalog")) == 2
            monkeypatch.undo()
            migrate(owner, application_role=role)
        elif case == "cli":
            env = {
                **os.environ,
                "MDM_DATABASE_URL": owner.url.render_as_string(hide_password=False),
            }
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from edgar_warehouse.cli import main; raise SystemExit(main())",
                    "mdm",
                    "migrate",
                    "--application-role",
                    role,
                ],
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )
            assert result.returncode == 0, "normal owner migration CLI failed"
            assert json.loads(result.stdout)["installed"] is False
        assert storage_api.registered_policy(opened, digest) == policy
        assert reading_at(opened, "invented.source", 1) == first
        assert current_reading(opened, "invented.source") == second


def test_registry_contract_is_stable_across_hash_seeds(storage_api):
    values = []
    for seed in ("1", "2", "37"):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from registry_migration import contract; print(contract()[-1])",
            ],
            env={
                **os.environ,
                "PYTHONHASHSEED": seed,
                "PYTHONPATH": str(Path(storage_api.__file__).parent),
            },
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, "registry contract subprocess failed"
        values.append(result.stdout.strip())
    assert len(set(values)) == 1 and len(values[0]) == 64


def test_governed_store_runs_from_installed_bundle(installed, database):
    """Normal owner command and restricted reads with no checkout imports."""
    python, root = installed
    owner, runtime, role = database
    code = """
import json, os
from pathlib import Path
from types import SimpleNamespace
from sqlalchemy.engine import make_url
from edgar_warehouse.database_connections import storage_adapter
from edgar_warehouse.mdm.clean.connections import engine_from_env
from edgar_warehouse.mdm.clean.store import migrate, register_policy
api=storage_adapter()
assert "bundle_data" in str(Path(api.__file__).resolve())
selected=make_url(os.environ["MDM_DATABASE_URL"]).get_backend_name()
owner=(SimpleNamespace(dialect=SimpleNamespace(name="mssql")) if selected=="mssql" else
       engine_from_env("MDM_DATABASE_URL",restricted=False))
if owner.dialect.name=="mssql":
    try:migrate(owner,application_role=os.environ["TEST_RUNTIME_ROLE"])
    except ValueError:pass
    else:raise AssertionError("SQL Server normal owner path must remain deferred")
else:
    from edgar_warehouse.cli import main
    assert main(["mdm","migrate","--application-role",os.environ["TEST_RUNTIME_ROLE"]])==0
    body={"version":"invented-installed-policy","required_consumers":["invented"],
          "automatic_rules":[],"threshold":10**80+1}
    with owner.begin() as conn:pin=register_policy(conn,body)
    runtime=engine_from_env("TEST_RUNTIME_URL")
    with runtime.connect() as conn:assert api.registered_policy(conn,pin)==body
    assert not migrate(owner,application_role=os.environ["TEST_RUNTIME_ROLE"])["installed"]
print(json.dumps({"passed":True}))
"""
    result = subprocess.run(
        [str(python), "-I", "-c", code],
        cwd=root,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "MDM_DATABASE_URL": owner.url.render_as_string(hide_password=False),
            "TEST_RUNTIME_URL": runtime.url.render_as_string(hide_password=False),
            "TEST_RUNTIME_ROLE": role,
            "MDM_APPLICATION_ROLE": role,
        },
        timeout=90,
    )
    assert result.returncode == 0, "installed normal governed-store caller failed"
    assert json.loads(result.stdout.splitlines()[-1]) == {"passed": True}
