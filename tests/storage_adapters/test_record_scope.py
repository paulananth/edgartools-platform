"""Exact indexed scope and hostile references on the shared read boundary."""

import copy
import json
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import text

from edgar_warehouse.mdm.clean import scope
from edgar_warehouse.mdm.clean.evidence import KINDS, assertion, decision, subject_key
from edgar_warehouse.mdm.clean.record_reads import RecordReader
from edgar_warehouse.mdm.clean.store import Conflict
from edgar_warehouse.rules.source_engine import (
    prepare_record_history,
    prepare_record_lookups,
    prepare_scope_lookups,
)
from tests.storage_adapters.test_lookup_entries import lookup_store  # noqa: F401
from tests.storage_adapters.test_prepared_effects import assert_index_lookup

AT = "2026-01-01T00:00:00+00:00"
CASES = [
    "plain",
    "hierarchy",
    "current_links",
    "reviews",
    "wrong_anchor",
    "wrong_member",
    "dangling_input",
    "mismatched_input",
    "wrong_projection",
    "missing_projection",
    "members",
    "plans",
    "wrong_membership",
    "wrong_candidate",
    "bad_floor",
    "pointer_source_code",
    "pointer_kind",
    "pointer_mapping_version",
    "pointer_revision",
    "pointer_identifiers",
    "pointer_cross_references",
]


def assert_group_probes(engine, statement, table, count):
    if engine.dialect.name != "postgresql":
        return assert_index_lookup(engine, statement, table)
    sql = str(
        statement.compile(
            dialect=engine.dialect, compile_kwargs={"literal_binds": True}
        )
    )
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL enable_seqscan=off"))
        plan = conn.execute(
            text("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) " + sql)
        ).scalar()[0]["Plan"]

    def nodes(node):
        yield node
        for child in node.get("Plans", []):
            yield from nodes(child)

    accesses = [node for node in nodes(plan) if node.get("Relation Name") == table]
    # PostgreSQL may choose a bitmap heap probe backed by one primary-key
    # bitmap index seek per requested prefix. Prove the seek and actual work,
    # rather than accepting a node merely because it is named Index Scan.
    assert accesses and all(
        node["Node Type"] in {"Index Scan", "Index Only Scan", "Bitmap Heap Scan"}
        for node in accesses
    )
    probes = [
        node
        for node in nodes(plan)
        if node.get("Index Name", "").startswith(table)
        and "type_key" in node.get("Index Cond", "")
    ]
    assert probes and sum(node["Actual Loops"] for node in probes) == count
    assert all(node["Actual Rows"] <= 1 for node in probes)


@pytest.mark.parametrize("case", CASES)
def test_shared_indexed_scope(case, lookup_store, storage_api):
    owner, runtime, lease, request = lookup_store
    kind = sorted(KINDS)[0]
    source = "invented.scope"
    subjects = [subject_key(source, str(i)) for i in range(3)]
    ids = [str(uuid4()) for _ in subjects]
    readings = [
        assertion(
            source_code=source,
            record_key=str(i),
            publication_key="one",
            revision=1,
            effective_at=AT,
            kind=kind,
            fields={"invented_label": str(i)},
            relationships=(
                [
                    {
                        "type": "invented-plain" if i == 0 else "invented-parent",
                        "target_subject": subjects[i + 1],
                        "on": AT,
                    }
                ]
                if i < 2
                else []
            ),
        )
        for i in range(3)
    ]
    identities = [{"entity_id": key, "kind": kind, "published_at": AT} for key in ids]
    binds = [
        decision(
            "bind",
            actor="fixture",
            reason="invented binding",
            at=AT,
            subject=subject,
            entity_id=key,
            evidence=[reading["assertion_id"]],
        )
        for subject, key, reading in zip(subjects, ids, readings)
    ]
    links = [
        {
            "type": "relationship",
            "id": "invented-link-" + str(i),
            "body": {
                "relationship_id": "invented-link-" + str(i),
                "source_id": ids[i],
                "target_id": ids[i + 1],
                "type": "invented-plain" if i == 0 else "invented-parent",
                "retired": False,
                "evidence": [{"assertion_id": readings[i]["assertion_id"]}],
            },
        }
        for i in range(2)
    ]
    review = {
        "type": "review",
        "id": "invented-review",
        "body": {
            "review_id": "invented-review",
            "reason": "invented-finding",
            "entity_id": ids[0],
            "affected_subjects": [subjects[0]],
        },
    }
    objects = [
        *links,
        review,
        *[
            {
                "type": "entity",
                "id": key,
                "body": {
                    "entity_id": key,
                    "canonical_id": key,
                    "status": "active",
                    "kind": kind,
                },
            }
            for key in ids
        ],
    ]
    saved = copy.deepcopy(readings)
    if case == "mismatched_input":
        saved[0]["fields"] = {}
    evidence, history = prepare_record_history(
        {"readings": saved, "decisions": binds, "identities": identities}
    )
    routes = {"invented-route": ["fields", "invented_label", "value"]}
    _, current = prepare_record_lookups(
        {
            "readings": readings,
            "previous": {},
            "subjects": subjects,
            "bindings": dict(zip(subjects, ids)),
            "quarantined": {},
            "policy": {},
            "normalizers": {},
            "batch_id": "invented-scope",
            "occurrences": {},
            "candidate_routes": routes,
        }
    )
    _, projections = prepare_scope_lookups(
        {
            "previous": [],
            "objects": objects,
            "identities": identities,
            "previous_publications": {},
        }
    )
    indices = {
        (e["type"], e["id"]): storage_api.IndexChange(
            e["type"], e["id"], e["body_json"]
        )
        for e in [*history, *current, *projections]
    }
    if case in ("wrong_anchor", "wrong_member"):
        group = RecordReader.group("record_readings", subjects[0])
        del indices[group, readings[0]["assertion_id"]]
        key = (
            readings[1]["assertion_id"]
            if case == "wrong_anchor"
            else "invented-wrong-member"
        )
        indices[group, key] = storage_api.IndexChange(
            group,
            key,
            {
                "type": "source-reading",
                "id": readings[1]["assertion_id"],
                "immutable": True,
            },
        )
    if case == "wrong_projection":
        group = RecordReader.group("outgoing_links", ids[0])
        indices[group, links[1]["id"]] = storage_api.IndexChange(
            group,
            links[1]["id"],
            {"type": "relationship", "id": links[1]["id"], "immutable": False},
        )
    if case == "wrong_membership":
        group = RecordReader.group("master_members", ids[0])
        indices[group, subjects[1]] = storage_api.IndexChange(
            group, subjects[1], {"subject": subjects[1]}
        )
    if case == "wrong_candidate":
        group = RecordReader.group("name_candidates", source, "invented-route", "1")
        indices[group, subjects[0]] = storage_api.IndexChange(
            group, subjects[0], {"subject": subjects[0]}
        )
    if case.startswith("pointer_"):
        field = case.removeprefix("pointer_")
        key = ("source-record", subjects[0])
        body = json.loads(indices[key].body)
        body[field] = (
            {"invented": "changed"}
            if field in ("identifiers", "cross_references")
            else "changed"
        )
        indices[key] = storage_api.IndexChange(*key, body)
    if case == "bad_floor":
        indices["identity-publication", kind] = storage_api.IndexChange(
            "identity-publication",
            kind,
            {"entity_id": ids[0], "kind": kind, "published_at": "2000-01-01T00:00:00Z"},
        )
    if case == "dangling_input":
        evidence = [e for e in evidence if e["id"] != readings[0]["assertion_id"]]
    if case == "missing_projection":
        objects = [o for o in objects if o["id"] != links[0]["id"]]
    if case == "plans":
        for i in range(2000):
            key = "invented-unrelated-" + str(i)
            indices["lookup/unrelated", key] = storage_api.IndexChange(
                "lookup/unrelated", key, {"subject": key}
            )
    prepared = replace(
        request,
        batch="invented-scope",
        objects=tuple(
            storage_api.Effect(o["type"], o["id"], o["body"]) for o in objects
        ),
        evidence=tuple(
            storage_api.Effect(e["type"], e["id"], e["body_json"]) for e in evidence
        ),
        indexes=tuple(indices.values()),
    )
    runtime.apply(prepared, lease)
    reader = RecordReader(runtime, routes=routes)
    if case.startswith("pointer_"):
        with pytest.raises(Conflict):
            reader.bindings([subjects[0]])
        return
    if case == "wrong_membership":
        with pytest.raises(Conflict):
            reader.members(ids)
        return
    if case == "wrong_candidate":
        with pytest.raises(Conflict):
            reader.candidates(source, "invented-route", ["0", "1"])
        return
    if case == "bad_floor":
        with pytest.raises(Conflict):
            reader.newest([kind])
        return
    if case in ("wrong_anchor", "wrong_member", "dangling_input", "mismatched_input"):
        with pytest.raises(ValueError):
            scope.identities(reader, [readings[0]], [])
        return
    if case in ("wrong_projection", "missing_projection"):
        with pytest.raises(Conflict):
            reader.projections(starts=[ids[0]])
        return
    start = 1 if case == "hierarchy" else 0
    affected = scope.identities(reader, [readings[start]], [])
    assert affected.subjects == {subjects[start]}
    assert len(affected.readings) == len(affected.identities) == 1
    affected.masters = {ids[start]}
    affected.replayed = {subjects[start]: ids[start]}
    if case in ("plain", "hierarchy"):
        scope.links(
            reader,
            affected,
            {ids[start]},
            {ids[start]},
            {"invented-parent": {"hierarchy": True}},
            [readings[start]],
        )
        assert affected.starts == (
            {ids[1], ids[2]} if case == "hierarchy" else {ids[0]}
        )
        # A changed hierarchy end also rechecks a plain link coming into it;
        # its source reading is needed without replaying that source's identity.
        assert set(affected.readings) == (
            {r["assertion_id"] for r in readings}
            if case == "hierarchy"
            else {readings[0]["assertion_id"]}
        )
        if case == "plain":
            assert (
                affected.master(subjects[1]) == ids[1]
                and subjects[1] not in affected.subjects
            )
    elif case == "current_links":
        assert scope._chain(
            reader, {ids[1]}, {"invented-parent": {"hierarchy": True}}
        ) == {ids[1], ids[2]}
        assert len(reader.projections(starts=ids)) == 2
    elif case == "reviews":
        affected.starts = {ids[0]}
        found = scope.stored_links_and_reviews(reader, affected)
        assert {(r["object_type"], r["object_id"]) for r in found} == {
            ("relationship", links[0]["id"]),
            ("review", review["id"]),
        }
    elif case == "members":
        assert reader.members(ids) == set(subjects)
        assert len(reader.source_readings(subjects)) == 3
    else:
        if owner.engine.dialect.name == "postgresql":
            # Inspect realistic cardinalities after this fixture's fresh bulk
            # load, before autovacuum has had an opportunity to collect them.
            with owner.engine.begin() as conn:
                for name in ("lookup", "evidence"):
                    table = owner.engine.dialect.identifier_preparer.format_table(
                        runtime.tables[name]
                    )
                    conn.exec_driver_sql("ANALYZE " + table)
        groups = [reader.group("record_readings", key) for key in subjects]
        assert_group_probes(
            owner.engine,
            runtime.lookup_groups_statement(groups),
            runtime.tables["lookup"].name,
            len(groups),
        )
        assert_index_lookup(
            owner.engine,
            runtime.lookup_statement(
                [("source-reading", r["assertion_id"]) for r in readings],
                immutable=True,
            ),
            runtime.tables["evidence"].name,
        )
        assert_index_lookup(
            owner.engine,
            runtime.lookup_statement(
                [("source-record", s) for s in subjects], lookup=True
            ),
            runtime.tables["lookup"].name,
        )
    assert runtime.apply(prepared, lease)["duplicate"]
