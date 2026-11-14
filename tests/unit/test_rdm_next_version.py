"""The next version of a published code set: every published code, plus the added ones."""
import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import rdm_next_version  # noqa: E402

ROOT = rdm_next_version.DEFAULT_ROOT
ADDED = [{"code": "INVESTMENT_ADVISER_TO:invented", "parent_code": "INVESTMENT_ADVISER_TO", "level": "Capacity",
          "label": "Invented", "definition": "An invented capacity. Source: a test."}]


def test_a_published_version_rebuilds_its_pinned_bytes():
    version, rows = rdm_next_version.published(ROOT, "mdm-relationship-types")
    pin = json.loads((ROOT / "mdm-relationship-types" / version / "pin.json").read_text())
    assert rdm_next_version.rebuilds(rows, pin["sha256"])
    rows[0] = {**rows[0], "label": rows[0]["label"] + " changed"}
    assert not rdm_next_version.rebuilds(rows, pin["sha256"])


def test_the_draft_holds_every_published_code_and_the_added_one(tmp_path):
    add, out = tmp_path / "add.yaml", tmp_path / "draft.yaml"
    add.write_text(yaml.safe_dump(ADDED))
    assert rdm_next_version.main(["mdm-relationship-types", "99", "--add", str(add), "--out", str(out)]) == 0
    draft = yaml.safe_load(out.read_text())
    version, rows = rdm_next_version.published(ROOT, "mdm-relationship-types")
    assert draft["supersedes"] == version and draft["version"] == "99"
    assert [c["code"] for c in draft["codes"]] == [r["code"] for r in rows] + ["INVESTMENT_ADVISER_TO:invented"]
    assert {"depth": 2, "name": "Capacity"} in draft["levels"]
    assert {"code": "INVESTMENT_ADVISER_TO:invented", "language": "en", "kind": "preferred",
            "label": "Invented"} in draft["labels"]


def test_a_code_already_held_is_refused(tmp_path):
    add = tmp_path / "add.yaml"
    add.write_text(yaml.safe_dump([{**ADDED[0], "code": "INVESTMENT_ADVISER_TO"}]))
    with pytest.raises(SystemExit, match="already held"):
        rdm_next_version.main(["mdm-relationship-types", "99", "--add", str(add), "--out", str(tmp_path / "d.yaml")])
