"""One writer builds a declared target's input manifest (ticket 14, slice 2), from
the source's Bookkeeping section version 2."""
import json

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.config import Blocked, validate
from edgar_warehouse.mdm.target_manifest import write_manifest
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
    assert Artifacts().json(read["contract"]) == files.contract(files.ROOT / "sources" / SOURCE / "source.yaml")
    records = steps["records"][0]
    assert {k: records["keys"][k] for k in ("table", "record_column", "dataset", "revision")} == {
        "table": "submissions", "record_column": "record", "dataset": "sec.submissions.person.v1", "revision": "0"}
    assert records["input"]["compose"]["slots"] == {"read": [{"step": "read", "key": "read-0"}]}
    assert steps["merge"][0]["input"] == {"from": {"step": "records", "key": "records"}}
    assert steps["merge"][0]["keys"] == {"batch_id": report["publication"]["batch_id"],
                                         "consumer": report["publication"]["consumer"]}
    assert len(Artifacts().json(steps["processed"][0]["input"])["files"]) == len(DOCUMENTS)
    # The capture it was written from (ticket 121): a reading of this run takes the newest capture's runs.
    assert Artifacts().json(report["manifest"])["capture"] == "capture-1"


def test_the_engine_sees_version_one_steps():
    steps = validate(files.source(SOURCE), "mastering")["steps"]

    assert all(set(step) == {"name", "operation", "requires", "key", "leases", "checks"} for step in steps)


@pytest.mark.parametrize("plan, words", [
    ({"units": {"slices": {"bytes": 0}}}, "slices name their bytes"),
    ({"units": {"groups": 17}}, "groups hold 1..16"),
    ({"units": {"every": 2}}, "units are one"),
    ({"input": {"other": 1}}, "pieces, references, runfile, always and bind only"),
    ({"input": {"always": True}}, "always is true, names its files"),   # always without files
    ({"input": {"always": "yes", "files": "*"}}, "always is true, names its files"),
    ({"units": {"each": "Folder"}}, "each file"),
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


def test_a_source_whose_section_states_no_plan_is_refused(tmp_path, monkeypatch):
    body = files.source(SOURCE)
    body["bookkeeping"]["version"] = 1  # every committed source states version 2 now (ticket 149)
    monkeypatch.setattr(files, "source", lambda name, root=None: body)
    with pytest.raises(ValueError, match="must be version 2"):
        write_manifest(target="mastering", **options(tmp_path))


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


OTHER = {"source": "openfigi", "target": "mastering", "step": "answers"}


@pytest.mark.parametrize("named, words", [
    ({"pieces": {"run": OTHER}}, "pieces name one prerequisite step"),
    ({"lookups": {"umbrella": {"run": OTHER, "table": "pairs", "column": "fund", "value_column": "umbrella",
                               "max_input_bytes": 1024, "max_input_rows": 10}}}, "lookups each read"),
])
def test_a_step_reads_its_own_runs_steps_only(monkeypatch, named, words):
    body = files.source(SOURCE)
    read = body["bookkeeping"]["targets"]["mastering"]["steps"][0]
    read["units"] = "one" if "pieces" in named else {"each": "file"}
    read["input"] = {"contract": "source.yaml", **named}
    monkeypatch.setattr(files, "source", lambda name, root=None: body)
    with pytest.raises(Blocked, match=words):
        validate(files.source(SOURCE), "mastering")


def test_a_target_that_only_reads_has_no_publication_steps(tmp_path, monkeypatch):
    """A target with no preparation reads and records its files."""
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


def test_two_targets_over_the_same_files_each_process_them(tmp_path, monkeypatch):
    """A source's two Dataset Contracts read the same files through two targets; the target
    is part of the processing identity, so recording one never marks the files done for the other."""
    body = files.source(SOURCE)
    body["bookkeeping"]["targets"]["mastering_again"] = body["bookkeeping"]["targets"]["mastering"]
    monkeypatch.setattr(files, "source", lambda name, root=None: body)
    first = write_manifest(target="mastering", **options(tmp_path / "a"))
    second = write_manifest(target="mastering_again", **options(tmp_path / "b"))

    assert first["scope"]["processing_identity"] != second["scope"]["processing_identity"]
    assert first["publication"]["batch_id"] != second["publication"]["batch_id"]


PERIOD = {"period": "2026-06-30T00:00:00+00:00"}


def test_the_second_batch_of_securities_reads_the_same_files_with_its_own_context(tmp_path):
    """The Securities keyed by a SEDOL or a LoanX: the same passes and record rules as the first batch, batch `other`."""
    one = tmp_path / "one.json"  # the quarter's one data set file
    one.write_text(json.dumps([key(1001)]))
    settings = options(tmp_path, source="sec.nport.security", documents=str(one), facts=PERIOD)
    first = steps_of(write_manifest(target="mastering", **settings))
    other = steps_of(write_manifest(target="mastering_other_keys", **{**settings, "output": str(tmp_path / "other")}))

    assert {"record", "prepare", "merge", "processed"} < set(other) <= set(first)  # its own read, recorded like the first
    context = lambda steps: steps["record"][0]["input"]["compose"]["document"]["context"]
    assert (context(first)["batch"], context(other)["batch"]) == ("first", "other")
    assert other["prepare"][0]["keys"]["dataset"] == "sec.nport.security.v2"


def test_the_second_batch_of_securities_is_recorded_and_a_second_pass_skips_it(tmp_path):
    """The second batch records its files in the Change Journal, so a rerun of the same files finds nothing to load."""
    from uuid import uuid4

    from edgar_warehouse.workers import journal_record

    one = tmp_path / "one.json"
    one.write_text(json.dumps([key(1001)]))
    settings = options(tmp_path, source="sec.nport.security", target="mastering_other_keys", documents=str(one), facts=PERIOD)
    report = write_manifest(**settings)
    body = Artifacts().json(Artifacts().json(report["manifest"])["steps"]["processed"][0]["input"])
    for value in journal_record._events({"claim": {"run_id": str(uuid4())}}, body):
        settings["journal"].append(value)

    again = write_manifest(**{**settings, "output": str(tmp_path / "again")})
    assert again["manifest"] is None
