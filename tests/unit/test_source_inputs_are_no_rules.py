"""A source's `inputs.yaml` says where its files are, not how they are read: adding a delivery must change no rules version."""
import shutil
from pathlib import Path

import pytest

from edgar_warehouse.mdm import changed_files
from edgar_warehouse.rules import catalog, files

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def copy(tmp_path, monkeypatch):
    """The repository's `rules/` and `sources/gleif` copied beside each other, and the rules root pointed at the copy."""
    shutil.copytree(REPO / "rules", tmp_path / "rules")
    folder = tmp_path / "sources" / "gleif"
    folder.mkdir(parents=True)
    for path in (REPO / "sources/gleif").glob("*.yaml"):
        shutil.copy(path, folder / path.name)
    monkeypatch.setattr(files, "ROOT", tmp_path / "rules")
    return folder


def test_a_new_delivery_changes_neither_the_processing_identity_nor_the_rules_digest(copy):
    identity, digest = changed_files.source_rules("gleif"), catalog.rules_digest(copy.parents[1] / "rules")
    inputs = copy / "inputs.yaml"
    inputs.write_text(inputs.read_text() + "  another-delivery:\n    folder: gleif/another-delivery\n")
    assert changed_files.source_rules("gleif") == identity
    assert catalog.rules_digest(copy.parents[1] / "rules") == digest
    assert "inputs.yaml" not in identity


def test_another_rules_file_of_the_source_still_counts(copy):
    identity = changed_files.source_rules("gleif")
    (copy / "quality.yaml").write_text((copy / "quality.yaml").read_text() + "\n# a changed rule is a changed version\n")
    (copy / "name-key.yaml").write_text((copy / "name-key.yaml").read_text() + "\nextra_rule: 1\n")
    assert changed_files.source_rules("gleif") != identity
