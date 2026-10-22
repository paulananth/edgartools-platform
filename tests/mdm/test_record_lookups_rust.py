"""Latest readings and correction lookups are one Rust operation for every kind."""

import pytest

from edgar_warehouse.mdm.clean.evidence import KINDS, assertion
from edgar_warehouse.rules.source_engine import prepare_record_lookups

AT = "2026-01-01T00:00:00+00:00"
MASTER = "00000000-0000-0000-0000-000000000001"


def reading(revision=1, kind="person", **changes):
    args = dict(source_code="fixture.latest", record_key="one", publication_key=str(revision),
                revision=revision, effective_at=AT, kind=kind, fields={"amount": 10**80},
                identifiers={"number": "17-1"})
    return assertion(**{**args, **changes})


def prepare(readings, previous=None, *, bindings=None, subjects=None, occurrences=None, batch="first"):
    previous = previous or {}
    subjects = subjects if subjects is not None else sorted(set(previous) | {item["subject"] for item in readings})
    return prepare_record_lookups({
        "readings": readings, "previous": previous, "subjects": subjects,
        "bindings": bindings or {}, "quarantined": {}, "batch_id": batch,
        "occurrences": occurrences or {}, "normalizers": {},
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
