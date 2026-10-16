"""Real Docker PG16: six stores, independent agents, restart and exact restore."""
import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from tests.unit.test_local_test_stores import local


def test_two_agents_keep_their_data_and_restore_all_six_stores(tmp_path):
    root = tmp_path / "stores"
    first = local.LocalStores(root, tmp_path / "first-worktree")
    second = local.LocalStores(root, tmp_path / "second-worktree")
    one, two = "one-" + uuid4().hex[:10], "two-" + uuid4().hex[:10]
    restored = "copy-" + uuid4().hex[:10]
    try:
        with first.locked(one):
            first.start(one)
            first.start(one)  # repeated provisioning changes no rows
        with second.locked(two):
            second.start(two)
        # Each store has its own restricted login; it cannot create tables.
        for database, (_, schema) in local.STORES.items():
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
        with pytest.raises(ValueError, match="another worktree"):
            second.start(one)
        with first.locked(one):
            first.stop(one)
            first.start(one)
        assert first.contents(one) == expected
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
