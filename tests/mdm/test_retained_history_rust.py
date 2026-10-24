"""Immutable reading revisions, held records and delivery evidence use shared indexes."""

from hashlib import sha256
import json

import pytest

from edgar_warehouse.rules.source_engine import prepare_record_history


def prepare(*, readings=(), deferred=(), occurrences=()):
    return prepare_record_history({"readings": list(readings), "identities": [],
                                   "decisions": [], "deferred": list(deferred),
                                   "occurrences": list(occurrences)})


def reading(key="invented-reading", revision=1):
    return {"assertion_id": key, "subject": "invented-record", "source_code": "invented.source",
            "record_key": "one", "revision": revision, "relationships": []}


def test_reading_revision_pointer_refuses_contradictory_publications():
    evidence, indexes = prepare(readings=[reading(), reading(revision=2, key="invented-newer")])
    assert len(evidence) == 2
    versions = [row for row in indexes if row["type"].startswith("lookup/record_revision/")]
    assert len(versions) == 2 and all(row["id"] == "reading" for row in versions)
    with pytest.raises(ValueError, match="contradictory content"):
        prepare(readings=[reading(), reading(key="invented-contradiction")])


def test_deferred_natural_key_is_immutable():
    held = {"deferred_id": "invented-held", "source_code": "invented.source",
            "publication_key": "one", "record_locator": "held", "raw_record": {"amount": 7}}
    evidence, indexes = prepare(deferred=[held, held])
    assert len(evidence) == len(indexes) == 1
    assert json.loads(evidence[0]["body_json"]) == held
    with pytest.raises(ValueError, match="contradictory content"):
        prepare(deferred=[held, {**held, "deferred_id": "invented-another", "raw_record": {"amount": 8}}])


def test_occurrences_retain_original_body_and_reading_reference():
    occurrence = {"assertion_id": "invented-reading", "object": "invented/capture.json",
                  "sha256": "a" * 64, "locator": "one"}
    evidence, indexes = prepare(occurrences=[occurrence, occurrence])
    assert len(evidence) == len(indexes) == 1
    entry = evidence[0]
    assert entry["type"] == "source-occurrence"
    assert json.loads(entry["body_json"]) == occurrence
    assert entry["id"] == sha256(entry["body_json"].encode()).hexdigest()
    assert json.loads(indexes[0]["body_json"])["id"] == entry["id"]
