"""Contract errors block before any database or destination mutation."""
from copy import deepcopy

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.capabilities import standard_registry
from edgar_warehouse.bookkeeping.clean.config import Blocked, validate, worklist
from edgar_warehouse.rules.files import source, pipeline


@pytest.mark.parametrize("edit", ["unknown", "cycle", "bad_key", "empty_lease", "duration", "unknown_check", "unknown_op",
                                 "checks_map", "duplicate_checks", "final_checks_map", "broken_template"])
def test_invalid_configuration(edit):
    body = deepcopy(source("sec.submissions.company"))
    target = body["bookkeeping"]["targets"]["capture"]
    step = target["steps"][0]
    if edit == "unknown":
        target["ignored"] = True
    elif edit == "cycle":
        step["requires"] = ["capture"]
    elif edit == "bad_key":
        step["key"] = "{object.__class__}"
    elif edit == "empty_lease":
        step["leases"] = []
    elif edit == "duration":
        target["lease_seconds"] = 30
        target["heartbeat_seconds"] = 30
    elif edit == "unknown_check":
        step["checks"] = ["assume.success"]
    elif edit == "checks_map":
        step["checks"] = {"input.hash": False}
    elif edit == "duplicate_checks":
        step["checks"] = ["input.hash", "input.hash"]
    elif edit == "final_checks_map":
        target["checks"] = {"manifest.hash": False}
    elif edit == "broken_template":
        step["key"] = "{unclosed"
    else:
        step["operation"] = "unknown.stage"
    with pytest.raises(Blocked):
        validate(body, "capture", standard_registry())


def test_manifest_duplicates_missing_references_and_template_fields():
    selected = validate(source("sec.submissions.company"), "capture", standard_registry())
    unit = {"keys": {"artifact_id": "one", "destination": "s3://bucket/key"},
            "input": {"uri": "s3://bucket/source", "sha256": "a"*64}, "output": "s3://bucket/key", "cursor": 0}
    for units in ([unit, unit], [{**unit, "keys": {}}], [{**unit, "input": {"uri": "missing-hash"}}], [{**unit, "business_rows": []}]):
        with pytest.raises(Blocked):
            worklist({"version": 1, "units": units}, selected)


def test_control_artifacts_are_immutable_atomic_and_digest_checked(tmp_path):
    artifacts = Artifacts()
    reference = artifacts.put(tmp_path.as_uri(), {"version": 1, "units": []})
    assert artifacts.put(tmp_path.as_uri(), {"units": [], "version": 1}) == reference
    assert not list(tmp_path.glob(".bookkeeping-*"))
    with pytest.raises(Blocked):
        artifacts.put_bytes(reference["uri"], b"conflicting bytes")
    assert artifacts.json(reference) == {"version": 1, "units": []}


def test_offline_artifact_uris_preserve_encoded_path_characters(tmp_path):
    artifacts = Artifacts()
    source = tmp_path / "a space and % sign" / "input.json"
    source.parent.mkdir()
    source.write_bytes(b'{"version":1}')
    assert artifacts.read(source.as_uri()) == source.read_bytes()
    output = source.parent / "output.json"
    ref = artifacts.put_bytes(output.as_uri(), source.read_bytes())
    assert output.read_bytes() == source.read_bytes() and artifacts.json(ref) == {"version": 1}


@pytest.mark.parametrize("payload", [b'{"version":1,"version":2}', b'{"bad":NaN}', b'{"bad":1e999}', b'[]'])
def test_corrupt_json_control_documents(tmp_path, payload):
    artifacts = Artifacts()
    ref = artifacts.put_bytes((tmp_path / "bad.json").as_uri(), payload)
    with pytest.raises(Blocked):
        artifacts.json(ref)


def test_cli_commands_remain_available_and_resume_is_bounded():
    from edgar_warehouse.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["rules", "run", "--pipeline", "graph-publication", "--target", "publish", "--resume-run-id", "original"])
    assert args.resume_run_id == "original" and args.limit == 100
    assert parser.parse_args(["bookkeeping", "leases", "original"]).limit == 100
    # The legacy warehouse commands are deleted (platform validation slice 2a).
    with pytest.raises(SystemExit):
        parser.parse_args(["gold-refresh"])
    assert pipeline("graph-publication")["pipeline"] == "graph-publication"


def stage_manifest():
    selected = validate(source("sec.submissions.company"), "capture", standard_registry())
    selected["steps"] = [
        {**selected["steps"][0], "name": "capture", "requires": [], "key": "{artifact_id}"},
        {**selected["steps"][0], "name": "parse", "requires": ["capture"], "key": "{artifact_id}"},
    ]
    unit = {"keys": {"artifact_id": "one", "destination": "s3://bucket/capture"},
            "input": {"uri": "s3://bucket/source", "sha256": "a"*64},
            "output": "s3://bucket/capture", "cursor": 0}
    dependent = {**unit, "input": {"from": {"step": "capture", "key": "one"}},
                 "keys": {"artifact_id": "parsed", "destination": "s3://bucket/parse"},
                 "output": "s3://bucket/parse"}
    return selected, {"version": 2, "steps": {"capture": [unit], "parse": [dependent]}}


def test_stage_worklists_preserve_distinct_scope_and_inputs():
    config, manifest = stage_manifest()
    manifest["steps"]["parse"].append({**manifest["steps"]["parse"][0],
        "keys": {"artifact_id": "second", "destination": "s3://bucket/second"},
        "output": "s3://bucket/second"})
    items = worklist(manifest, config)
    assert [(i["step"], i["key"], i["ordinal"]) for i in items] == [
        ("capture", "one", 0), ("parse", "parsed", 0), ("parse", "second", 1)]
    assert items[1]["unit"]["input"] == {"from": {"step": "capture", "key": "one"}}
    assert items[1]["resources"] == ["artifact:s3://bucket/parse"]


@pytest.mark.parametrize("edit", ["unknown_stage", "missing_stage", "stage_not_list", "unknown_unit",
    "unknown_input", "missing_unit", "undeclared_dependency", "forward_dependency", "mixed_reference",
    "bad_dependency", "empty_stage", "duplicate_unit", "v1_selector", "bad_version"])
def test_invalid_stage_scope_blocks_before_execution(edit):
    config, manifest = stage_manifest()
    dependent = manifest["steps"]["parse"][0]
    if edit == "unknown_stage":
        manifest["steps"]["extra"] = []
    elif edit == "missing_stage":
        del manifest["steps"]["capture"]
    elif edit == "stage_not_list":
        manifest["steps"]["capture"] = {}
    elif edit == "unknown_unit":
        dependent["rows"] = []
    elif edit == "unknown_input":
        dependent["input"] = {"guess_latest": True}
    elif edit == "missing_unit":
        dependent["input"]["from"]["key"] = "missing"
    elif edit == "undeclared_dependency":
        config["steps"][1]["requires"] = []
    elif edit == "forward_dependency":
        manifest["steps"]["capture"][0]["input"] = {"from": {"step": "parse", "key": "parsed"}}
    elif edit == "mixed_reference":
        dependent["input"]["uri"] = "s3://bucket/guess"
    elif edit == "bad_dependency":
        dependent["input"]["from"] = {"step": "capture", "key": []}
    elif edit == "empty_stage":
        manifest["steps"]["parse"] = []
    elif edit == "duplicate_unit":
        manifest["steps"]["parse"].append(dependent)
    elif edit == "v1_selector":
        manifest = {"version": 1, "units": [dependent]}
    else:
        manifest["version"] = True
    with pytest.raises(Blocked):
        worklist(manifest, config)


def test_version_one_worklist_remains_identical_for_frozen_runs():
    config, manifest = stage_manifest()
    unit = manifest["steps"]["capture"][0]
    assert worklist({"version": 1, "units": [unit]}, config) == [
        {"step": name, "key": "one", "ordinal": 0, "resources": ["artifact:s3://bucket/capture"], "unit": unit}
        for name in ("capture", "parse")]


def test_empty_stage_requires_explicit_configuration_even_with_other_work():
    config, manifest = stage_manifest()
    config["allow_zero_work"] = True
    manifest["steps"]["parse"] = []
    assert len(worklist(manifest, config)) == 1
    manifest["steps"]["capture"] = []
    assert worklist(manifest, config) == []
