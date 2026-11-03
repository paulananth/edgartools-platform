"""A step's `bind` fills a run fact or a run file's digest into its contract before the contract is
frozen (ticket 177, slice 2): for a read and for a combine. Every name here is invented."""
import json
from copy import deepcopy

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean import target_manifest
from edgar_warehouse.mdm.clean.store import digest
from edgar_warehouse.rules import files
from tests.mdm import test_ownership_target as ownership
from tests.mdm import test_thirteenf_securities_target as thirteenf

NAME_COUNT = {"entries": [1, 2, 3], "version": 1}
TOKENS = {"APPROVED_RUN": {"fact": "approved_run"}, "NAME_COUNT_DIGEST": {"digest": "name_count"}}


def plan(monkeypatch, tmp_path, module, step_name, *, bind=TOKENS, facts=None, run=None, carries=("APPROVED_RUN", "NAME_COUNT_DIGEST")):
    """Plan a module's target with `bind` on one step; its contract carries the tokens."""
    real, real_load = files.source, files.load
    name_count = tmp_path / "name_count.json"
    name_count.write_text(json.dumps(NAME_COUNT))

    def source(name, *args, **kwargs):
        reading = deepcopy(real(name, *args, **kwargs))
        if name == module.SOURCE:
            target = reading["bookkeeping"]["targets"]["mastering"]
            target["run"] = run if run is not None else {"facts": ["approved_run"], "files": ["name_count"]}
            step = next(s for s in target["steps"] if s["name"] == step_name)
            step.setdefault("input", {})["bind"] = bind
        return reading

    def load(path, *args, **kwargs):
        body = deepcopy(real_load(path, *args, **kwargs))
        if str(path).endswith(contract_name(module, step_name)):
            body["tokens"] = list(carries)
        return body
    monkeypatch.setattr(target_manifest.rules_files, "source", source)
    monkeypatch.setattr(target_manifest.rules_files, "load", load)
    options = module.capture(tmp_path, [1])
    return target_manifest.write_manifest(
        **options, facts={"approved_run": "run-7"} if facts is None else facts, run_files={"name_count": str(name_count)})


def contract_name(module, step_name):
    return {"read": "ownership-sgml.yaml", "reduce": "reduce.yaml"}[step_name]


def stored_contract(report, step_name, read):
    store = Artifacts()
    (unit,) = store.json(report["manifest"])["steps"][step_name]
    source = unit["input"]
    document = store.json(source) if read else source["compose"]["document"]
    return store.json(document["contract"])


def test_a_read_contract_carries_the_fact_and_the_run_files_digest(monkeypatch, tmp_path):
    report = plan(monkeypatch, tmp_path, ownership, "read")
    assert stored_contract(report, "read", True)["tokens"] == ["run-7", digest(NAME_COUNT)]


def test_a_combine_contract_carries_them_too(monkeypatch, tmp_path):
    report = plan(monkeypatch, tmp_path, thirteenf, "reduce")
    assert stored_contract(report, "reduce", False)["tokens"] == ["run-7", digest(NAME_COUNT)]


@pytest.mark.parametrize("kwargs, message", [
    ({"carries": ("APPROVED_RUN",)}, "carries no"),                      # a stale token
    ({"facts": {"approved_run": 7}}, "takes text"),                         # a fact that is not text
    ({"run": {"facts": [], "files": ["name_count"]}, "facts": {}}, "not in the target's run"),   # an undeclared fact
    ({"run": {"facts": ["approved_run"], "files": []}}, "not in the target's run|run takes"),  # an undeclared file
    ({"bind": {"APPROVED_RUN": {"fact": 3}}}, "bind maps a token"),         # a malformed reference
])
def test_a_bad_bind_is_refused(monkeypatch, tmp_path, kwargs, message):
    with pytest.raises(Exception, match=message):
        plan(monkeypatch, tmp_path, ownership, "read", **kwargs)
