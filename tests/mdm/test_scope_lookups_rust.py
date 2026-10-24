"""Scope indexes retain references, with no second policy or merge calculation."""

import copy

import pytest

from edgar_warehouse.rules.source_engine import prepare_scope_lookups


def prepare(previous=(), objects=(), identities=(), publications=None):
    return prepare_scope_lookups(
        {
            "previous": list(previous),
            "objects": list(objects),
            "identities": list(identities),
            "previous_publications": publications or {},
        }
    )


def relationship(source="one", target="two"):
    return {
        "type": "relationship",
        "id": "invented-link",
        "body": {
            "relationship_id": "invented-link",
            "source_id": source,
            "target_id": target,
            "type": "invented-hierarchy",
            "retired": False,
        },
    }


def test_projection_keys_change_only_their_affected_groups():
    first = relationship()
    publications, created = prepare(objects=[first])
    assert not publications and len(created) == 2
    assert {row["type"] for row in created} == {
        'lookup/outgoing_links/["one"]',
        'lookup/incoming_links/["two"]',
    }
    assert all('"immutable":false' in row["body_json"] for row in created)
    assert prepare(previous=[first], objects=[copy.deepcopy(first)]) == ({}, [])
    corrected = relationship(target="three")
    _, changes = prepare(previous=[first], objects=[corrected])
    assert len(changes) == 2
    assert {(row["type"], row["removed"]) for row in changes} == {
        ('lookup/incoming_links/["two"]', True),
        ('lookup/incoming_links/["three"]', False),
    }
    _, removed = prepare(previous=[corrected])
    assert len(removed) == 2 and all(row["removed"] for row in removed)


def test_review_references_include_each_named_scope_key_once():
    review = {
        "type": "review",
        "id": "invented-review",
        "body": {
            "review_id": "invented-review",
            "entity_id": "one",
            "subject": "record",
            "affected_subjects": ["record", "other"],
            "entities": ["one", "two"],
        },
    }
    _, changes = prepare(objects=[review])
    assert {row["type"] for row in changes} == {
        'lookup/related_reviews/["one"]',
        'lookup/related_reviews/["two"]',
        'lookup/related_reviews/["record"]',
        'lookup/related_reviews/["other"]',
    }


def test_publication_floor_compares_instants_and_keeps_original_identity():
    first = {
        "entity_id": "one",
        "kind": "invented-kind",
        "published_at": "2026-01-01T00:00:00Z",
    }
    later = {
        "entity_id": "two",
        "kind": "invented-kind",
        "published_at": "2025-12-31T21:00:00-04:00",
    }
    publications, changes = prepare(identities=[later, first])
    assert publications == {"invented-kind": later}
    assert len(changes) == 1 and changes[0]["type"] == "identity-publication"
    assert prepare(identities=[first, later], publications=publications) == (
        publications,
        [],
    )
    assert prepare(identities=[first], publications=publications) == (publications, [])


@pytest.mark.parametrize(
    "case", ["wrong_key", "duplicate", "unsupported", "bad_floor", "bad_time"]
)
def test_invalid_scope_inputs_are_refused(case):
    objects = [relationship()]
    publications = {}
    identities = []
    if case == "wrong_key":
        objects[0]["id"] = "another"
    elif case == "duplicate":
        objects *= 2
    elif case == "unsupported":
        objects[0]["type"] = "invented-unsupported-type"
    elif case == "bad_floor":
        publications = {"one": {"kind": "two"}}
    else:
        identities = [
            {"entity_id": "one", "kind": "invented-kind", "published_at": "not-a-time"}
        ]
    with pytest.raises(ValueError):
        prepare(objects=objects, identities=identities, publications=publications)
