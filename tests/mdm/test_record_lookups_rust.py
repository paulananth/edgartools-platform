"""Latest readings and correction lookups are one Rust operation for every kind."""

import pytest

from edgar_warehouse.mdm.clean.evidence import KINDS, assertion
from edgar_warehouse.mdm.clean.matching import candidate_routes
from edgar_warehouse.rules.source_engine import prepare_record_lookups

AT = "2026-01-01T00:00:00+00:00"
MASTER = "00000000-0000-0000-0000-000000000001"


def reading(revision=1, kind="person", **changes):
    args = dict(source_code="fixture.latest", record_key="one", publication_key=str(revision),
                revision=revision, effective_at=AT, kind=kind, fields={"amount": 10**80},
                identifiers={"number": "17-1"})
    return assertion(**{**args, **changes})


def prepare(readings, previous=None, *, bindings=None, subjects=None, occurrences=None, batch="first", routes=None):
    previous = previous or {}
    subjects = subjects if subjects is not None else sorted(set(previous) | {item["subject"] for item in readings})
    return prepare_record_lookups({
        "readings": readings, "previous": previous, "subjects": subjects,
        "bindings": bindings or {}, "quarantined": {}, "batch_id": batch,
        "occurrences": occurrences or {}, "normalizers": {},
        "candidate_routes": candidate_routes() if routes is None else routes,
        "policy": {"kinds": {kind: {"identifiers": {"number": {
            "normalizer": "normalize_identifier@crd-v1", "sources": ["fixture.latest"],
        }}} for kind in sorted(KINDS)}},
    })


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_each_kind_keeps_one_latest_pointer_and_normalized_lookup(kind):
    item = reading(kind=kind)
    current, changes = prepare([item], bindings={item["subject"]: MASTER})
    record = current[item["subject"]]
    assert record["assertion_id"] == item["assertion_id"] and record["entity_id"] == MASTER
    assert record["normalized_identifiers"] == {"number": "171"}
    assert "fields" not in record and "snapshot" not in record
    assert any(entry["type"].startswith("lookup/master_members/") for entry in changes)
    assert any(entry["type"].startswith("lookup/identifier_records/") and '"bound"' in entry["type"] for entry in changes)


def test_newer_reading_wins_independently_of_delivery_order():
    older, newer = reading(), reading(2)
    current, _ = prepare([newer, older])
    assert current[newer["subject"]]["assertion_id"] == newer["assertion_id"]
    same, changes = prepare([older], current, batch="late")
    assert same == current and changes == []


def test_duplicate_delivery_keeps_the_original_occurrence():
    item = reading()
    first = {"assertion_id": item["assertion_id"], "object": "fixture://first", "sha256": "a" * 64, "locator": "one"}
    current, _ = prepare([item], occurrences={item["assertion_id"]: first})
    assert current[item["subject"]]["bronze"] == {key: first[key] for key in ("object", "sha256", "locator")}
    repeated, changes = prepare([item], current, occurrences={item["assertion_id"]: {**first, "object": "fixture://second"}}, batch="again")
    assert repeated == current and changes == []


def test_same_revision_with_different_content_is_refused():
    current, _ = prepare([reading()])
    with pytest.raises(ValueError, match="contradictory publications"):
        prepare([reading(fields={"amount": 2})], current)


def test_revocation_removes_membership_and_moves_the_identifier_lookup():
    item = reading()
    current, _ = prepare([item], bindings={item["subject"]: MASTER})
    corrected, changes = prepare([], current)
    assert corrected[item["subject"]]["entity_id"] is None
    assert any(entry["type"].startswith("lookup/master_members/") and entry["removed"] for entry in changes)
    assert any('"bound"' in entry["type"] and entry["removed"] for entry in changes)
    assert any('"unbound"' in entry["type"] and not entry["removed"] for entry in changes)


def test_records_outside_the_affected_scope_are_not_changed_or_removed():
    first, second = reading(), reading(record_key="other")
    current, _ = prepare([first, second], bindings={first["subject"]: MASTER, second["subject"]: MASTER})
    scoped, changes = prepare([], current, bindings={first["subject"]: MASTER}, subjects=[first["subject"]])
    assert set(scoped) == {first["subject"]} and changes == []


def test_reading_outside_the_declared_scope_is_refused():
    with pytest.raises(ValueError, match="outside its affected record scope"):
        prepare([reading()], subjects=[])


@pytest.mark.parametrize("value,expected", [("invented-target", {"invented-route":"invented-target"}),
    (None, {}), (False, {}), (0, {}), ("", {}), ([], {}), ({"value":"invented-target"}, {})])
def test_candidate_route_reads_only_nonempty_scalar_keys(value, expected):
    item = reading(provenance={"matching":{"invented_census":{"invented_entries":[[value,1]]}}})
    route = {"invented-route":["provenance","matching","invented_census","invented_entries",0,0]}
    current, changes = prepare([item], routes=route)
    assert current[item["subject"]]["matching_keys"] == expected
    groups = [entry for entry in changes if entry["type"].startswith("lookup/name_candidates/")]
    assert len(groups) == len(expected)


def test_profile_routes_include_identifier_census_and_cascade_without_fixed_fields():
    item = reading(provenance={"matching":{"invented/field'Ω":{"entries":[["target-one",1]],
        "assignment":{"target":"target-two"}}}})
    routes = {"reference":["identifiers","number"],
        "census":["provenance","matching","invented/field'Ω","entries",0,0],
        "assignment":["provenance","matching","invented/field'Ω","assignment","target"]}
    current, _ = prepare([item], routes=routes)
    assert current[item["subject"]]["matching_keys"] == {
        "reference":"17-1", "census":"target-one", "assignment":"target-two"}
    assert len(current[item["subject"]]["matching_routes_sha256"]) == 64


def test_route_upgrade_reindexes_retained_latest_reading_without_a_new_revision():
    item = reading(provenance={"matching":{"one":"old-target","two":"new-target"}})
    before, _ = prepare([item], routes={"old":["provenance","matching","one"]})
    after, changes = prepare([item], before, routes={"new":["provenance","matching","two"]}, batch="later")
    assert after[item["subject"]]["matching_keys"] == {"new":"new-target"}
    assert after[item["subject"]]["batch_id"] == "first"
    assert after[item["subject"]]["assertion_id"] == item["assertion_id"]
    groups = [entry for entry in changes if entry["type"].startswith("lookup/name_candidates/")]
    assert len(groups) == 2 and sum(entry["removed"] for entry in groups) == 1
    repeated, changes = prepare([item], after, routes={"new":["provenance","matching","two"]}, batch="again")
    assert repeated == after and changes == []
    with pytest.raises(ValueError, match="require the retained latest reading"):
        prepare([], before, routes={"new":["provenance","matching","two"]})


def test_old_pointer_without_route_fingerprint_requires_its_latest_reading():
    item = reading()
    before, _ = prepare([item])
    before[item["subject"]].pop("matching_routes_sha256")
    with pytest.raises(ValueError, match="require the retained latest reading"):
        prepare([], before)
    after, _ = prepare([item], before, batch="repair")
    assert after[item["subject"]]["batch_id"] == "first"
    assert after[item["subject"]]["assertion_id"] == item["assertion_id"]
    assert after[item["subject"]]["matching_routes_sha256"]


@pytest.mark.parametrize("route", [{"": ["identifiers","number"]}, {"route": []},
    {"route":["missing",""]}, {"route":["identifiers",-1]}, {"route":["identifiers",True]}])
def test_invalid_candidate_route_is_refused_before_data_dependent_selection(route):
    with pytest.raises(ValueError):
        prepare([reading()], routes=route)
    with pytest.raises(ValueError):
        prepare([], routes=route)
