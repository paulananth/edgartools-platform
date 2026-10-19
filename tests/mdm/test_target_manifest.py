"""One writer builds a declared target's input manifest (ticket 14, slice 2), from
the source's Bookkeeping section version 2."""
import json

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.config import Blocked, validate
from edgar_warehouse.mdm.clean.target_manifest import write_manifest
from edgar_warehouse.rules import files
from tests.support.memory_journal import MemoryJournal
from tests.support.sec_capture import document, key, person, write_capture

SOURCE = "sec.submissions.person"
DOCUMENTS = {1001: person(1001, "DOE JOHN"), 1002: person(1002, "ROE JANE"),
             320193: document(320193, "EXAMPLE INC")}


def options(tmp_path, **changes):
    folder, _ = write_capture(tmp_path / "capture", DOCUMENTS)
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps([key(cik) for cik in DOCUMENTS]))
    return {"source": SOURCE, "capture": str(folder), "documents": str(listed), "capture_run": "capture-1",
            "output": str(tmp_path / "bundle"), "as_of": "2026-10-18T00:00:00Z", "revision": 0,
            "journal": MemoryJournal(), **changes}


def captured(tmp_path):
    """Each document's reference in the capture, in key order."""
    return [(tmp_path / "capture" / "bronze" / key(cik).removeprefix("warehouse/bronze/")).as_uri()
            for cik in sorted(DOCUMENTS, key=key)]


def steps_of(report):
    return Artifacts().json(report["manifest"])["steps"]


def test_the_declared_writer_builds_persons_mastering_manifest(tmp_path):
    report = write_manifest(target="mastering", **options(tmp_path))
    steps = steps_of(report)

    assert {name: len(units) for name, units in steps.items()} == {"read": 1, "records": 1, "merge": 1, "processed": 1}
    read = Artifacts().json(steps["read"][0]["input"])
    assert [a["uri"] for a in read["artifacts"]] == captured(tmp_path)
    assert Artifacts().json(read["contract"]) == files.load(files.ROOT / "sources" / SOURCE / "source.yaml")
    records = steps["records"][0]
    assert {k: records["keys"][k] for k in ("table", "record_column", "dataset", "revision")} == {
        "table": "submissions", "record_column": "record", "dataset": "sec.submissions.person.v1", "revision": "0"}
    assert records["input"]["compose"]["slots"] == {"read": [{"step": "read", "key": "read-0"}]}
    assert steps["merge"][0]["input"] == {"from": {"step": "records", "key": "records"}}
    assert steps["merge"][0]["keys"] == {"batch_id": report["publication"]["batch_id"],
                                         "consumer": report["publication"]["consumer"]}
    assert len(Artifacts().json(steps["processed"][0]["input"])["files"]) == len(DOCUMENTS)


def test_the_engine_sees_version_one_steps():
    steps = validate(files.source(SOURCE), "mastering")["steps"]

    assert all(set(step) == {"name", "operation", "requires", "key", "leases", "checks"} for step in steps)


@pytest.mark.parametrize("plan, words", [
    ({"units": {"slices": {"bytes": 0}}}, "slices name their bytes"),
    ({"units": {"groups": 17}}, "groups hold 1..16"),
    ({"units": {"every": 2}}, "units are one"),
    ({"input": {"other": 1}}, "pieces and references only"),
    ({"units": {"each": "folder"}}, "each file"),
    ({"input": {"files": "../x"}}, "pattern over the bundle"),
    ({"input": {"beside": {"path": "{stem}.json", "sha256": "request_sha256"}}}, "template path"),
    ({"input": {"context": {"batch": "{stem}"}}}, "templates over"),
    ({"input": {"lookups": {"asked": {"from": "nothing"}}}}, "same file's unit"),
    ({"input": {"pieces": {"step": "nothing"}}}, "pieces name one prerequisite"),
    ({"input": {"readings": {"read": {"all": "nothing"}}}}, "one prerequisite step"),
])
def test_a_plan_the_engine_cannot_run_is_refused(plan, words):
    body = files.source(SOURCE)
    body["bookkeeping"]["targets"]["mastering"]["steps"][1].update(plan)

    with pytest.raises(Blocked, match=words):
        validate(body, "mastering")


def test_a_version_one_section_runs_but_states_no_plan(tmp_path, monkeypatch):
    body = files.source(SOURCE)
    body["bookkeeping"]["version"] = 1
    with pytest.raises(Blocked, match="A step requires name, operation"):
        validate(body, "mastering")  # version 1 holds no units or input
    for step in body["bookkeeping"]["targets"]["mastering"]["steps"]:
        step.pop("units", None), step.pop("input", None)
    assert len(validate(body, "mastering")["steps"]) == 4
    monkeypatch.setattr(files, "source", lambda name, root=None: body)

    with pytest.raises(ValueError, match="must be version 2"):
        write_manifest(target="mastering", **options(tmp_path))


def test_units_on_a_step_that_reads_no_captured_documents_are_refused(tmp_path, monkeypatch):
    body = files.source(SOURCE)
    body["bookkeeping"]["targets"]["mastering"]["steps"][1]["units"] = {"groups": 4}
    monkeypatch.setattr(files, "source", lambda name, root=None: body)

    with pytest.raises(ValueError, match="only a read declares its units"):
        write_manifest(target="mastering", **options(tmp_path))


def test_a_record_column_the_reading_does_not_declare_is_refused(tmp_path, monkeypatch):
    body = files.source(SOURCE)
    body["bookkeeping"]["targets"]["mastering"]["steps"][1]["input"]["keys"]["record_column"] = "other"
    monkeypatch.setattr(files, "source", lambda name, root=None: body)

    with pytest.raises(ValueError, match="not declared by the reading"):
        write_manifest(target="mastering", **options(tmp_path))


def test_the_declared_slices_cut_the_read_units(tmp_path, monkeypatch):
    body = files.source(SOURCE)
    body["bookkeeping"]["targets"]["mastering"]["steps"][0]["units"] = {"slices": {"bytes": 2000}}
    monkeypatch.setattr(files, "source", lambda name, root=None: body)
    steps = steps_of(write_manifest(target="mastering", **options(tmp_path)))

    read = [[a["uri"] for a in Artifacts().json(unit["input"])["artifacts"]] for unit in steps["read"]]
    assert len(read) > 1 and sum(read, []) == captured(tmp_path)
    assert [u["keys"]["unit"] for u in steps["read"]] == [s["key"] for s in steps["records"][0]["input"]["compose"]["slots"]["read"]]


def test_a_source_whose_section_states_no_plan_is_refused(tmp_path):
    with pytest.raises(ValueError, match="must be version 2"):  # SEC Company keeps its own writer for now
        write_manifest(target="mastering", **options(tmp_path, source="sec.submissions.company"))


def test_an_edit_to_a_declared_contract_is_a_new_consumer(tmp_path, monkeypatch):
    first = write_manifest(target="mastering", **options(tmp_path / "a"))
    load = files.load

    def edited(path, *args, **kwargs):
        body = load(path, *args, **kwargs)
        return {**body, "note": "edited"} if path.name == "source.yaml" and SOURCE in str(path) else body
    monkeypatch.setattr(files, "load", edited)
    second = write_manifest(target="mastering", **options(tmp_path / "b"))

    assert second["publication"]["consumer"] != first["publication"]["consumer"]
    assert second["publication"]["batch_id"] != first["publication"]["batch_id"]
    frozen = Artifacts().json(Artifacts().json(steps_of(second)["read"][0]["input"])["contract"])
    assert frozen["note"] == "edited"  # the ids digest the contract that is frozen


def test_a_second_declared_contract_is_digested_too(tmp_path, monkeypatch):
    body = files.source(SOURCE)
    body["bookkeeping"]["targets"]["mastering"]["steps"][1]["input"]["contract"] = "quality.yaml"
    monkeypatch.setattr(files, "source", lambda name, root=None: body)
    first = write_manifest(target="mastering", **options(tmp_path / "a"))
    load = files.load
    monkeypatch.setattr(files, "load", lambda path, *a, **k: (
        {**load(path, *a, **k), "note": "edited"} if path.name == "quality.yaml" else load(path, *a, **k)))
    second = write_manifest(target="mastering", **options(tmp_path / "b"))

    assert second["publication"]["batch_id"] != first["publication"]["batch_id"]


class Runs:
    """Bookkeeping's verified units of another run's step (ticket 120), as given."""
    def __init__(self, units):
        self.units, self.asked = units, []

    def verified_units(self, **selector):
        self.asked.append(selector)
        return self.units


OTHER = {"source": "openfigi", "target": "answers_cusip", "step": "answers"}


def reading_another_run(monkeypatch, selector=OTHER):
    """Person's target with a combine that reads another source's run (ticket 120)."""
    body = files.source(SOURCE)
    body["bookkeeping"]["targets"]["mastering"]["steps"].insert(1, {
        "name": "others", "operation": "source.combine", "requires": [], "key": "{unit}",
        "leases": ["artifact:{destination}"], "checks": ["input.hash", "output.receipt", "source.combined"],
        "input": {"contract": "source.yaml", "readings": {"answers": {"run": selector}}}})
    monkeypatch.setattr(files, "source", lambda name, root=None: body)


def unit(run, key, sha):
    return {"run": run, "step": "answers", "key": key, "sha256": sha * 64}


def test_a_combine_reads_the_verified_units_of_another_runs_step(tmp_path, monkeypatch):
    reading_another_run(monkeypatch)
    runs = Runs([unit("11111111-1111-1111-1111-111111111111", "answers-0", "a"),
                 unit("22222222-2222-2222-2222-222222222222", "answers-0", "b")])
    first = write_manifest(target="mastering", bookkeeping=runs, **options(tmp_path / "a"))

    assert runs.asked == [OTHER]
    assert steps_of(first)["others"][0]["input"]["compose"]["slots"] == {"answers": [
        {k: u[k] for k in ("run", "step", "key")} for u in runs.units]}
    runs.units = runs.units[:1]
    second = write_manifest(target="mastering", bookkeeping=runs, **options(tmp_path / "b"))
    assert second["scope"]["processing_identity"] != first["scope"]["processing_identity"]  # its outputs are its identity
    assert second["publication"]["batch_id"] != first["publication"]["batch_id"]


@pytest.mark.parametrize("count", [0, 257])
def test_another_run_with_no_or_too_many_verified_units_is_refused(tmp_path, monkeypatch, count):
    reading_another_run(monkeypatch)
    runs = Runs([unit("11111111-1111-1111-1111-111111111111", f"answers-{n}", "a") for n in range(count)])
    with pytest.raises(ValueError, match=f"has {count} verified units"):
        write_manifest(target="mastering", bookkeeping=runs, **options(tmp_path))


@pytest.mark.parametrize("selector", [{"source": "openfigi", "target": "answers_cusip"},
                                      {**OTHER, "step": "Answers"}, {**OTHER, "extra": "x"}])
def test_a_reading_of_another_run_names_source_target_and_step(monkeypatch, selector):
    reading_another_run(monkeypatch, selector)
    with pytest.raises(Blocked, match="another run's step"):
        validate(files.source(SOURCE), "mastering")


def test_a_target_that_only_reads_has_no_publication_steps(tmp_path, monkeypatch):
    """Ticket 120: a target with no preparation reads and records its files, for another run to read."""
    body = files.source(SOURCE)
    steps = body["bookkeeping"]["targets"]["mastering"]["steps"]
    body["bookkeeping"]["targets"]["mastering"]["steps"] = [steps[0], {**steps[-1], "requires": [steps[0]["name"]]}]
    monkeypatch.setattr(files, "source", lambda name, root=None: body)
    report = write_manifest(target="mastering", **options(tmp_path))

    assert {name: len(units) for name, units in steps_of(report).items()} == {"read": 1, "processed": 1}
    assert report["source_code"] is None


def test_two_preparations_are_refused(tmp_path, monkeypatch):
    body = files.source(SOURCE)
    steps = body["bookkeeping"]["targets"]["mastering"]["steps"]
    steps.insert(2, {**steps[1], "name": "records_again"})
    monkeypatch.setattr(files, "source", lambda name, root=None: body)
    with pytest.raises(ValueError, match="at most one mdm.prepare"):
        write_manifest(target="mastering", **options(tmp_path))


def test_a_lookup_set_reads_another_runs_step_whole(tmp_path, monkeypatch):
    """Ticket 120: every file's lookup set is the other run's verified units, read whole."""
    body = files.source(SOURCE)
    read = body["bookkeeping"]["targets"]["mastering"]["steps"][0]
    read["units"] = {"each": "file"}
    read["input"] = {**read.get("input", {}), "lookups": {"umbrella": {
        "run": OTHER, "table": "pairs", "column": "fund", "value_column": "umbrella",
        "max_input_bytes": 1024, "max_input_rows": 10}}}
    monkeypatch.setattr(files, "source", lambda name, root=None: body)
    runs = Runs([unit("11111111-1111-1111-1111-111111111111", "answers-0", "a")])
    steps = steps_of(write_manifest(target="mastering", bookkeeping=runs, **options(tmp_path)))

    assert len(steps["read"]) == len(DOCUMENTS)
    for each in steps["read"]:
        (lookup,) = each["input"]["compose"]["slots"].values()
        assert lookup["compose"]["slots"] == {"umbrella": [{k: runs.units[0][k] for k in ("run", "step", "key")}]}
        assert lookup["compose"]["document"]["sets"]["umbrella"]["readings"] == {"slot": "umbrella"}


def test_two_targets_over_the_same_files_each_process_them(tmp_path, monkeypatch):
    """Ticket 120: a source's two Dataset Contracts read the same files through two targets; the target
    is part of the processing identity, so recording one never marks the files done for the other."""
    body = files.source(SOURCE)
    body["bookkeeping"]["targets"]["mastering_again"] = body["bookkeeping"]["targets"]["mastering"]
    monkeypatch.setattr(files, "source", lambda name, root=None: body)
    first = write_manifest(target="mastering", **options(tmp_path / "a"))
    second = write_manifest(target="mastering_again", **options(tmp_path / "b"))

    assert first["scope"]["processing_identity"] != second["scope"]["processing_identity"]
    assert first["publication"]["batch_id"] != second["publication"]["batch_id"]
