"""The Rules Database on the selected engine: the digests runs used, recorded once, under a restricted role."""
import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.rules import frozen
from edgar_warehouse.rules.db import TABLE, Rules, migrate


def pipeline(seconds=60):
    return {"pipeline": "invented.pipeline", "bookkeeping": {"version": 1, "targets": {"copy": {
        "lease_seconds": seconds, "heartbeat_seconds": 30, "retry": {"attempts": 2, "base_ms": 1, "cap_ms": 2},
        "allow_zero_work": False,
        "steps": [{"name": "copy", "operation": "artifact.copy", "requires": [], "key": "{id}",
                   "leases": ["output:{destination}"], "checks": ["input.hash", "output.receipt"]}],
        "checks": ["manifest.hash", "work.accounting", "journal.delivered"]}}}}


def test_a_runs_rules_are_recorded_once_and_read_back(database_factory, monkeypatch, capsys):
    with database_factory() as (owner, runtime, role):
        if owner.dialect.name == "mssql":
            pytest.skip("The Rules Database is qualified on PostgreSQL and MySQL")
        assert migrate(owner, agent_role=role) == {"table": TABLE}
        assert migrate(owner, agent_role=role) == {"table": TABLE}  # rerunning changes nothing
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

        monkeypatch.setenv("RULES_DATABASE_URL", runtime.url.render_as_string(hide_password=False))
        assert main(["rules", "status", "--pipeline", "invented.pipeline"]) == 0
        assert [row["digest"] for row in json.loads(capsys.readouterr().out)] == [first["digest"], changed["digest"]]
