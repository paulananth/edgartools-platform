"""Destination-owned prepared-command lifecycle, before normal caller admission."""

import os
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from threading import Barrier

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError

from tests.storage_adapters.test_prepared_effects import batch

CASES = (
    ["deferred"]
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql"
    else [
        "inline",
        "standalone",
        "missing",
        "mismatch",
        "rejected",
        "superseded",
        "generation",
        "duplicate_observer",
        "observer_pins",
        "alternatives",
        "rollback",
        "competing",
        "collision",
        "grants",
        "upgrade",
        "unregistered",
        "unicode_pins",
        "revoked_duplicate",
        "all_effects",
        "stale_index",
        "input_publication",
        "no_input_publication",
        "migration_rerun",
        "stored_replay",
        "proposal_without_pins",
        "deferred_activation",
        "activation_rollback",
        "producer_payload",
        "required_references",
        "preview",
    ]
)


@pytest.mark.parametrize("case", CASES)
def test_governed_command_admission(case, database_factory, storage_api):
    with database_factory() as (owner, runtime, role):
        if case == "deferred":
            with pytest.raises(storage_api.AdapterError, match="SQL Server"):
                storage_api.migrate(owner, runtime_role=role, protocol=5)
            return
        prefix = "invented_admission"
        protocol = 4 if case == "upgrade" else 5
        deferred_activation = case in ("deferred_activation", "activation_rollback")
        storage_api.migrate(owner, runtime_role=role, prefix=prefix, protocol=protocol,
                            runtime_execute=not deferred_activation,
                            defer_ready=deferred_activation)
        api = storage_api.Adapter(runtime, prefix=prefix, protocol=protocol)
        b = batch(
            storage_api,
            governed=protocol == 5,
            indexes=(storage_api.IndexChange("invented-lookup", "one", {"ref": "one"}),),
            objects=(storage_api.Effect("invented-kind", "one", {"value": 1}),),
        )
        if case == "unicode_pins":
            b = replace(b, pins={'invented."pin/😀': "invented-ß-值"})
        if deferred_activation:
            admin = storage_api.Adapter(owner, prefix=prefix, protocol=5)
            with pytest.raises(storage_api.AdapterError):
                api.claim(b.scope, "invented-worker")
            if case == "activation_rollback":
                with pytest.raises(RuntimeError, match="invented interruption"), owner.begin() as conn:
                    admin.activate(conn, b.pins)
                    raise RuntimeError("invented interruption")
                with pytest.raises(storage_api.AdapterError, match="storage_not_initialized"):
                    admin.enable_runtime(role)
            with owner.begin() as conn:
                admin.activate(conn, b.pins)
            admin.enable_runtime(role)
        if protocol == 5:
            with owner.begin() as conn:
                for name, value in b.pins.items():
                    api.admit_pin(conn, name, value)
        lease = api.claim(b.scope, "invented-worker")
        body = {"command": "invented-command", "outcome": "ready"}

        def count(name):
            with owner.connect() as conn:
                return conn.scalar(select(func.count()).select_from(api.tables[name]))

        if case == "preview":
            names = ("batch", "proposal", "proposal_event", "current", "history",
                     "evidence", "lookup", "checkpoint", "outbox", "run")
            assert api.preview(b, proposal_body=body)["generation"] == 1
            assert api.generation() == 0 and all(count(name) == 0 for name in names)
            invalid = replace(b, indexes=(storage_api.IndexChange(
                "invented-lookup", "one", {"ref": "one"}, expected_version=1),))
            with pytest.raises(storage_api.AdapterError, match="stale_index_version"):
                api.preview(invalid, proposal_body=body)
            assert api.generation() == 0 and all(count(name) == 0 for name in names)
            api.apply(b, lease, proposal_body=body)
            before = {name: count(name) for name in names}
            assert api.preview(b, proposal_body=body)["duplicate"]
            assert before == {name: count(name) for name in names}
            return

        if case == "producer_payload":
            payload = storage_api.ProducerPayload(b'{"content":"invented","origin":', b'}')
            changed = replace(b, payloads={c: payload for c in b.consumers})
            proposal = api.record_proposal(b.batch, body, b.run, outcome="ready",
                                           expected_generation=0, intent=changed.intent())
            producer = 'invented-producer-"😀'
            api.apply(changed, lease, proposal_key=proposal, observer=producer)
            with runtime.connect() as conn:
                rows = conn.execute(select(api.tables["outbox"])).mappings().all()
                assert len(rows) == 2
                for row in rows:
                    raw = bytes(row["payload"])
                    assert json.loads(raw) == {"content": "invented", "origin": producer}
                    assert raw == payload.before + storage_api.canonical(producer) + payload.after
                    assert row["payload_hash"] == sha256(raw).hexdigest()
            assert api.read_batch(b.batch)["run_key"] == storage_api.key(producer)
            api.replay(b.batch, lease, observer="another-observer")
            with runtime.connect() as conn:
                assert [bytes(row[0]) for row in conn.execute(select(api.tables["outbox"].c.payload))] == [raw, raw]
            return
        if case == "required_references":
            b = replace(b, required_pins={"invented-mapping": "one"})
            with pytest.raises(storage_api.AdapterError, match="unregistered_frozen_pins"):
                api.apply(b, lease, proposal_body=body)
            with owner.begin() as conn:
                api.admit_pin(conn, "invented-mapping", "one")
                api.admit_pin(conn, "invented-mapping", "two")
            api.apply(b, lease, proposal_body=body)
            other = replace(b, batch="another-command", expected_generation=1,
                            expected_checkpoint=1, checkpoint=2, objects=(), evidence=(), indexes=(),
                            required_pins={"invented-mapping": "two"})
            api.apply(other, lease, proposal_body={"command": "another"})
            assert api.replay(b.batch, lease, observer=b.run)["duplicate"]
            return

        if deferred_activation:
            assert api.apply(b, lease, proposal_body=body)["generation"] == 1
            storage_api.migrate(owner, runtime_role=role, prefix=prefix, protocol=5,
                                runtime_execute=False, defer_ready=True)
            with pytest.raises(storage_api.AdapterError):
                api.replay(b.batch, lease, observer="during-migration")
            with owner.begin() as conn:
                admin.activate(conn, b.pins)
            admin.enable_runtime(role)
            assert api.replay(b.batch, lease, observer="after-migration")["duplicate"]
            assert count("history") == count("batch") == 1
            return

        if case == "proposal_without_pins":
            intent = json.loads(b.intent())
            intent.pop("pins")
            with pytest.raises(storage_api.AdapterError, match="unregistered_frozen_pins"):
                api.record_proposal(b.batch, body, b.run, outcome="ready",
                                    expected_generation=0,
                                    intent=storage_api.canonical(intent).decode())
            assert count("proposal") == 0
            return

        if case == "upgrade":
            assert api.apply(b, lease)["generation"] == 1
            storage_api.migrate(owner, runtime_role=role, prefix=prefix, protocol=5)
            api = storage_api.Adapter(runtime, prefix=prefix, protocol=5)
            assert api.apply(b, lease)["duplicate"]
            with pytest.raises(storage_api.AdapterError, match="proposal_required"):
                api.apply(
                    replace(
                        b,
                        batch="unadmitted",
                        expected_generation=1,
                        expected_checkpoint=1,
                        checkpoint=2,
                    ),
                    lease,
                )
            return
        if case == "missing":
            with pytest.raises(storage_api.AdapterError, match="proposal_required"):
                api.apply(b, lease)
            assert api.generation() == count("proposal") == 0
            return
        if case == "inline":
            result = api.apply(b, lease, proposal_body=body)
            key = sha256(storage_api.document(body)).hexdigest()
            assert result["generation"] == 1
            assert api.read_proposal(key)["state"] == "applied"
            assert count("proposal_event") == 3
            return
        if case == "stale_index":
            changed = replace(b, indexes=(storage_api.IndexChange(
                "invented-lookup", "one", {"ref": "one"}, expected_version=1
            ),))
            with pytest.raises(storage_api.AdapterError, match="stale_index_version"):
                api.apply(changed, lease, proposal_body=body)
            assert count("batch") == count("proposal") == count("lookup") == 0
            return
        if case in ("input_publication", "no_input_publication"):
            changed = replace(b, objects=(), publish_inputs=case == "input_publication")
            assert api.apply(changed, lease, proposal_body=body)["changed"] == (
                case == "input_publication"
            )
            assert count("evidence") == count("lookup") == 1
            assert count("outbox") == (2 if case == "input_publication" else 0)
            return
        if case in ("all_effects", "migration_rerun"):
            api.apply(b, lease, proposal_body=body)
            assert count("current") == count("history") == count("evidence") == count("lookup") == 1
            assert count("outbox") == 2 and count("checkpoint") == 1
            if case == "migration_rerun":
                storage_api.migrate(owner, runtime_role=role, prefix=prefix, protocol=5)
            assert api.apply(b, lease)["duplicate"]
            assert count("current") == count("history") == count("evidence") == count("lookup") == 1
            assert count("outbox") == 2 and count("checkpoint") == 1
            return
        if case == "unregistered":
            with owner.begin() as conn:
                conn.execute(update(api.tables["pin"]).values(active=0))
            with pytest.raises(
                storage_api.AdapterError, match="unregistered_frozen_pins"
            ):
                api.apply(b, lease, proposal_body=body)
            assert count("batch") == count("proposal") == 0
            return
        if case == "rollback":
            target = owner.dialect.identifier_preparer.format_table(
                api.tables["outbox"]
            )
            with owner.begin() as conn:
                if owner.dialect.name == "postgresql":
                    conn.exec_driver_sql(
                        "CREATE FUNCTION invented_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'invented_fault'; END $$"
                    )
                    conn.exec_driver_sql(
                        f"CREATE TRIGGER invented_fault BEFORE INSERT ON {target} FOR EACH ROW EXECUTE FUNCTION invented_fault()"
                    )
                else:
                    conn.exec_driver_sql(
                        f"CREATE TRIGGER invented_fault BEFORE INSERT ON {target} FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='invented_fault'"
                    )
            with pytest.raises(storage_api.AdapterError):
                api.apply(b, lease, proposal_body=body)
            assert api.generation() == 0
            assert all(
                count(name) == 0
                for name in (
                    "proposal",
                    "proposal_event",
                    "batch",
                    "current",
                    "history",
                    "evidence",
                    "lookup",
                    "checkpoint",
                    "outbox",
                )
            )
            return
        if case == "competing":
            barrier = Barrier(2)

            def save(i):
                barrier.wait(timeout=10)
                try:
                    return api.apply(
                        replace(b, batch=f"invented-{i}"),
                        lease,
                        proposal_body={"candidate": i},
                    )
                except storage_api.AdapterError as error:
                    return str(error)

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(save, (1, 2)))
            assert sum(isinstance(outcome, dict) for outcome in outcomes) == 1
            assert "stale_generation" in outcomes
            assert count("batch") == count("proposal") == count("current") == 1
            return
        if case == "grants":
            with pytest.raises(DBAPIError), runtime.begin() as conn:
                conn.execute(update(api.tables["proposal"]).values(state="applied"))
            return

        outcome = "rejected" if case == "rejected" else "ready"
        key = api.record_proposal(
            b.batch,
            body,
            b.run,
            outcome=outcome,
            expected_generation=0,
            intent=b.intent() if outcome == "ready" else None,
        )
        assert api.generation() == 0 and count("batch") == count("outbox") == 0
        assert (
            api.record_proposal(
                b.batch,
                body,
                b.run,
                outcome=outcome,
                expected_generation=0,
                intent=b.intent() if outcome == "ready" else None,
            )
            == key
        )
        assert count("proposal") == 1 and count("proposal_event") == 2
        if case == "mismatch":
            with pytest.raises(
                storage_api.AdapterError, match="assessed_effects_changed"
            ):
                api.apply(
                    replace(b, payload={"changed": True}), lease, proposal_key=key
                )
            assert count("batch") == 0 and api.read_proposal(key)["state"] == "ready"
            return
        if case == "collision":
            with pytest.raises(
                storage_api.AdapterError, match="proposal_content_collision"
            ):
                api.record_proposal(
                    b.batch,
                    body,
                    b.run,
                    outcome="ready",
                    expected_generation=0,
                    intent=replace(b, payload={"changed": True}).intent(),
                )
            return
        if case == "superseded":
            api.supersede_proposal(key, "new-observer")
            assert api.read_proposal(key)["state"] == "superseded"
        if case in ("rejected", "superseded"):
            with pytest.raises(storage_api.AdapterError, match="proposal_not_ready"):
                api.apply(b, lease, proposal_key=key)
            assert count("batch") == 0
            return
        if case == "generation":
            other = replace(
                b, batch="overtaking", scope="other-scope", objects=(), evidence=()
            )
            other_lease = api.claim(other.scope, "other-worker")
            api.apply(other, other_lease, proposal_body={"different": True})
            with pytest.raises(storage_api.AdapterError, match="stale_generation"):
                api.apply(replace(b, expected_generation=1), lease, proposal_key=key)
            return
        alternative = None
        if case == "alternatives":
            alternative = api.record_proposal(
                b.batch,
                {"alternative": True},
                b.run,
                outcome="ready",
                expected_generation=0,
                intent=b.intent(),
            )
        assert api.apply(b, lease, proposal_key=key)["generation"] == 1
        assert api.read_proposal(key)["state"] == "applied"
        if case == "stored_replay":
            saved = api.read_batch(b.batch)
            assert bytes(saved["intent"]).decode() == b.intent()
            assert api.replay(b.batch, lease, observer="new-observer")["duplicate"]
            assert api.read_batch(b.batch)["run_key"] == saved["run_key"]
            with pytest.raises(storage_api.AdapterError, match="unknown_committed_batch"):
                api.replay("unknown", lease, observer="new-observer")
            with pytest.raises(storage_api.AdapterError, match="Lease scope"):
                api.replay(b.batch, replace(lease, scope="another"), observer="new-observer")
            assert count("history") == count("batch") == 1 and count("outbox") == 2
            return
        if case == "revoked_duplicate":
            with owner.begin() as conn:
                api.admit_pin(conn, "policy", "replacement", exclusive=True)
            with pytest.raises(
                storage_api.AdapterError, match="unregistered_frozen_pins"
            ):
                api.apply(b, lease)
            return
        if alternative:
            assert api.read_proposal(alternative)["state"] == "superseded"
        if case in ("duplicate_observer", "observer_pins"):
            if case == "observer_pins":
                other = replace(
                    b,
                    batch="other-batch",
                    run="other-observer",
                    expected_generation=1,
                    expected_checkpoint=1,
                    checkpoint=2,
                    pins={"policy": "other-approved-pin"},
                    indexes=(),
                    objects=(),
                    evidence=(),
                )
                with owner.begin() as conn:
                    api.admit_pin(conn, "policy", "other-approved-pin")
                api.apply(other, lease, proposal_body={"other": True})
                with pytest.raises(
                    storage_api.AdapterError, match="frozen_pins_changed"
                ):
                    api.apply(replace(b, run=other.run), lease)
                return
            assert api.apply(replace(b, run="other-observer"), lease)["duplicate"]
            with owner.connect() as conn:
                original = conn.execute(
                    select(api.tables["batch"].c.run_key)
                ).scalar_one()
                observer = conn.execute(
                    select(api.tables["proposal_event"].c.observer_bytes).where(
                        api.tables["proposal_event"].c.event == "duplicate"
                    )
                ).scalar_one()
            assert original == sha256(b.run.encode()).hexdigest()
            assert bytes(observer) == b"other-observer"
            assert count("batch") == 1 and count("history") == 1
