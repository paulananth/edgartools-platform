"""A step's `bind` fills a run fact or a run file's digest into its contract before the contract is
frozen (ticket 177, slice 2): for a read and for a combine. Every name here is invented."""
import hashlib
import json
from pathlib import Path
from copy import deepcopy

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm import target_manifest
from edgar_warehouse.mdm.store import canonical, digest
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


def runfile_plan(monkeypatch, tmp_path, *, run=None, runfile="name_count", extra=None):
    """The ownership read step reads a run file as its one document (ticket 177, slice 5)."""
    real = files.source

    def source(name, *args, **kwargs):
        reading = deepcopy(real(name, *args, **kwargs))
        if name == ownership.SOURCE:
            target = reading["bookkeeping"]["targets"]["mastering"]
            target["run"] = run if run is not None else {"facts": [], "files": ["name_count"]}
            step = next(s for s in target["steps"] if s["name"] == "read")
            step["units"] = "one"
            step["input"] = {k: v for k, v in step.get("input", {}).items() if k in ("contract", "bind")}
            step["input"]["runfile"] = runfile
            step["input"].update(extra or {})
        return reading
    monkeypatch.setattr(target_manifest.rules_files, "source", source)
    path = tmp_path / "name_count.json"
    path.write_text(json.dumps(NAME_COUNT))
    options = ownership.capture(tmp_path, [1])
    return target_manifest.write_manifest(**options, facts={}, run_files={"name_count": str(path)})


def test_a_read_may_take_a_run_file_as_its_one_document(monkeypatch, tmp_path):
    report = runfile_plan(monkeypatch, tmp_path)
    store = Artifacts()
    (unit,) = store.json(report["manifest"])["steps"]["read"]
    (artifact,) = store.json(unit["input"])["artifacts"]
    document = artifact.get("input", artifact)
    assert document["sha256"] == hashlib.sha256(canonical(NAME_COUNT).encode()).hexdigest()


@pytest.mark.parametrize("kwargs, message", [
    ({"run": {"facts": [], "files": []}}, "run takes|not in the target's run"),   # an undeclared file
    ({"runfile": 3}, "runfile names"),                                            # not a name
    ({"extra": {"files": "*.xml"}}, "runfile"),                                   # with a document glob
])
def test_a_bad_runfile_is_refused(monkeypatch, tmp_path, kwargs, message):
    with pytest.raises(Exception, match=message):
        runfile_plan(monkeypatch, tmp_path, **kwargs)


def context_plan(monkeypatch, tmp_path, context):
    """The ownership read step with the given context values (ticket 177, slice 5b)."""
    real = files.source

    def source(name, *args, **kwargs):
        reading = deepcopy(real(name, *args, **kwargs))
        if name == ownership.SOURCE:
            step = next(s for s in reading["bookkeeping"]["targets"]["mastering"]["steps"] if s["name"] == "read")
            step["input"]["context"] = context
        return reading
    monkeypatch.setattr(target_manifest.rules_files, "source", source)
    report = target_manifest.write_manifest(**ownership.capture(tmp_path, [1]), facts={}, run_files={})
    store = Artifacts()
    (unit,) = store.json(report["manifest"])["steps"]["read"]
    (artifact,) = store.json(unit["input"])["artifacts"]
    return store.json(artifact["context"])["values"]


def test_a_context_value_may_be_a_folder_segment_of_the_key(monkeypatch, tmp_path):
    values = context_plan(monkeypatch, tmp_path, {"accession_number": {"segment": "accession"}})
    assert values == {"accession_number": "0000000042-26-000001"}


def test_a_folder_segment_is_filled_as_text_or_as_an_integer():
    from edgar_warehouse.mdm import read_units
    key = "bronze/cik=320193/year=2026/doc.json"
    assert read_units.fill({"segment": "cik"}, key) == "320193"
    assert read_units.fill({"segment": "cik", "as": "integer"}, key) == 320193
    with pytest.raises(ValueError, match="no segment"):
        read_units.fill({"segment": "month"}, key)


def test_a_segment_must_fit_the_contracts_type(monkeypatch, tmp_path):
    with pytest.raises(Exception, match="is integer, but the contract's accession_number is text"):
        context_plan(monkeypatch, tmp_path, {"accession_number": {"segment": "accession", "as": "integer"}})


@pytest.mark.parametrize("value", [{"segment": 3}, {"segment": "accession", "as": "float"}, {"segment": "a", "x": 1}])
def test_a_bad_segment_is_refused(monkeypatch, tmp_path, value):
    with pytest.raises(Exception, match="segment"):
        context_plan(monkeypatch, tmp_path, {"accession_number": value})


def test_a_context_value_may_be_null_where_the_contract_allows(monkeypatch, tmp_path):
    values = context_plan(monkeypatch, tmp_path, {"accession_number": {"segment": "accession"}, "filed": None})
    assert values["filed"] is None
    with pytest.raises(Exception, match="does not take null"):
        context_plan(monkeypatch, tmp_path / "x", {"accession_number": None})


def matched_plan(monkeypatch, tmp_path, body, matches=None):
    """A target whose run file must name this capture: `run.matches` (ticket 177, slice 5d)."""
    real = files.source

    def source(name, *args, **kwargs):
        reading = deepcopy(real(name, *args, **kwargs))
        if name == ownership.SOURCE:
            reading["bookkeeping"]["targets"]["mastering"]["run"] = {
                "facts": [], "files": ["name_count"],
                "matches": matches if matches is not None else [
                    {"file": "name_count", "path": "sec.receipts_sha256", "to": "receipts_sha256"}]}
        return reading
    monkeypatch.setattr(target_manifest.rules_files, "source", source)
    options = ownership.capture(tmp_path, [1])
    receipts = hashlib.sha256((Path(options["capture"]) / "receipts.jsonl").read_bytes()).hexdigest()
    path = tmp_path / "name_count.json"
    path.write_text(json.dumps(body(receipts)))
    return target_manifest.write_manifest(**options, facts={}, run_files={"name_count": str(path)})


def test_a_run_file_that_names_this_capture_is_accepted(monkeypatch, tmp_path):
    report = matched_plan(monkeypatch, tmp_path, lambda receipts: {"sec": {"receipts_sha256": receipts}})
    assert report["manifest"]


def test_a_run_file_built_from_another_capture_is_refused(monkeypatch, tmp_path):
    with pytest.raises(Exception, match="name_count did not count this capture"):
        matched_plan(monkeypatch, tmp_path, lambda receipts: {"sec": {"receipts_sha256": "0" * 64}})


def test_a_run_file_without_the_matched_part_is_refused(monkeypatch, tmp_path):
    with pytest.raises(Exception, match="name_count did not count this capture"):
        matched_plan(monkeypatch, tmp_path, lambda receipts: {"other": 1})


@pytest.mark.parametrize("matches", [
    [{"file": "other", "path": "a", "to": "receipts_sha256"}],               # a file the run does not declare
    [{"file": "name_count", "path": "a", "to": "something"}],                # not a known property
    [{"file": "name_count", "path": "", "to": "receipts_sha256"}],           # no path
    [{"file": "name_count", "path": "a"}],                                    # no property
])
def test_a_bad_match_is_refused(monkeypatch, tmp_path, matches):
    with pytest.raises(Exception, match="matches"):
        matched_plan(monkeypatch, tmp_path, lambda receipts: {"a": 1}, matches)
