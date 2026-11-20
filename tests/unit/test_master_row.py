"""A golden record as the store keeps it: the split loses nothing, and the text holds only what no column or table holds."""
import json

import pytest

from edgar_warehouse.mastering import master_row

STAMPS = {"policy_digest": "invented-policy", "kind_version": "invented-kind-1"}
MASTER = {
    "entity_id": "00000000-0000-0000-0000-000000000001", "kind": "company", "status": "accepted",
    "canonical_id": "00000000-0000-0000-0000-000000000001",
    "identifiers": {"cik": ["0000000001"], "lei": ["INVENTEDLEI000000001", "INVENTEDLEI000000002"]},
    "subjects": ["invented-subject-a", "invented-subject-b"],
    "profiles": [{"profile_id": "p1", "role": "adviser", "valid_from": "2015-01-01", "valid_to": None, "fields": {}, "evidence": []},
                 {"profile_id": "p2", "role": "auditor", "valid_from": "2020-01-01", "valid_to": "2021-01-01", "fields": {}, "evidence": []}],
    "fields": {"name": {"value": "INVENTED CO", "winner": {"source": "invented"}, "cleared": False, "conflicts": [], **STAMPS},
               "jurisdiction": {"value": "XX", "winner": {"source": "invented"}, "cleared": False, "conflicts": [], **STAMPS}},
    "details": {"invented": True},
}
ALIAS = {"entity_id": "00000000-0000-0000-0000-000000000002", "kind": "company",
         "canonical_id": "00000000-0000-0000-0000-000000000001", "status": "alias"}


def round_trip(body):
    columns, profiles, text = master_row.split(body)
    identifiers = body.get("identifiers") or {}
    return master_row.assemble(body["entity_id"], columns, text, identifiers, body.get("subjects") or [], profiles)


@pytest.mark.parametrize("body", [MASTER, ALIAS, {**MASTER, "profiles": []}, {k: v for k, v in MASTER.items() if k != "details"}],
                         ids=["master", "alias", "no-profiles", "no-details"])
def test_a_split_master_assembles_to_what_survivorship_gave(body):
    assert round_trip(body) == body


def test_the_text_holds_no_column_no_other_tables_rows_and_no_stamp():
    columns, profiles, text = master_row.split(MASTER)
    assert columns == {"kind": "company", "status": "accepted", "canonical_id": MASTER["canonical_id"], **STAMPS}
    assert [p["profile_id"] for p in profiles] == ["p1", "p2"]
    kept = json.loads(text)
    assert set(kept) == {"fields", "details", "_held", "_held_sha256"}
    assert not any(stamp in value for value in kept["fields"].values() for stamp in STAMPS)
    assert "INVENTEDLEI000000001" not in text and "invented-subject-a" not in text


@pytest.mark.parametrize("change", [{"kind_version": "another"}, {"kind_version": None}])
def test_a_master_whose_fields_disagree_on_a_stamp_is_refused(change):
    fields = {**MASTER["fields"], "jurisdiction": {**MASTER["fields"]["jurisdiction"], **change}}
    if change["kind_version"] is None:
        del fields["jurisdiction"]["kind_version"]
    with pytest.raises(ValueError, match="kind_version"):
        master_row.split({**MASTER, "fields": fields})


def test_a_master_whose_rows_drifted_from_what_was_written_is_refused():
    columns, profiles, text = master_row.split(MASTER)
    with pytest.raises(ValueError, match="differ from what was written"):
        master_row.assemble(MASTER["entity_id"], columns, text, {**MASTER["identifiers"], "cik": ["0000000009"]},
                            MASTER["subjects"], profiles)


def test_a_change_to_a_masters_rows_alone_changes_its_text():
    _, _, before = master_row.split(MASTER)
    _, _, after = master_row.split({**MASTER, "subjects": [*MASTER["subjects"], "invented-subject-c"]})
    assert before != after
