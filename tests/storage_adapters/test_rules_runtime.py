"""The Rules Database on the selected engine: the digests runs used, recorded once, under a restricted role."""
import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.support.duty import duty_url
from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.rules import frozen
from edgar_warehouse.rules.db import TABLE, Rules, migrate
from tests.support.rules_authority import register_dataset


def pipeline(seconds=60):
    return {"pipeline": "invented.pipeline", "bookkeeping": {"version": 1, "targets": {"copy": {
        "lease_seconds": seconds, "heartbeat_seconds": 30, "retry": {"attempts": 2, "base_ms": 1, "cap_ms": 2},
        "allow_zero_work": False,
        "steps": [{"name": "copy", "operation": "artifact.copy", "requires": [], "key": "{id}",
                   "leases": ["output:{destination}"], "checks": ["input.hash", "output.receipt"]}],
        "checks": ["manifest.hash", "work.accounting", "journal.delivered"]}}}}


def test_a_runs_rules_are_recorded_once_and_read_back(database_factory, monkeypatch, capsys):
    with database_factory(store="rules") as (owner, runtime, role):
        if owner.dialect.name == "mssql":
            pytest.skip("The Rules Database is qualified on PostgreSQL and MySQL")
        made = {"tables": sorted([TABLE, "policy", "dataset_reading", "draft"])}
        assert migrate(owner, agent_role=role) == made
        assert migrate(owner, agent_role=role) == made  # rerunning changes nothing
        rules = Rules(runtime)
        first, changed = frozen.of("pipeline", "invented.pipeline", pipeline()), \
            frozen.of("pipeline", "invented.pipeline", pipeline(seconds=90))
        rules.record(first)
        rules.record(first)  # the same digest again is left as it is
        rules.record(changed)
        history = rules.history("pipeline", "invented.pipeline")
        assert [row["digest"] for row in history] == [first["digest"], changed["digest"]]
        assert rules.body("pipeline", "invented.pipeline", first["digest"]) == first["body"]
        with pytest.raises(Blocked, match="No run recorded"):
            rules.body("pipeline", "invented.pipeline", "0" * 64)
        with pytest.raises(Blocked, match="digest is not their body's"):
            rules.record({**first, "digest": "0" * 64})
        # The runtime role adds to the record and never changes it.
        target = f"rules.{TABLE}" if owner.dialect.name == "postgresql" else TABLE
        with pytest.raises(DBAPIError), runtime.begin() as conn:
            conn.execute(text(f"DELETE FROM {target}"))
        from edgar_warehouse.cli import main

        monkeypatch.setenv("CONTROL_URL", duty_url(runtime, "rules"))
        assert main(["rules", "status", "--pipeline", "invented.pipeline"]) == 0
        assert [row["digest"] for row in json.loads(capsys.readouterr().out)] == [first["digest"], changed["digest"]]


def test_a_draft_is_stored_once_and_the_runtime_cannot_change_it(database_factory):
    with database_factory(store="rules") as (owner, runtime, role):
        if owner.dialect.name == "mssql":
            pytest.skip("The Rules Database is qualified on PostgreSQL and MySQL")
        migrate(owner, agent_role=role)
        rules = Rules(runtime)
        body = {"trim": "quantity", "version": "draft-1"}
        case = {"family": "example", "inputs": {}, "expected": None, "actual": None, "passed": True,
                "rule": '{"trim": "quantity", "version": "draft-1"}'}
        saved = rules.save(kind="try", name="example", version="draft-1", body=body, case=case)
        assert saved["status"] == "draft"
        assert saved["digest"] == "d7097b4a191ff17f3098239ce47cc828375d3dc088e6b3ad1ee6178019a6e9fb"
        assert rules.save(kind="try", name="example", version="draft-1", body=body, case={"family": "example"}) == saved
        found = rules.draft("try", "example", "draft-1")
        assert found["body"] == body
        assert found["case"] == case
        assert found["status"] == "draft"
        with pytest.raises(Blocked, match="already stored"):
            rules.save(kind="try", name="example", version="draft-1",
                       body={"trim": "other", "version": "draft-1"}, case=case)
        assert rules.draft("try", "example", "draft-1")["body"] == body
        upper = {"trim": "quantity", "version": "Draft-1"}
        rules.save(kind="try", name="example", version="Draft-1", body=upper, case=case)
        assert rules.draft("try", "example", "Draft-1")["body"] == upper
        assert rules.draft("try", "example", "draft-1")["body"] == body
        prefix = "rules." if owner.dialect.name == "postgresql" else ""
        for sql in (f"DELETE FROM {prefix}draft", f"UPDATE {prefix}draft SET status='active'"):
            with pytest.raises(DBAPIError), runtime.begin() as conn:
                conn.execute(text(sql))


def test_the_registry_keeps_each_policy_and_each_reading_and_the_runtime_only_reads_it(database_factory):
    """The merge rules and the Dataset Contracts MDM runs by, registered in the Rules Database: a policy under its
    digest, each reading numbered from 1, nothing changed in place, a rolled-back registration leaving nothing."""
    from edgar_warehouse.mdm.store import current_reading, reading_at, register_policy
    from edgar_warehouse.rules import registry

    with database_factory(store="rules") as (owner, runtime, role):
        if owner.dialect.name == "mssql":
            pytest.skip("The Rules Database is qualified on PostgreSQL and MySQL")
        migrate(owner, agent_role=role)
        body = {"version": "invented-approved", "required_consumers": ["invented"], "automatic_rules": []}
        with owner.begin() as conn:
            pin = register_policy(conn, body)
        with owner.begin() as conn:
            assert register_policy(conn, body) == pin  # registering again changes nothing
        contract = {"provider": "fixture", "family": "fixture", "schema_version": "1", "record_key": "key",
                    "publication_key": "revision", "effective_time": "effective_at", "semantics": "patch"}
        with owner.begin() as conn:
            register_dataset(conn, "invented.source", "invented-registry", contract)
            register_dataset(conn, "invented.source", "invented-registry", {**contract, "schema_version": "2"})
        with pytest.raises(RuntimeError, match="invented interruption"), owner.begin() as conn:
            rejected = register_policy(conn, {**body, "version": "invented-rolled-back"})
            register_dataset(conn, "invented.source", "invented-registry", {**contract, "schema_version": "3"})
            raise RuntimeError("invented interruption")
        with runtime.connect() as conn:
            assert registry.policy(conn, pin) == body and registry.policy(conn, rejected) is None
            version, latest = current_reading(conn, "invented.source")
            assert (version, latest["schema_version"]) == (2, "2")
            assert reading_at(conn, "invented.source", 1)[1]["schema_version"] == "1"
            assert registry.first_contracts(conn, ["invented.source"])["invented.source"]["schema_version"] == "1"
        with pytest.raises(ValueError, match="A Dataset Contract names provider"), owner.begin() as conn:
            register_dataset(conn, "invented.other", "invented-registry", {k: v for k, v in contract.items()
                                                                           if k != "provider"})
        prefix = "rules." if owner.dialect.name == "postgresql" else ""
        for sql in (f"DELETE FROM {prefix}policy", f"UPDATE {prefix}dataset_reading SET body='{{}}'",
                    f"INSERT INTO {prefix}policy(digest, body, registered_at) VALUES ('x', '{{}}', CURRENT_TIMESTAMP)"):
            with pytest.raises(DBAPIError), runtime.begin() as conn:
                conn.execute(text(sql))
