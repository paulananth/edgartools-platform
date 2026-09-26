"""Regression checks for the prototype XML-root change and 13F contract."""
from pathlib import Path

import pytest

from source_engine import Engine, prove, read_artifact


@pytest.mark.parametrize("expected", ["informationTable", "{urn:test}informationTable"])
def test_root_accepts_local_and_expanded_names(expected):
    assert read_artifact({"format": "xml", "root": expected},
                         b'<informationTable xmlns="urn:test"><infoTable/></informationTable>')


def test_root_still_rejects_a_different_document():
    assert read_artifact({"format": "xml", "root": "informationTable"}, b"<other/>") == []
    assert read_artifact({"format": "xml", "root": "{urn:other}informationTable"},
                         b'<informationTable xmlns="urn:test"/>') == []


def test_thirteenf_named_case():
    engine = Engine(Path(__file__).resolve().parents[1] / "sources/thirteenf", {})
    result = prove(engine, gate=False, bronze_root=None)
    assert not result["failures"], result
