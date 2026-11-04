"""A preparation may name `distinct_on` (an entity named in many rows of one file is one record of it);
no other optional key yet. Every name here is invented."""
from copy import deepcopy

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm import target_manifest
from edgar_warehouse.rules import files
from tests.mdm.test_ownership_target import SOURCE, capture


def plan(monkeypatch, tmp_path, keys):
    real = files.source

    def changed(name, *args, **kwargs):
        reading = deepcopy(real(name, *args, **kwargs))
        if name == SOURCE:
            steps = reading["bookkeeping"]["targets"]["mastering"]["steps"]
            next(s for s in steps if s["operation"] == "mdm.prepare")["input"]["keys"].update(keys)
        return reading
    monkeypatch.setattr(target_manifest.rules_files, "source", changed)
    return target_manifest.write_manifest(**capture(tmp_path, [1]))


def test_distinct_on_reaches_the_preparation_unit(monkeypatch, tmp_path):
    report = plan(monkeypatch, tmp_path, {"distinct_on": ["rpt_owner_cik"]})
    (prepare,) = Artifacts().json(report["manifest"])["steps"]["prepare"]
    assert prepare["keys"]["distinct_on"] == ["rpt_owner_cik"]


@pytest.mark.parametrize("keys", [{"distinct_on": []}, {"distinct_on": ["a", "a"]}, {"distinct_on": "a"},
                                  {"distinct_on": [1]}])
def test_a_bad_distinct_on_is_refused(monkeypatch, tmp_path, keys):
    with pytest.raises(Exception, match="keys"):
        plan(monkeypatch, tmp_path, keys)


def test_another_optional_key_is_refused_until_a_ruled_need_asks_for_it(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="mdm.prepare step's keys"):
        plan(monkeypatch, tmp_path, {"effective_column": "filed"})
