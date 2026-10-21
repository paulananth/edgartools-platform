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
        body = {key: store._plain(row.get(key)) for key in store.CODE_COLUMNS}
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
