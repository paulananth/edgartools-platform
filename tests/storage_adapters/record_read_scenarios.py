"""Private-process qualification with invented vocabulary loaded before imports."""

import copy
import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from edgar_warehouse.database_connections import engine_from_env, storage_adapter
from edgar_warehouse.mdm.clean import binding, catalog, correction, matching
from edgar_warehouse.mdm.clean.evidence import assertion, decision, deferred_record, instant
from edgar_warehouse.mdm.clean.identity import replay
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.record_reads import RecordReader
from edgar_warehouse.mdm.clean.store import (
    Conflict,
    Store,
    canonical,
    digest,
    migrate,
    register_policy,
)
from edgar_warehouse.rules.source_engine import (
    prepare_record_history,
    prepare_record_lookups,
    prepare_scope_lookups,
)
from tests.mdm.test_clean_activation import CIK_CONTRACT, COMPANY_BAR, proof
from tests.support.rules_authority import register_dataset

AT = "2026-01-01T00:00:00+00:00"
AS_OF = "2026-03-01T00:00:00+00:00"
KIND = os.environ.get("READ_KIND", "invented-kind")
NAMESPACE = "invented_number"
PRIMARY = "invented.authority"
SECONDARY = "invented.consumer"
case = os.environ["READ_CASE"]
owner = engine_from_env("READ_OWNER_URL")
runtime = engine_from_env("READ_RUNTIME_URL")
api = storage_adapter()
prepared_mode = os.environ.get("READ_PREPARED") == "1"
migrate(owner, application_role=os.environ["READ_RUNTIME_ROLE"], prepared=prepared_mode)
rule = {
    "rule_id": "invented-bind",
    "version": "1",
    "family": "binding",
    "applies_to_verdict": KIND,
    "emits": ["bind"],
    "on_no_match": "mint",
    "source": PRIMARY,
    "when": [
        {"primitive": "identifier_match@1", "args": {"namespace": NAMESPACE}},
        {"primitive": "identifier_cardinality@1", "args": {"namespace": NAMESPACE}},
    ],
}
join = {**rule, "rule_id": "invented-join", "on_no_match": "wait"}
del join["source"]
contract = {
    **CIK_CONTRACT,
    "authority": "invented-issuer",
    "sources": [PRIMARY],
    "normalizer": "normalize_identifier@crd-v1",
}
if case == "list_join":
    # A master may hold every value of the list (ticket 138: no reverse limit).
    contract["claim"] = {"forward": 1, "reverse": None}
rules = [rule, join]
policy = {
    "version": "invented-read-phase",
    "required_consumers": ["invented-export"],
    "kinds": {
        KIND: {
            "version": "1",
            "defaults": {
                "sources": [PRIMARY, SECONDARY],
                "allow_unknown_effective": True,
            },
            "rules": rules,
            "identifiers": {NAMESPACE: contract},
        }
    },
    "automatic_rules": [
        {
            "kind": KIND,
            "family": "binding",
            "rule_id": r["rule_id"],
            "rule_version": "1",
            "verdict": "bind",
            "activation": "deterministic",
        }
        for r in rules
    ],
}
if case in ("links", "hierarchy"):
    spec = {"from": [KIND], "to": [KIND]}
    if case == "hierarchy":
        spec.update(hierarchy=True, cycles="invalid", one_parent=True)
    policy["relationships"] = {"version": "invented-links-v1", "types": {"invented_link": spec}}
if case.startswith(("name_", "cascade_")):
    from tests.mdm.test_configured_pair_comparison import PROGRAM

    comparison_fixture = {}
    exec(PROGRAM, comparison_fixture)
    left = comparison_fixture["left"]
    right = comparison_fixture["right"]
    names = comparison_fixture["names"]
    eligibility = comparison_fixture["eligibility"]
    primitive = (
        "cascade_pass@1" if case.startswith("cascade_") else "name_census_match@1"
    )
    args = (
        {
            **names,
            "pass": "P1",
            "compare": ["street", "city", "postcode"],
            "refused_flags": [],
            "over_shared": 10,
        }
        if primitive == "cascade_pass@1"
        else names
    )
    tests = [
        {"primitive": primitive, "args": args},
        {"primitive": "gleif_entity_eligible@1", "args": eligibility},
        {"primitive": "holds_no_other_lei@1", "args": {}},
    ]
    if primitive == "name_census_match@1":
        tests.append(
            {
                "primitive": "postal_agrees@1",
                "args": {
                    "sec_code": "matching.invented_postal",
                    "sec_country": "matching.invented_country",
                    "gleif_code": "matching.invented_postal",
                    "gleif_country": "matching.invented_country",
                },
            }
        )
    named = {
        "rule_id": "invented-name",
        "version": "1",
        "family": "name_binding",
        "pair_comparison": "invented-comparison",
        "applies_to_verdict": KIND,
        "emits": ["bind"],
        "on_no_match": "wait",
        "source": SECONDARY,
        "holder_source": PRIMARY,
        "when": tests,
    }
    policy["kinds"][KIND]["rules"].append(named)
    policy["kinds"][KIND]["bars"] = {"name_binding": COMPANY_BAR}
    policy["kinds"][KIND]["identifiers"]["invented_reference"] = {
        **contract,
        "sources": [SECONDARY],
        "normalizer": "normalize_text@legal-form-kept-v1",
    }
    policy["automatic_rules"].append(
        {
            "kind": KIND,
            "family": "name_binding",
            "rule_id": named["rule_id"],
            "rule_version": "1",
            "verdict": "bind",
            "activation": "measured",
            "proof": proof(n=300, correct=300),
        }
    )
inactive = {**policy, "version": "invented-seed", "automatic_rules": []}
with owner.begin() as conn:
    seed_pin = register_policy(conn, inactive)
    pin = register_policy(conn, policy)
    for source in (PRIMARY, SECONDARY):
        contract_body = {
            "provider": "fixture", "family": "fixture", "schema_version": "1",
            "record_key": "key", "publication_key": "version", "effective_time": "effective_at",
            "semantics": "patch",
        }
        if case == "details":
            from tests.support.reading import reading
            configured = reading({"invented_name": "invented_name"})
            configured["read"]["tables"]["mapped"]["columns"]["details"] = {
                "object": {"fields": {"invented_rows": {"value": {"path": "rows"}}}}}
            contract_body["adapter"] = {"version": "invented-details-v1", "kind": KIND,
                "record_key": ["key"], "reading": configured, "detail_keys": {"invented_rows": "row_id"}}
        register_dataset(
            conn,
            source,
            str(uuid4()),
            contract_body,
        )
mysql = owner.dialect.name == "mysql"
if mysql and not prepared_mode:
    owner_store = api.Adapter(owner, prefix="mdm_store", protocol=4)
    lease = owner_store.claim("invented-read-phase", "fixture-owner")
readings = {}
decisions = {}
identities = {}
pointers = {}
publications = {}
sequence = 0


def record(key, source=PRIMARY, revision=1, **changes):
    defaults = {
        "source_code": source,
        "record_key": key,
        "publication_key": str(revision),
        "revision": revision,
        "effective_at": AT,
        "kind": KIND,
        "fields": {"invented_name": "INVENTED LABEL"},
        "identifiers": {NAMESPACE: "171"},
    }
    return assertion(**{**defaults, **changes})


def identity(record, at=AT):
    value = {"entity_id": str(uuid4()), "kind": KIND, "published_at": at}
    bind = decision(
        "bind",
        actor="fixture",
        reason="invented reviewed identity",
        at=AT,
        subject=record["subject"],
        entity_id=value["entity_id"],
        evidence=[record["assertion_id"]],
    )
    return value, bind


def save(incoming=(), allocated=(), journal=()):
    global sequence, pointers, publications
    sequence += 1
    if not mysql or prepared_mode:
        MergeStage(Store(runtime)).apply(
            batch_id="seed-" + str(sequence),
            run_id=str(uuid4()),
            policy_digest=seed_pin,
            consumer="invented-seed",
            expected_checkpoint=sequence - 1,
            checkpoint=sequence,
            as_of=AS_OF,
            assertions=list(incoming),
            identities=list(allocated),
            decisions=list(journal),
        )
        return
    readings.update((r["assertion_id"], r) for r in incoming)
    identities.update((i["entity_id"], i) for i in allocated)
    decisions.update((d["decision_id"], d) for d in journal)
    state = replay(list(identities.values()), list(decisions.values()), AS_OF)
    evidence, retained = prepare_record_history(
        {
            "readings": list(incoming),
            "identities": list(allocated),
            "decisions": list(journal),
        }
    )
    pointers, indices = prepare_record_lookups(
        {
            "readings": list(readings.values()),
            "previous": pointers,
            "subjects": sorted({r["subject"] for r in readings.values()}),
            "bindings": state.bindings,
            "quarantined": state.quarantined,
            "policy": policy,
            "normalizers": {},
            "batch_id": "seed-" + str(sequence),
            "occurrences": {},
            "candidate_routes": matching.candidate_routes(),
        }
    )
    publications, floors = prepare_scope_lookups(
        {
            "previous": [],
            "objects": [],
            "identities": list(allocated),
            "previous_publications": publications,
        }
    )
    index_changes = []
    for e in [*retained, *indices, *floors]:
        old = owner_store.read([(e["type"], e["id"])], lookup=True).get(
            (e["type"], e["id"])
        )
        if old and not e.get("removed") and old["body"].decode() == e["body_json"]:
            continue
        index_changes.append(
            api.IndexChange(
                e["type"],
                e["id"],
                e.get("body_json"),
                expected_version=old["version"] if old else 0,
                removed=e.get("removed", False),
            )
        )
    masters = tuple(
        api.Effect(
            "entity",
            i["entity_id"],
            {
                "entity_id": i["entity_id"],
                "kind": i["kind"],
                "canonical_id": i["entity_id"],
                "status": "active",
            },
        )
        for i in allocated
    )
    request = api.PreparedBatch(
        batch="seed-" + str(sequence),
        run="fixture",
        scope="invented-read-phase",
        pins={"policy": seed_pin},
        assessment={"fixture": "read-phase-only"},
        expected_generation=sequence - 1,
        expected_checkpoint=sequence - 1,
        checkpoint=sequence,
        objects=masters,
        consumers=("invented-export",),
        payload={},
        evidence=tuple(
            api.Effect(e["type"], e["id"], e["body_json"]) for e in evidence
        ),
        indexes=tuple(index_changes),
    )
    owner_store.apply(request, lease)


def propose(items=(), journal=(), at=AS_OF):
    return MergeStage(Store(runtime, read_only=True)).propose(
        policy_digest=pin, assertions=list(items), decisions=list(journal), as_of=at
    )


try:
    holder = record("one")
    if case == "list_join":
        # A holder that carries a list (ticket 138): the joining record's one
        # value is the list's second, so each value is indexed and read.
        holder = record("one", identifiers={NAMESPACE: ["170", "171"]})
    master, bind = identity(holder)
    other = record("two", SECONDARY)
    if case.startswith(("name_", "cascade_")):
        for raw in (left, right):
            raw["provenance"]["matching"].update(
                invented_postal="11111", invented_country="ZZ"
            )
        holder = record(
            "origin-1",
            provenance=left["provenance"],
            fields={k: v["value"] for k, v in left["fields"].items()},
        )
        other = record(
            "target-1",
            SECONDARY,
            identifiers=right["identifiers"],
            fields={k: v["value"] for k, v in right["fields"].items()},
            effective_at=right["effective_at"],
            provenance=right["provenance"],
        )
        master, bind = identity(holder)
        if case.endswith("candidate_first"):
            save([other])
            proposed = propose([holder], [bind])
        else:
            save([holder], [master], [bind])
            proposed = propose([other])
        assert any(
            d["subject"] == other["subject"] and d["entity_id"] == master["entity_id"]
            for d in proposed["decisions"]
        )
        if case == "name_held_value":
            save([other], journal=proposed["decisions"])
            changed = copy.deepcopy(left["provenance"])
            entry = changed["matching"]["invented_census"]
            entry["invented_matches"][0][0] = "other-target"
            entry["invented_assignment"]["invented_target"] = "other-target"
            updated = record(
                "origin-1",
                revision=2,
                fields={k: v["value"] for k, v in left["fields"].items()},
                provenance=changed,
            )
            save([updated])
            other_target = record(
                "other-target",
                SECONDARY,
                identifiers={"invented_reference": "other-target"},
                fields={k: v["value"] for k, v in right["fields"].items()},
                effective_at=right["effective_at"],
                provenance=right["provenance"],
            )
            assert propose([other_target])["decisions"] == []
        if prepared_mode:
            target = other_target if case == "name_held_value" else holder if case.endswith("candidate_first") else other
            command = {"batch_id": "invented-normal-name", "run_id": str(uuid4()),
                       "policy_digest": pin, "consumer": "invented-proof", "expected_checkpoint": 0,
                       "checkpoint": 1, "as_of": AS_OF, "assertions": [target]}
            if case.endswith("candidate_first"):
                command.update(identities=[master], decisions=[bind])
            stage = MergeStage(Store(runtime))
            result = stage.apply(**command)
            assert result["generation"] == sequence + 1
            assert stage.apply(**{**command, "run_id": str(uuid4())})["duplicate"]
            normal = api.Adapter(runtime, prefix="mdm_store", protocol=6)
            reader = RecordReader(normal, routes=matching.candidate_routes())
            subject = other_target["subject"] if case == "name_held_value" else other["subject"]
            saved = reader.current([subject])[subject]
            assert saved["entity_id"] == (None if case == "name_held_value" else master["entity_id"])
    else:
        if case == "issuer_only":
            holder = record("one", SECONDARY)
            master, bind = identity(holder)
        if case == "newest":
            master, bind = identity(holder, "2026-02-01T00:00:00+00:00")
        if case == "details":
            holder = record("one", details={"invented_rows": [
                {"key": "D1", "amount": 10**80 + 1}, {"key": "D2", "amount": 2}]})
            master, bind = identity(holder)
            other = record("two", SECONDARY, details={"invented_rows": [
                {"key": "D2", "amount": 9}, {"key": "D3", "amount": 3}]})
        save([holder], [master], [bind])
        if case in ("links", "hierarchy"):
            third = record("third", identifiers={NAMESPACE: "333"})
            third_id, third_bind = identity(third, "2026-01-02T00:00:00Z")
            save([third], [third_id], [third_bind])
            second_links = ([{"type": "invented_link", "target_subject": third["subject"],
                              "valid_from": AT, "valid_to": None, "scope": "invented"}]
                            if case == "hierarchy" else [])
            second = record("second", identifiers={NAMESPACE: "222"}, relationships=second_links)
            second_id, second_bind = identity(second, "2026-01-03T00:00:00Z")
            save([second], [second_id], [second_bind])
            linked = record("one", revision=2, relationships=[{"type": "invented_link",
                "target_subject": second["subject"], "valid_from": AT, "valid_to": None, "scope": "invented"}])
        if case == "corrected":
            save([record("one", revision=2, identifiers={NAMESPACE: "999"})])
        if case in ("quarantine", "lifted"):
            other_bind = decision(
                "bind",
                actor="fixture",
                reason="invented reviewed binding",
                at=AT,
                subject=other["subject"],
                entity_id=master["entity_id"],
                evidence=[other["assertion_id"]],
            )
            save([other], journal=[other_bind])
            quarantine = decision(
                "quarantine",
                actor="fixture",
                reason="invented hold",
                at="2026-01-03T00:00:00Z",
                subject=other["subject"],
                entity_id=master["entity_id"],
                policy=seed_pin,
            )
            revoke = decision(
                "revoke",
                actor="fixture",
                reason="invented release",
                at="2026-01-02T00:00:00Z",
                target=other_bind["decision_id"],
                subject=other["subject"],
                entity_id=master["entity_id"],
            )
            save(journal=[revoke, quarantine])
        journal = []
        if case == "released":
            journal = [
                decision(
                    "revoke",
                    actor="fixture",
                    reason="invented correction",
                    at="2026-01-02T00:00:00Z",
                    target=bind["decision_id"],
                    subject=holder["subject"],
                    entity_id=master["entity_id"],
                )
            ]
        if case == "lifted":
            journal = [
                decision(
                    "revoke",
                    actor="fixture",
                    reason="invented lift",
                    at="2026-01-04T00:00:00Z",
                    target=quarantine["decision_id"],
                    subject=other["subject"],
                    policy=pin,
                )
            ]
        if case == "retired":
            save(
                journal=[
                    decision(
                        "retire_source",
                        actor="fixture",
                        reason="invented retirement",
                        at=AT,
                        source_code=PRIMARY,
                        evidence=[holder["assertion_id"]],
                    )
                ]
            )
        if case.startswith("prepare_"):
            incoming = (
                record("one", revision=2, fields={"invented_name": "INVENTED CORRECTION"})
                if case == "prepare_no_identity"
                else record("new", identifiers={NAMESPACE: "777"})
                if case == "prepare_new_identity"
                else other
            )
            automatic = propose([incoming])
            command = {
                "batch_id": "invented-preparation", "policy_digest": pin,
                "consumer": "invented-seed", "expected_checkpoint": 1,
                "checkpoint": 2, "as_of": AS_OF, "assertions": [incoming],
                "decisions": [], "identities": [],
            }
            stage = MergeStage(Store(runtime, read_only=True))
            with runtime.connect() as connection:
                transport = (
                    RecordReader(api.Adapter(runtime, prefix="mdm_store", protocol=4),
                                 connection=connection, routes=matching.candidate_routes())
                    if mysql else connection
                )
                request, before, _ = stage._prepare(
                    transport, policy=policy, command=command, assertions=[incoming],
                    decisions=automatic["decisions"], identities=automatic["identities"],
                    deferred=[], automatic=automatic, input_hash=digest(command),
                )
            assert request["expected_generation"] == 1
            expected_id = (
                automatic["identities"][0]["entity_id"]
                if case == "prepare_new_identity" else master["entity_id"]
            )
            projected = [p for p in request["projections"] if p["object_type"] == "entity"]
            assert len(projected) == 1 and projected[0]["object_id"] == expected_id
            expected_value = (
                "INVENTED CORRECTION" if case == "prepare_no_identity" else "INVENTED LABEL"
            )
            assert projected[0]["body"]["fields"]["invented_name"]["value"] == expected_value
            assert bool(request["identities"]) == (case == "prepare_new_identity")
            assert bool(request["decisions"]) == (case != "prepare_no_identity")
            assert bool(before) == (case != "prepare_new_identity")
            with runtime.connect() as connection:
                generation = (
                    owner_store.generation(connection=connection) if mysql else
                    connection.scalar(text("SELECT max(generation) FROM mdm.batch"))
                )
            assert generation == 1  # Preparation commits no business effects.
        elif case == "write_gate":
            reader_store = Store(runtime, read_only=True)
            stage = MergeStage(reader_store)
            with pytest.raises(Conflict, match="read-only"):
                stage.apply()
            with pytest.raises(Conflict, match="read-only"):
                stage.assess()
            with pytest.raises(Conflict, match="read-only"):
                stage.apply_assessment("invented", run_id=str(uuid4()))
            with runtime.connect() as conn, pytest.raises(Conflict, match="read-only"):
                reader_store.commit(conn, {}, str(uuid4()))
            with pytest.raises(Conflict, match="read-only"):
                reader_store.deliver_one("invented", "invented", object())
            if mysql:
                with pytest.raises(ValueError, match="requires PostgreSQL"):
                    Store(runtime)
                with pytest.raises(Conflict, match="not yet qualified"):
                    reader_store.run_status(str(uuid4()))
        elif case in ("scope", "retired"):
            frame = MergeStage(Store(runtime, read_only=True)).read_scope([holder], [])
            assert (
                frame.subjects == {holder["subject"]}
                and holder["assertion_id"] in frame.readings
            )
            assert bind["decision_id"] in frame.decisions and len(frame.identities) == 1
            if case == "retired":
                assert any(
                    d["operation"] == "retire_source" for d in frame.decisions.values()
                )
        else:
            incoming = [record("new", identifiers={NAMESPACE: "777"})] if case == "newest" else [other]
            proposed = propose(
                incoming,
                journal,
                at="2026-01-02T00:00:00+00:00" if case == "newest" else AS_OF,
            )
            joins = [
                d
                for d in proposed["decisions"]
                if d["operation"] == "bind" and d["subject"] == other["subject"]
            ]
            if case in ("issuer_only", "corrected", "quarantine"):
                assert joins == []
            elif case == "released":
                assert all(d["entity_id"] != master["entity_id"] for d in joins)
            elif case == "newest":
                assert (
                    proposed["identities"]
                    and proposed["identities"][0]["published_at"] > "2026-02-01"
                )
            else:
                assert len(joins) == 1 and joins[0]["entity_id"] == master["entity_id"]
            if prepared_mode:
                stage = MergeStage(Store(runtime))
                command = {
                    "batch_id": "invented-normal-merge", "run_id": str(uuid4()),
                    "policy_digest": pin, "consumer": "invented-proof",
                    "expected_checkpoint": 0, "checkpoint": 1,
                    "assertions": incoming, "decisions": journal,
                    "as_of": "2026-01-02T00:00:00+00:00" if case == "newest" else AS_OF,
                }
                if case == "deferred":
                    held = deferred_record(source_code=SECONDARY, publication_key="1",
                        record_locator="held", schema_version="1", reason="invented_missing_key",
                        raw_record={"invented_amount": 7}, provenance={"object": "invented/held.json"})
                    command["deferred"] = [held]
                if case in ("links", "hierarchy"):
                    incoming = [linked]
                    command["assertions"] = incoming
                if case == "no_identity_stale":
                    incoming = [holder]
                    command["assertions"] = incoming
                normal = api.Adapter(runtime, prefix="mdm_store", protocol=6)

                def counts():
                    with runtime.connect() as conn:
                        return {name: conn.scalar(select(func.count()).select_from(normal.tables[name]))
                                for name in ("batch", "current", "history", "evidence", "lookup", "checkpoint", "outbox")}

                if case == "preview":
                    before = counts()
                    preview = stage.apply(**{**command, "preview": True})
                    assert preview["preview"] and not preview["duplicate"]
                    assert counts() == before and normal.generation() == sequence
                if case in ("assessment", "stale_assessment"):
                    before = counts()
                    candidate = stage.assess(**command, automatic=stage.propose(**command))
                    assert counts() == before and normal.generation() == sequence
                    kept = normal.read_proposal(candidate["assessment_id"])
                    assert kept["state"] == "ready" and b'"effects":' not in bytes(kept["body"])
                    if case == "stale_assessment":
                        from edgar_warehouse.mdm.clean.assessment import StaleAssessment
                        save([record("one", revision=2, fields={"invented_name": "INVENTED CORRECTION"})])
                        with pytest.raises(StaleAssessment):
                            stage.apply_assessment(candidate["assessment_id"], run_id=str(uuid4()))
                        assert normal.read_proposal(candidate["assessment_id"])["state"] == "superseded"
                        result = stage.apply(**command)
                    else:
                        producer = str(uuid4())
                        result = stage.apply_assessment(candidate["assessment_id"], run_id=producer)
                        assert normal.read_batch(command["batch_id"])["run_key"] == api.key(producer)
                        with runtime.connect() as conn:
                            payloads = conn.execute(select(normal.tables["outbox"].c.payload)
                                .where(normal.tables["outbox"].c.batch_key == api.key(command["batch_id"]))).scalars().all()
                            assert len(payloads) == 1 and all(json.loads(bytes(raw))["run_id"] == producer for raw in payloads)
                elif case == "no_identity_stale":
                    original = stage.propose
                    observations = []
                    newer = record("one", revision=2, fields={"invented_name": "INVENTED CORRECTION"})

                    def proposed_then_overtaken(**args):
                        proposal = original(**args)
                        observations.append(proposal["observed_generation"])
                        assert not proposal["decisions"] and not proposal["identities"]
                        if sequence == 1:
                            save([newer])
                        return proposal

                    stage.propose = proposed_then_overtaken
                    result = stage.apply(**command)
                    assert sequence == 2 and observations[:2] == [1, 2]
                elif case in ("competing", "mint_competing"):
                    barrier = Barrier(2)

                    def race(ordinal):
                        worker = MergeStage(Store(runtime))
                        claim = {**command, "batch_id": f"invented-race-{ordinal}",
                                 "run_id": str(uuid4()), "assertions": [record(f"race-{ordinal}", SECONDARY)]}
                        if case == "mint_competing":
                            claim.update(consumer=f"invented-race-{ordinal}", assertions=[
                                record(f"race-{ordinal}", PRIMARY, identifiers={NAMESPACE: "777"})])
                        original = worker.store.commit
                        calls = 0

                        def admitted(connection, prepared, root):
                            nonlocal calls
                            calls += 1
                            if calls == 1:
                                barrier.wait(timeout=30)
                            return original(connection, prepared, root)

                        worker.store.commit = admitted
                        try:
                            return claim, worker.apply(**claim)
                        except Conflict:
                            return claim, None

                    with ThreadPoolExecutor(max_workers=2) as pool:
                        outcomes = list(pool.map(race, (1, 2)))
                    winners = [(claim, result) for claim, result in outcomes if result is not None]
                    assert len(winners) == (2 if case == "mint_competing" else 1)
                    command, result = max(winners, key=lambda item: item[1]["generation"])
                    incoming = command["assertions"]
                    if case == "mint_competing":
                        reader = RecordReader(normal, routes=matching.candidate_routes())
                        subjects = [claim["assertions"][0]["subject"] for claim, _ in winners]
                        pointers = reader.current(subjects)
                        assert len(pointers) == 2
                        canonical = {pointer["entity_id"] for pointer in pointers.values()}
                        assert len(canonical) == 1 and master["entity_id"] not in canonical
                        with runtime.connect() as conn:
                            table = normal.tables["evidence"]
                            assert conn.scalar(select(func.count()).select_from(table).where(
                                table.c.type_key == api.key("identity"))) == 2
                    for claim, saved_result in outcomes:
                        if saved_result is None:
                            assert normal.read_batch(claim["batch_id"]) is None
                            assert not normal.read([("source-reading", claim["assertions"][0]["assertion_id"])], immutable=True)
                elif case == "rollback":
                    before = counts()
                    target = owner.dialect.identifier_preparer.format_table(normal.tables["outbox"])
                    with owner.begin() as conn:
                        if mysql:
                            conn.exec_driver_sql(f"CREATE TRIGGER invented_fault BEFORE INSERT ON {target} FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='invented_fault'")
                        else:
                            conn.exec_driver_sql("CREATE FUNCTION invented_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'invented_fault'; END $$")
                            conn.exec_driver_sql(f"CREATE TRIGGER invented_fault BEFORE INSERT ON {target} FOR EACH ROW EXECUTE FUNCTION invented_fault()")
                    try:
                        with pytest.raises(Conflict):
                            stage.apply(**command)
                        assert counts() == before and normal.generation() == sequence
                    finally:
                        with owner.begin() as conn:
                            conn.exec_driver_sql("DROP TRIGGER invented_fault" if mysql else f"DROP TRIGGER invented_fault ON {target}")
                    result = stage.apply(**command)
                else:
                    result = stage.apply(**command)
                assert result["generation"] == sequence + (2 if case == "mint_competing" else 1) and not result["duplicate"]
                assert stage.apply(**{**command, "run_id": str(uuid4())})["duplicate"]
                if case == "collision":
                    before = counts()
                    changed = record("two", SECONDARY, revision=2)
                    with pytest.raises(Conflict, match="Batch key reused"):
                        stage.apply(**{**command, "assertions": [changed]})
                    assert counts() == before
                if case == "deferred":
                    stored = normal.read([("deferred-record", held["deferred_id"])], immutable=True)
                    assert json.loads(bytes(stored["deferred-record", held["deferred_id"]]["body"])) == held
                    review = normal.read([("review", held["deferred_id"])])
                    body = json.loads(bytes(review["review", held["deferred_id"]]["body"]))
                    assert body["open"] and body["blocking"]
                    changed = deferred_record(source_code=SECONDARY, publication_key="1",
                        record_locator="held", schema_version="1", reason="invented_missing_key",
                        raw_record={"invented_amount": 8}, provenance={"object": "invented/held.json"})
                    before = counts()
                    with pytest.raises(Conflict, match="publication identity"):
                        stage.apply(**{**command, "batch_id": "invented-deferred-change",
                                       "expected_checkpoint": 1, "checkpoint": 2, "deferred": [changed]})
                    assert counts() == before
                if case in ("unchanged", "occurrence"):
                    before = counts()
                    again = {**command, "batch_id": "invented-followup", "expected_checkpoint": 1, "checkpoint": 2}
                    if case == "occurrence":
                        again["occurrences"] = [{"assertion_id": incoming[0]["assertion_id"],
                                                 "object": "invented/capture.json", "sha256": "a" * 64, "locator": "1"}]
                    followup = stage.apply(**again)
                    assert followup["changed"] == (case == "occurrence")
                    after = counts()
                    assert before["history"] == after["history"] and before["current"] == after["current"]
                    assert after["outbox"] - before["outbox"] == (1 if case == "occurrence" else 0)
                    assert after["evidence"] - before["evidence"] == (1 if case == "occurrence" else 0)
                    assert stage.apply(**again)["duplicate"]
                    result = followup
                reader = RecordReader(normal, routes=matching.candidate_routes())
                saved = reader.current([incoming[0]["subject"]])[incoming[0]["subject"]]
                assert saved["assertion_id"] == (newer["assertion_id"] if case == "no_identity_stale" else incoming[0]["assertion_id"])
                if case in ("join", "lifted"):
                    assert saved["entity_id"] == master["entity_id"]
                elif case in ("issuer_only", "corrected", "quarantine"):
                    assert saved["entity_id"] is None
                elif case in ("released", "newest"):
                    assert saved["entity_id"] != master["entity_id"]
                if case == "details":
                    root = master["entity_id"]
                    initial = reader.masters([root])[root]["details"]["invented_rows"]
                    assert initial == [
                        {"key": "D1", "amount": 10**80 + 1, "sources": [PRIMARY]},
                        {"key": "D2", "amount": 2, "sources": [PRIMARY, SECONDARY]},
                        {"key": "D3", "amount": 3, "sources": [SECONDARY]}]
                    revised = [{"key": "D1", "amount": 10**80 + 2}]
                    updates = [
                        record("one", revision=2, details={"invented_rows": revised}),
                        record("two", SECONDARY, revision=2, details={"invented_rows": []}),
                        record("one", revision=3, fields={"invented_name": "INVENTED RENAMED"},
                               details={"invented_rows": revised}),
                    ]
                    for position, updated in enumerate(updates, 1):
                        result = stage.apply(batch_id=f"invented-details-{position}", run_id=str(uuid4()),
                            policy_digest=pin, consumer="invented-details-proof", expected_checkpoint=position-1,
                            checkpoint=position, as_of=AS_OF, assertions=[updated])
                    with runtime.connect() as conn:
                        table = normal.tables["history"]
                        history = conn.execute(select(table.c.generation, table.c.body).where(
                            table.c.type_key == api.key("entity"), table.c.id_key == api.key(root)
                        ).order_by(table.c.generation)).all()
                    assert len(history) == 5
                    lists = {generation: json.loads(bytes(raw)).get("details", {}).get("invented_rows", [])
                             for generation, raw in history}
                    assert lists[2] == initial
                    assert lists[3] == [
                        {"key": "D1", "amount": 10**80 + 2, "sources": [PRIMARY]},
                        {"key": "D2", "amount": 9, "sources": [SECONDARY]},
                        {"key": "D3", "amount": 3, "sources": [SECONDARY]}]
                    assert lists[4] == lists[5] == [{"key": "D1", "amount": 10**80 + 2, "sources": [PRIMARY]}]
                    assert len({row["key"] for row in lists[2]}) == len(lists[2])
                if case in ("links", "hierarchy"):
                    root = master["entity_id"]
                    links = [p["body"] for p in reader.projections(starts=[root]) if p["object_type"] == "relationship"]
                    assert len(links) == 1 and links[0]["target_id"] == second_id["entity_id"]
                    far_keys = [("entity", second_id["entity_id"]), ("entity", third_id["entity_id"])]
                    far_before = normal.read(far_keys)
                    if case == "links":
                        moved = record("one", revision=3, effective_at="2026-02-01T00:00:00Z", relationships=[
                            {"type": "invented_link", "target_subject": third["subject"],
                             "valid_from": "2026-02-01T00:00:00Z", "valid_to": None, "scope": "invented"}])
                        result = stage.apply(**{**command, "batch_id": "invented-link-move", "assertions": [moved],
                                                "expected_checkpoint": 1, "checkpoint": 2})
                        assert normal.read(far_keys) == far_before
                        after = [p["body"] for p in reader.projections(starts=[root]) if p["object_type"] == "relationship"]
                        active = [body for body in after if not body.get("retired") and any(
                            (not period.get("valid_from") or instant(period["valid_from"]) <= instant(AS_OF))
                            and (not period.get("valid_to") or instant(AS_OF) < instant(period["valid_to"]))
                            for period in body["periods"])]
                        assert len(active) == 1 and active[0]["target_id"] == third_id["entity_id"]
                        with runtime.connect() as conn:
                            table = normal.tables["history"]
                            retained = conn.execute(select(table.c.body).where(
                                table.c.type_key == api.key("relationship"),
                                table.c.id_key == api.key(links[0]["relationship_id"])
                            ).order_by(table.c.generation)).scalars().all()
                        assert len(retained) == 2 and json.loads(bytes(retained[0])) == links[0]
                    else:
                        cycle = record("third", revision=2, identifiers={NAMESPACE: "333"}, relationships=[
                            {"type": "invented_link", "target_subject": holder["subject"],
                             "valid_from": AT, "valid_to": None, "scope": "invented"}])
                        result = stage.apply(**{**command, "batch_id": "invented-cycle", "assertions": [cycle],
                                                "expected_checkpoint": 1, "checkpoint": 2})
                        for identity_id in (root, second_id["entity_id"], third_id["entity_id"]):
                            reviews = [p["body"] for p in reader.projections(reviews=[identity_id])
                                       if p["object_type"] == "review" and p["body"].get("reason") == "hierarchy_cycle"]
                            assert reviews and all(identity_id in r["affected_entities"] for r in reviews)
                assert normal.generation() == result["generation"]
    print("normal read phase passed")
finally:
    owner.dispose()
    runtime.dispose()
