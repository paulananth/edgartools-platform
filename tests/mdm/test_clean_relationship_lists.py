"""A relationship mapping reads lists (profiling ticket 04c; operator,
2026-10-07: "Approved"): `each` makes one link per item of a list, read under
`item.`; `find` adds the first item of another list whose `where` paths match,
read under its name. A path through a nested list matches when any element
does. A mapping without them reads exactly as before (test_clean_link_start)."""

from __future__ import annotations

import pytest

from edgar_warehouse.mdm.clean.adapters import MappingError, normalize, subject_key

PUBLICATION = {"publication_key": "p1", "revision": 1, "artifact_sha256": "a" * 64, "member": "m"}
LINK = {
    "type": "SUCCEEDS",
    "each": "successors",
    "target_key": ["item.id"],
    "target_source": "fixture.records",
    "find": {"event": {"in": "events", "where": {"status": "DONE", "touched.id": {"path": "item.id"}}}},
    "valid_from": "event.date",
    "properties": {"source_event": "event.kind"},
}


def read(row: dict, link: dict = LINK) -> list[dict]:
    contract = {"schema_version": "1", "adapter": {
        "version": "fixture-v1", "kind": "company", "record_key": ["key"], "fields": {}, "relationships": [link]}}
    return normalize({"key": "K", **row}, source_code="fixture.records", contract=contract,
                     publication=PUBLICATION)["relationships"]


def test_one_link_per_item_dated_by_the_event_that_names_it():
    links = read({
        "successors": [{"id": "A"}, {"name": "no id"}, {"id": "B"}],
        "events": [
            {"status": "CANCELLED", "kind": "MERGER", "date": "2020-01-01", "touched": [{"id": "A"}]},
            {"status": "DONE", "kind": "MERGER", "date": "2021-01-01", "touched": [{"id": "X"}, {"id": "A"}]},
        ],
    })
    assert [(link["target_subject"], link["valid_from"], link["properties"]) for link in links] == [
        (subject_key("fixture.records", "A"), "2021-01-01", {"source_event": "MERGER"}),
        (subject_key("fixture.records", "B"), None, {"source_event": None}),
    ]


def test_a_lone_item_is_a_list_of_one_and_no_list_is_no_link():
    (link,) = read({"successors": {"id": "A"}, "events": {"status": "DONE", "kind": "M", "date": "d",
                                                         "touched": {"id": "A"}}})
    assert (link["valid_from"], link["properties"]) == ("d", {"source_event": "M"})
    assert read({}) == []


def test_find_without_each_reads_the_record_itself():
    link = {"type": "SUCCEEDS", "target_key": ["next"], "target_source": "fixture.records",
            "find": {"event": {"in": "events", "where": {"status": "DONE"}}}, "valid_from": "event.date"}
    (found,) = read({"next": "A", "events": [{"status": "OPEN", "date": "1"}, {"status": "DONE", "date": "2"}]}, link)
    assert found["valid_from"] == "2"


def test_a_list_of_values_matches_any_of_them():
    link = {**LINK, "find": {"event": {"in": "events", "where": {
        "kind": ["MERGER", "SPLIT"], "touched.id": {"path": "item.id"}}}}}
    links = read({"successors": [{"id": "A"}, {"id": "B"}], "events": [
        {"kind": "RENAME", "date": "1", "touched": [{"id": "A"}]},
        {"kind": "SPLIT", "date": "2", "touched": [{"id": "A"}]}]}, link)
    assert [found["valid_from"] for found in links] == ["2", None]


def test_a_mapping_that_cannot_run_stops_the_run_and_is_no_source_defect():
    # Not a ValueError: a reader that sets aside source defects does not catch it.
    assert not issubclass(MappingError, ValueError)
    with pytest.raises(MappingError, match="hide the record's own fields"):
        read({"item": "a field of the record", "successors": [{"id": "A"}]})
    with pytest.raises(MappingError, match="names its list"):
        read({"successors": [{"id": "A"}]}, {**LINK, "find": {"event": {"in": "events"}}})
