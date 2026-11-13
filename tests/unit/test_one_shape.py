"""Every load target has one shape, and it expands to the steps the engine runs."""
import json
from pathlib import Path

import pytest

from edgar_warehouse.rules import files, shape

# The steps of every target, recorded once from the hand-written step lists.
STEPS = json.loads(Path(__file__).with_name("load_target_steps.json").read_text())
SOURCES = sorted(path.parent.name for path in (files.ROOT / "sources").glob("*/source.yaml"))


def targets():
    return {f"{name}/{target}": body for name in SOURCES
            for target, body in (files.source(name).get("bookkeeping", {}).get("targets") or {}).items()}


def test_every_target_is_recorded():
    assert sorted(targets()) == sorted(STEPS)


@pytest.mark.parametrize("name", sorted(STEPS))
def test_a_target_gives_its_recorded_steps(name):
    assert targets()[name] == STEPS[name]


@pytest.mark.parametrize("name", sorted(STEPS))
def test_the_rules_version_holds_the_steps_not_how_they_are_written(name):
    # The processing identity is taken from this: a target written in the one shape must not load its files again.
    from edgar_warehouse.mdm import changed_files

    source, target = name.split("/")
    assert changed_files.source_rules(source)["source.yaml"]["bookkeeping"]["targets"][target] == STEPS[name]


def test_a_target_says_extract_master_and_silver_and_gets_every_step():
    target = shape.expand({
        "extract": {"dates": {"read": "dates.yaml", "units": {"each": "file"}},
                    "read": {"read": "fields.yaml", "files": "*.json", "lookups": {"filed": {"from": "dates", "table": "t"}}},
                    "joined": {"combine": "join.yaml", "readings": {"a": {"step": "read"}, "d": {"all": "dates"}}},
                    "record": "record.yaml"},
        "master": {"keys": {"table": "t", "dataset": "invented.v1"}},
        "silver": [{"name": "land_a", "land": {"table": "a", "silver": "a"}, "requires": ["read", "merge"]},
                   {"name": "land_b", "land": {"table": "b", "silver": "b"}, "requires": ["read", "merge"]}]})

    steps = target["steps"]
    assert [(s["name"], s["operation"], s["requires"]) for s in steps] == [
        ("dates", "source.read", []),
        ("read", "source.read", ["dates"]),                 # it waits for the pass its lookup reads
        ("joined", "source.combine", ["read", "dates"]),    # and a join for the passes it joins, in its order
        ("record", "source.read", ["joined"]),              # a rules file alone reads the pass before it
        ("prepare", "mdm.prepare", ["record"]), ("merge", "mastering.merge", ["prepare"]),
        ("land_a", "silver.land", ["read", "merge"]), ("land_b", "silver.land", ["read", "merge"]),
        ("processed", "journal.record", ["land_a", "land_b"])]  # the record waits for every step nothing waits for
    assert steps[0]["input"] == {"contract": "dates.yaml"} and steps[0]["units"] == {"each": "file"}
    assert steps[3]["input"] == {"contract": "record.yaml", "pieces": {"step": "joined"}}
    assert steps[4]["input"]["readings"] == {"record": {"all": "record"}}  # mastering reads the last pass whole
    assert steps[5] == {"name": "merge", "operation": "mastering.merge", "requires": ["prepare"], "key": "{batch_id}",
                        "leases": ["mdm:consumer:{consumer}"], "checks": ["input.hash", "output.receipt", "mdm.committed"]}
    assert steps[6]["leases"] == ["silver:{silver}:{unit}"]  # a landing unit leases its own part: units land side by side
    assert target["checks"] == ["manifest.hash", "work.accounting", "journal.delivered"]


def test_mastering_reads_what_it_names():
    steps = shape.expand({"extract": {"main": {"read": None}, "joined": {"combine": "j.yaml", "readings": {"m": {"step": "main"}}}},
                          "master": {"keys": {}, "readings": {"combined": {"all": "joined"}}}})["steps"]
    assert steps[2]["input"]["readings"] == {"combined": {"all": "joined"}}


def test_a_silver_only_target_masters_nothing():
    steps = shape.expand({"extract": {"read": {"read": None}},
                          "silver": [{"name": "land", "land": {"table": "t", "silver": "t"}},
                                     {"name": "built", "derive": {"build": "b", "silver": "s", "reads": "t"}}]})["steps"]
    assert [(s["name"], s["requires"]) for s in steps] == [
        ("read", []), ("land", ["read"]), ("built", ["land"]), ("processed", ["built"])]
    assert "input" not in steps[0]


@pytest.mark.parametrize("target", [
    {"extract": {"read": {"read": None}}, "steps": []},                          # both ways of writing a target
    {"extract": {}},                                                               # nothing extracted
    {"extract": [{"name": "read", "read": None}]},                                # a list, not passes by name
    {"extract": {"read": {}}},                                                    # neither read nor combine
    {"extract": {"read": {"read": None, "combine": None}}},                      # both
    {"extract": {"read": "record.yaml"}},                                         # a rules file alone, with no pass before it
    {"extract": {"a": {"read": None}, "b": {"read": None, "requires": ["a"]}}},  # a wait written by hand
    {"extract": {"read": {"read": None}}, "master": {"readings": {}}},           # no keys
    {"extract": {"read": {"read": None}}, "silver": [{"name": "x", "land": {}, "extra": 1}]},
])
def test_a_target_outside_the_shape_is_refused(target):
    with pytest.raises(shape.ShapeError):
        shape.expand(target)


def rules_folder(tmp_path, **documents):
    folder = tmp_path / "invented.source"
    folder.mkdir()
    for name, body in documents.items():
        (folder / f"{name.replace('_', '-')}.yaml").write_text(files.dumps(body))
    return folder


def test_a_target_names_its_last_rules_file_and_the_passes_follow(tmp_path):
    folder = rules_folder(
        tmp_path,
        source={"pass": {"name": "rows", "files": "*.json", "units": {"each": "file"},
                         "lookups": {"filed": {"from": "dates.yaml", "table": "t"}}}},
        dates={"pass": {"units": {"each": "file"}}},
        row_counts={"pass": {"readings": {"rows": {"all": "source.yaml"}}}},
        join={"pass": {"name": "joined", "readings": {"counts": {"step": "row-counts.yaml"}, "rows": {"all": "source.yaml"}}}},
        record={"pass": {"pieces": {"step": "join.yaml"}}})

    steps = shape.expand({"extract": "record.yaml", "master": {"keys": {"table": "t", "dataset": "invented.v1"}}}, folder)["steps"]

    assert [(s["name"], s["operation"], s["requires"]) for s in steps] == [
        ("dates", "source.read", []),                           # each pass after the passes it reads
        ("rows", "source.read", ["dates"]),                     # the source's own file: named by its block
        ("row_counts", "source.combine", ["rows"]),             # a pass is named after its file
        ("joined", "source.combine", ["row_counts", "rows"]),
        ("record", "source.read", ["joined"]),
        ("prepare", "mdm.prepare", ["record"]), ("merge", "mastering.merge", ["prepare"]),
        ("processed", "journal.record", ["merge"])]
    assert steps[1]["input"] == {"files": "*.json", "lookups": {"filed": {"from": "dates", "table": "t"}}}  # no contract: its own file
    assert steps[3]["input"] == {"contract": "join.yaml", "readings": {"counts": {"step": "row_counts"}, "rows": {"all": "rows"}}}
    assert steps[4]["input"] == {"contract": "record.yaml", "pieces": {"step": "joined"}}


def test_a_rules_file_with_no_pass_block_is_refused(tmp_path):
    folder = rules_folder(tmp_path, record={"pass": {"pieces": {"step": "join.yaml"}}}, join={"combine": {}})
    with pytest.raises(shape.ShapeError, match="join.yaml has no `pass` block"):
        shape.expand({"extract": "record.yaml"}, folder)


def test_a_pass_names_the_rules_file_it_reads_not_a_pass(tmp_path):
    folder = rules_folder(tmp_path, record={"pass": {"pieces": {"step": "joined"}}})
    with pytest.raises(shape.ShapeError, match="names the rules file it reads"):
        shape.expand({"extract": "record.yaml"}, folder)


def test_the_engine_reads_a_rules_file_without_its_pass_block(tmp_path):
    folder = rules_folder(tmp_path, record={"pass": {"pieces": {"step": "join.yaml"}}, "read": {"format": "json"}})
    assert files.contract(folder / "record.yaml") == {"read": {"format": "json"}}


@pytest.mark.parametrize("kind, operation", [("copy", "artifact.copy"), ("provider", "provider.capture")])
def test_a_capture_target_is_its_one_step(kind, operation):
    target = shape.expand({"capture": kind, "lease_seconds": 300})
    assert [(s["name"], s["operation"]) for s in target["steps"]] == [("capture", operation)]
    assert target["lease_seconds"] == 300 and target["checks"] == ["manifest.hash", "work.accounting", "journal.delivered"]
    with pytest.raises(shape.ShapeError):
        shape.expand({"capture": "other"})


def test_a_second_pass_over_recorded_files_has_no_record_step():
    target = shape.expand({"extract": {"record": {"read": "record.yaml", "pieces": {"run": {"source": "s", "target": "t", "step": "c"}}}},
                           "master": {"keys": {}}, "record": False})
    assert [s["name"] for s in target["steps"]] == ["record", "prepare", "merge"]
    assert target["checks"] == ["manifest.hash", "work.accounting"]


def test_a_target_that_lists_its_steps_is_left_as_it_is():
    target = {"steps": [{"name": "capture"}], "checks": ["manifest.hash"]}
    assert shape.expand(target) is target
