"""The rules files load as written."""

from __future__ import annotations

import pytest

from edgar_warehouse.mdm import gleif_publication
from edgar_warehouse.mdm.store import canonical
from edgar_warehouse.rules import files


def test_a_gleif_relationship_points_at_the_level1_source_it_is_given():
    contract = gleif_publication.dataset_contract("relationships", level1_source="x.level1")
    assert [r["target_source"] for r in contract["adapter"]["relationships"]] == ["x.level1"]
    assert [r["source_source"] for r in contract["adapter"]["relationships"]] == ["x.level1"]
    # A fresh copy each call: the substitution never leaks into the next caller.
    contract = gleif_publication.dataset_contract("relationships")
    assert "x.level1" not in {r["target_source"] for r in contract["adapter"]["relationships"]}


def test_an_unknown_gleif_member_is_refused():
    with pytest.raises(ValueError, match="Unknown GLEIF member"):
        gleif_publication.dataset_contract("level2")


@pytest.mark.parametrize(
    "path",
    sorted(p.relative_to(files.ROOT).as_posix() for p in files.ROOT.rglob("*.yaml")),
)
def test_every_rules_file_round_trips_exactly(path):
    value = files.load(files.ROOT / path)
    assert canonical(files.loads(files.dumps(value))) == canonical(value)
