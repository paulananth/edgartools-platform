"""Native preparation preserves the existing canonical format and full key distinctions."""
import hashlib
import json
from datetime import date

import pytest

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.rdm import store
from edgar_warehouse.rules.files import RulesFileError, context_subjects


def test_canonical_reference_bytes_match_the_existing_format():
    rows = [{"code": "b", "label": "Leaf Ω", "definition": "Invented", "parent_code": "a/\\",
             "valid_from": date(2026, 1, 1), "valid_to": None, "status": "valid", "invalid_reason": None,
             "labels": [{"language": "en", "kind": "synonym", "label": "Alternative"}],
             "crosswalk": [{"to_set": "other", "to_version": "outside", "to_code": "X", "match_type": "exact"}]},
            {"code": "a/\\", "label": "Root", "definition": "", "status": "valid"}]
    expected = []
    for row in sorted(rows, key=lambda row: row["code"]):
        # A typed value is in the canonical form only on a code that has one.
        body = {key: store._plain(row.get(key)) for key in store.CODE_COLUMNS
                if key not in ("value", "unit") or row.get("value") is not None}
        body["level"] = "Root level" if row["code"] == "a/\\" else "Leaf level"
        body["labels"] = sorted([label["language"], label["kind"], label["label"]] for label in row.get("labels", []))
        body["crosswalk"] = sorted([item["to_set"], item["to_version"], item["to_code"], item["match_type"]]
                                   for item in row.get("crosswalk", []))
        expected.append(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    expected = "".join(expected).encode()
    levels = {1: "Root level", 2: "Leaf level"}
    assert store.canonical(rows, levels) == expected
    assert store.sha256(rows, levels) == hashlib.sha256(expected).hexdigest()
    assert store.canonical(list(reversed(rows)), levels) == expected
    assert [row["code"] for row in store.paths(rows, levels)] == [row["code"] for row in rows]


def test_a_typed_value_is_pinned_with_its_unit():
    plain = [{"code": "a", "label": "Invented"}]
    valued = [{"code": "a", "label": "Invented", "value": "25.500000", "unit": "percent"}]
    line = json.loads(store.canonical(valued))
    assert (line["value"], line["unit"]) == ("25.500000", "percent")
    assert store.sha256(valued) != store.sha256(plain)
    assert store.sha256([{**plain[0], "value": None, "unit": None}]) == store.sha256(plain)
    for value, unit in (("25.5", None), ("2.5e1", "percent"), ("25.", "percent"), ("twenty", "percent")):
        with pytest.raises(Blocked, match="decimal text"):
            store.canonical([{"code": "a", "label": "Invented", "value": value, "unit": unit}])


PUBLISHED = sorted((store_path.parent for store_path in
                    __import__("pathlib").Path(__file__).parents[2].glob("rules/reference/published/*/*/pin.json")))


@pytest.mark.parametrize("folder", PUBLISHED, ids=lambda f: f"{f.parent.name}@{f.name}")
def test_every_published_version_keeps_its_pinned_bytes(folder):
    """Each version the repository pins, rebuilt from its own rows, gives the same bytes."""
    data = (folder / "canonical.jsonl").read_bytes()
    pin = json.loads((folder / "pin.json").read_text())
    assert hashlib.sha256(data).hexdigest() == pin["sha256"]
    lines = [json.loads(line) for line in data.decode().splitlines()]
    parents = {row["code"]: row["parent_code"] for row in lines}

    def depth(code):
        return 1 if parents[code] is None else 1 + depth(parents[code])

    levels = {depth(row["code"]): row["level"] for row in lines if row["level"] is not None}
    rows = [{**{key: row[key] for key in row if key not in ("labels", "crosswalk", "level")},
             "labels": [dict(zip(("language", "kind", "label"), label)) for label in row["labels"]],
             "crosswalk": [dict(zip(("to_set", "to_version", "to_code", "match_type"), item)) for item in row["crosswalk"]],
             "value": row.get("value"), "unit": row.get("unit")} for row in lines]
    assert store.canonical(rows, levels) == data


@pytest.mark.parametrize("rows,reason", [
    ([{"code": "a", "label": "A", "parent_code": "missing"}], "parent"),
    ([{"code": "a", "label": "A", "parent_code": "a"}], "cycle"),
    ([{"code": "a", "label": "A"}, {"code": "a", "label": "A"}], "duplicate"),
])
def test_invalid_hierarchies_are_refused(rows, reason):
    with pytest.raises(Blocked, match=reason):
        store.paths(rows, {})


def test_a_cyclic_draft_can_still_be_described():
    result = store._prepare([{"code": "a", "label": "A", "parent_code": "a"}], prepare=False)
    assert result["counts"] == {"codes": 1, "invalid": 0, "with_parent": 1}


def test_namespace_comes_from_configuration(tmp_path):
    path = tmp_path / "context" / "definitions.yaml"
    path.parent.mkdir()
    path.write_text("kinds: {invented-kind: Invented, another-kind: Another}\n")
    assert context_subjects(tmp_path) == {"invented-kind", "another-kind", "relationship"}
    path.write_text("kinds: [invented-kind]\n")
    with pytest.raises(RulesFileError, match="configured kinds"):
        context_subjects(tmp_path)
