"""A link may start at another record than the one stating it (platform
validation 06a): the adapter reads `source_key`/`source_source` the way it
reads `target_key`/`target_source`, and nothing changes when they are absent."""

from __future__ import annotations

from edgar_warehouse.mdm.clean.adapters import normalize, subject_key

PUBLICATION = {"publication_key": "p1", "revision": 1, "artifact_sha256": "a" * 64, "member": "m"}
LINK = {
    "type_field": "relationship_type",
    "type_values": {"IS_DIRECTLY_CONSOLIDATED_BY": "IS_DIRECTLY_CONSOLIDATED_BY"},
    "target_key": ["end"],
    "target_source": "fixture.level1",
    "valid_from": "valid_from",
    "scope": "GLEIF accounting consolidation",
}
ROW = {"start": "CHILD", "end": "PARENT", "relationship_type": "IS_DIRECTLY_CONSOLIDATED_BY",
       "valid_from": "2026-01-01T00:00:00+00:00"}


def read(link: dict) -> dict:
    contract = {"schema_version": "1", "adapter": {
        "version": "fixture-v1", "kind": "company", "record_key": ["start", "end", "relationship_type"],
        "fields": {}, "relationships": [link]}}
    return normalize(ROW, source_code="fixture.relationships", contract=contract, publication=PUBLICATION)


def test_a_link_with_a_source_key_starts_at_that_record():
    (link,) = read({**LINK, "source_key": ["start"], "source_source": "fixture.level1"})["relationships"]
    assert link["source_subject"] == subject_key("fixture.level1", "CHILD")
    assert link["target_subject"] == subject_key("fixture.level1", "PARENT")


def test_without_a_source_key_the_link_starts_at_its_own_record_as_before():
    reading = read(LINK)
    (link,) = reading["relationships"]
    assert sorted(link) == ["properties", "scope", "target_subject", "type", "valid_from", "valid_to"]
    # The reading's id, taken from the adapter before 06a: a mapping without a
    # `source_key` reads exactly as it did.
    assert reading["assertion_id"] == "7b3983f3d04be589d0b42bc6c3c49e6642c55fd10300ed708e51225a13d485a4"
