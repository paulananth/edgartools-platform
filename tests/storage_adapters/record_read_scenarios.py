"""Private-process qualification with invented vocabulary loaded before imports."""

import copy
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from edgar_warehouse.database_connections import engine_from_env, storage_adapter
from edgar_warehouse.mdm.clean import binding, catalog, correction, matching
from edgar_warehouse.mdm.clean.evidence import assertion, decision
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
KIND = "invented-kind"
NAMESPACE = "invented_number"
PRIMARY = "invented.authority"
SECONDARY = "invented.consumer"
case = os.environ["READ_CASE"]
owner = engine_from_env("READ_OWNER_URL")
runtime = engine_from_env("READ_RUNTIME_URL")
api = storage_adapter()
migrate(owner, application_role=os.environ["READ_RUNTIME_ROLE"])
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
        register_dataset(
            conn,
            source,
            str(uuid4()),
            {
                "provider": "fixture",
                "family": "fixture",
                "schema_version": "1",
                "record_key": "key",
                "publication_key": "version",
                "effective_time": "effective_at",
                "semantics": "patch",
            },
        )
mysql = owner.dialect.name == "mysql"
if mysql:
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
    if not mysql:
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
    else:
        if case == "issuer_only":
            holder = record("one", SECONDARY)
            master, bind = identity(holder)
        if case == "newest":
            master, bind = identity(holder, "2026-02-01T00:00:00+00:00")
        save([holder], [master], [bind])
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
                at="2026-01-02T00:00:00Z",
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
                    at=AT,
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
                    at=AT,
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
                request, before = stage._prepare(
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
            proposed = propose(
                [record("new", identifiers={NAMESPACE: "777"})]
                if case == "newest"
                else [other],
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
    print("normal read phase passed")
finally:
    owner.dispose()
    runtime.dispose()
