"""The repository's exposure list names RDM's published-only table and no table that holds drafts."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills" / "data-platform" / "scripts" / "exposure"))

from exposure_manifest import load_config  # noqa: E402


def test_the_list_exposes_rdms_published_codes_only():
    config = load_config(ROOT / "rules" / "exposure.yaml")
    assert [entry["table"] for entry in config["tables"] if entry["layer"] == "rdm"] == ["published_code"]
    assert config["layers"]["rdm"]["source_schema"] == "rdm"
