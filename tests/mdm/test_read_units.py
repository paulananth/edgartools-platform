"""A declared read's units (ticket 14, slice 2c): templates, companions and their refusals.
The chain they form runs end to end in `tests/integration/test_declared_chain_postgres.py`."""
import copy
import json

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm import read_units
from edgar_warehouse.mdm.store import Conflict
from edgar_warehouse.mdm.target_manifest import write_manifest
from edgar_warehouse.rules import files
from tests.integration import test_declared_chain_postgres as chain
from tests.support.memory_journal import MemoryJournal


def test_a_template_names_the_folder_the_base_and_the_name():
    assert read_units.fill("{dir}/{base}.request.json", "id_x/00003.json") == "id_x/00003.request.json"
    assert read_units.fill("{name}", "id_x/00003.json") == "00003.json"
    assert read_units.fill(7, "id_x/00003.json") == 7
    assert read_units.pair("id_x/00003.json") == read_units.pair("id_x/00003.request.json") == "id_x/00003"


def write(tmp_path, monkeypatch, change=None, tamper=None):
    body = chain.declared(monkeypatch)
    if change:
        change(body["bookkeeping"]["targets"][chain.TARGET]["steps"])
    keys = chain.capture(tmp_path / "capture", words=("cusip",))
    if tamper:
        tamper(tmp_path / "capture")
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps(keys))
    return write_manifest(source="openfigi", target="mastering", capture=str(tmp_path / "capture"),
                          documents=str(listed), capture_run="c", output=str(tmp_path / "bundle"),
                          as_of="2026-10-17T00:00:00Z", revision=0, journal=MemoryJournal())


def test_each_answers_file_reads_the_same_files_request_unit(tmp_path, monkeypatch):
    steps = Artifacts().json(write(tmp_path, monkeypatch)["manifest"])["steps"]

    assert [u["keys"]["unit"] for u in steps["requests"]] == [f"id_cusip/{n:05d}" for n in range(8)]
    first = steps["answers"][0]["input"]["compose"]
    named = [first["slots"][a["lookups"]["slot"]]["compose"]["slots"]["asked"] for a in first["document"]["artifacts"]]
    assert named == [{"step": "requests", "key": f"id_cusip/{n:05d}"} for n in range(3)]
    assert len(steps["reduce"][0]["input"]["compose"]["slots"]["answers"]) == 3


def test_a_companion_that_differs_from_its_receipt_is_refused(tmp_path, monkeypatch):
    def tamper(capture):
        (capture / "id_cusip" / "00000.request.json").write_text("[]")

    with pytest.raises(Conflict, match="differs from its receipt"):
        write(tmp_path, monkeypatch, tamper=tamper)


def test_a_receipt_without_the_companions_sha256_is_refused(tmp_path, monkeypatch):
    def other_field(steps):
        steps[0]["input"]["beside"]["sha256"] = "answer_sha256"

    with pytest.raises(Conflict, match="holds no answer_sha256"):
        write(tmp_path, monkeypatch, other_field)


def test_a_lookup_from_a_step_not_read_file_by_file_is_refused(tmp_path, monkeypatch):
    def grouped(steps):
        steps[0]["units"] = {"groups": 2}

    with pytest.raises(ValueError, match="units are each file"):
        write(tmp_path, monkeypatch, grouped)


def test_a_pattern_no_document_matches_is_refused(tmp_path, monkeypatch):
    def isins(steps):
        steps[1]["input"]["files"] = "id_isin/*"

    with pytest.raises(ValueError, match="no document of the bundle matches"):
        write(tmp_path, monkeypatch, isins)


def test_a_capture_key_outside_the_capture_is_refused(tmp_path):
    from edgar_warehouse.mdm import raw_capture

    with pytest.raises(Conflict, match="stays inside the capture"):
        raw_capture.path(tmp_path, "../elsewhere.json")


def test_one_step_reading_names_a_step_of_one_unit(tmp_path, monkeypatch):
    def from_answers(steps):
        steps[3]["requires"], steps[3]["input"]["readings"] = ["answers"], {"counts": {"step": "answers"}}

    with pytest.raises(ValueError, match="names a step of one unit"):
        write(tmp_path, monkeypatch, from_answers)


def test_the_declaration_is_not_changed_by_writing(tmp_path, monkeypatch):
    body = chain.declared(monkeypatch)
    before = copy.deepcopy(body)
    write(tmp_path, monkeypatch)
    assert files.source("openfigi") == before


def test_a_changed_request_beside_an_unchanged_answer_is_named_again(tmp_path, monkeypatch):
    from uuid import uuid4

    from edgar_warehouse.workers import journal_record

    journal = MemoryJournal()
    chain.declared(monkeypatch)
    keys = chain.capture(tmp_path / "capture", words=("cusip",))
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps(keys))

    def written(out):
        return write_manifest(source="openfigi", target="mastering", capture=str(tmp_path / "capture"),
                              documents=str(listed), capture_run="c", output=str(tmp_path / out),
                              as_of="2026-10-17T00:00:00Z", revision=0, journal=journal)
    first = written("first")
    body = Artifacts().json(Artifacts().json(first["manifest"])["steps"]["processed"][0]["input"])
    assert len(body["files"]) == 16  # each answer and the request beside it
    for event in journal_record._events({"claim": {"run_id": str(uuid4())}}, body):
        journal.append(event)
    assert written("again")["manifest"] is None
    # Asked again for another identifier, OpenFIGI's "not found" answer is the same bytes; the request is not.
    request = tmp_path / "capture" / "id_cusip" / "00007.request.json"
    request.write_text(json.dumps([{"idType": "ID_CUSIP", "idValue": "ZZ0000146"}]))
    chain.capture(tmp_path / "capture", rewrite=False, words=("cusip",))
    assert written("changed")["scope"]["documents"] == 1


def test_a_read_with_lookups_and_no_context_gets_an_empty_one(tmp_path, monkeypatch):
    def no_context(steps):
        del steps[1]["input"]["context"]
    steps = Artifacts().json(write(tmp_path, monkeypatch, no_context)["manifest"])["steps"]

    artifact = steps["answers"][0]["input"]["compose"]["document"]["artifacts"][0]
    assert Artifacts().json(artifact["context"])["values"] == {}


def test_pieces_are_read_from_a_combine(tmp_path, monkeypatch):
    def from_answers(steps):
        (record,) = [step for step in steps if step["name"] == "record"]
        record["requires"], record["input"]["pieces"] = ["answers"], {"step": "answers"}

    with pytest.raises(ValueError, match="pieces are read from a source.combine step"):
        write(tmp_path, monkeypatch, from_answers)


def test_a_bundle_larger_than_its_readings_is_not_refused_for_its_bytes(tmp_path, monkeypatch):
    def large(capture):  # one answer file padded past 24 MiB, as a real ISIN bundle is
        path = capture / "id_cusip" / "00000.json"
        answers = json.loads(path.read_text())
        path.write_text(json.dumps(answers) + " " * (25 * 1024**2))
        chain.capture(capture, rewrite=False, words=("cusip",))

    report = write(tmp_path, monkeypatch, tamper=large)
    assert report["manifest"] is not None and report["scope"]["documents"] == 8


def gleif_bundle(tmp_path, **inputs):
    """GLEIF's declared target over an invented one-file capture, with the run's fact."""
    import hashlib
    capture = tmp_path / "capture"
    capture.mkdir()
    name = "01-x-gleif-goldencopy-lei2-golden-copy.json.zip"
    (capture / name).write_bytes(b"invented")
    (capture / "receipts.jsonl").write_text(json.dumps(
        {"bytes": 8, "key": name, "sha256": hashlib.sha256(b"invented").hexdigest()}) + "\n")
    (tmp_path / "documents.json").write_text(json.dumps([name]))
    run = {"facts": {"publication_count": 3}, **inputs}
    return write_manifest(source="gleif", target="mastering", capture=str(capture), documents=str(tmp_path / "documents.json"),
                          capture_run="c", output=str(tmp_path / "bundle"), as_of="2026-10-19T00:00:00Z", revision=0,
                          journal=MemoryJournal(), **run)


def test_a_run_fact_fills_the_reading(tmp_path):
    store = Artifacts()
    (read,) = store.json(gleif_bundle(tmp_path)["manifest"])["steps"]["read"]
    (artifact,) = store.json(read["input"])["artifacts"]
    assert store.json(artifact["context"])["values"] == {"publication_count": 3}


def test_a_run_without_the_declared_facts_is_refused(tmp_path):
    with pytest.raises(ValueError, match="takes facts"):
        gleif_bundle(tmp_path, facts={})


def test_a_step_naming_an_undeclared_fact_is_refused():
    from edgar_warehouse.bookkeeping.clean.config import Blocked, validate
    body = copy.deepcopy(files.source("gleif"))
    body["bookkeeping"]["targets"]["mastering"]["run"]["facts"] = []
    with pytest.raises(Blocked, match="not in the target's run"):
        validate(body, "mastering")


def test_run_arguments_read_a_fact_as_json_else_text():
    from edgar_warehouse.mdm.target_manifest import run_arguments
    assert run_arguments(["n=3", "label=x"], ["scope=/s.json"]) == ({"n": 3, "label": "x"}, {"scope": "/s.json"})
    with pytest.raises(ValueError, match="each name once"):
        run_arguments(["n=3", "n=4"], None)


def test_a_fact_of_another_type_is_refused(tmp_path):
    with pytest.raises(ValueError, match="fact publication_count"):
        gleif_bundle(tmp_path, facts={"publication_count": "abc"})


def fund_bundle(tmp_path, change=None):
    """N-PORT fund's declared target over an invented one-file capture."""
    import hashlib
    capture = tmp_path / "capture"
    capture.mkdir(parents=True)
    (capture / "q.zip").write_bytes(b"invented")
    (capture / "receipts.jsonl").write_text(json.dumps(
        {"bytes": 8, "key": "q.zip", "sha256": hashlib.sha256(b"invented").hexdigest()}) + "\n")
    (tmp_path / "documents.json").write_text(json.dumps(["q.zip"]))
    return write_manifest(source="sec.nport.fund", target="mastering", capture=str(capture),
                          documents=str(tmp_path / "documents.json"), capture_run="c", output=str(tmp_path / "bundle"),
                          as_of="2026-10-19T00:00:00Z", revision=0, journal=MemoryJournal())


def test_a_step_reads_with_another_sources_rules_file(tmp_path):
    store = Artifacts()
    steps = store.json(fund_bundle(tmp_path)["manifest"])["steps"]
    (submissions,) = steps["submissions"]
    contract = store.json(store.json(submissions["input"])["contract"])
    assert contract == files.load(files.ROOT / "sources" / "sec.nport.registrant" / "submissions.yaml")


def test_another_sources_file_joins_the_processing_identity(tmp_path, monkeypatch):
    first = fund_bundle(tmp_path / "a")["scope"]["processing_identity"]
    load = files.load
    monkeypatch.setattr(files, "load", lambda path, *a, **k: {**load(path, *a, **k), "note": "changed"}
                        if str(path).endswith("sec.nport.registrant/submissions.yaml") else load(path, *a, **k))
    assert fund_bundle(tmp_path / "b")["scope"]["processing_identity"] != first


@pytest.mark.parametrize("name", ["../x.yaml", "a/../b.yaml", "/x.yaml", "a/b/c.yaml"])
def test_a_contract_path_outside_the_rules_is_refused(name):
    from edgar_warehouse.bookkeeping.clean.config import Blocked, validate
    body = copy.deepcopy(files.source("sec.nport.fund"))
    body["bookkeeping"]["targets"]["mastering"]["steps"][0]["input"]["contract"] = name
    with pytest.raises(Blocked, match="rules file"):
        validate(body, "mastering")


@pytest.mark.parametrize("name", ["nosuch/x.yaml", "sec.nport.fund/source.yaml"])
def test_a_missing_source_or_the_sources_own_folder_is_refused(tmp_path, monkeypatch, name):
    body = copy.deepcopy(files.source("sec.nport.fund"))
    body["bookkeeping"]["targets"]["mastering"]["steps"][0]["input"]["contract"] = name
    source = files.source
    monkeypatch.setattr(files, "source", lambda n, *a, **k: body if n == "sec.nport.fund" else source(n, *a, **k))
    with pytest.raises(ValueError, match="another source's existing rules file"):
        fund_bundle(tmp_path)


def over_all(steps):
    answers = next(step for step in steps if step["name"] == "answers")
    answers["units"] = "one"
    answers["input"]["lookups"]["asked"]["over"] = "all"


def test_a_lookup_over_all_reads_every_unit_of_its_prerequisite_in_one_reading(tmp_path, monkeypatch):
    """Ticket 177, slice 4: one read of a large shared file per bundle, not one per group of files
    (measured: 0.56 s a read for a 6 MB Name Count whether it is narrowed to 16 keys or 512)."""
    steps = Artifacts().json(write(tmp_path, monkeypatch, over_all)["manifest"])["steps"]

    (unit,) = steps["answers"]
    compose = unit["input"]["compose"]
    named = compose["slots"][compose["document"]["artifacts"][0]["lookups"]["slot"]]["compose"]["slots"]["asked"]
    assert named == [{"step": "requests", "key": f"id_cusip/{n:05d}"} for n in range(8)]
    # the lookup document names that slot whole, as a derived set reads a list of readings
    document = compose["slots"][compose["document"]["artifacts"][0]["lookups"]["slot"]]["compose"]["document"]
    assert document["sets"]["asked"]["readings"] == {"slot": "asked"}


def test_a_lookup_over_all_is_one_of_all_or_each(tmp_path, monkeypatch):
    def bad(steps):
        over_all(steps)
        next(step for step in steps if step["name"] == "answers")["input"]["lookups"]["asked"]["over"] = "some"

    with pytest.raises(Exception, match="over"):
        write(tmp_path, monkeypatch, bad)


def each_answers(steps):
    reduce = next(step for step in steps if step["name"] == "reduce")
    reduce["units"] = {"each": "answers"}
    reduce["input"]["readings"] = {"answers": {"step": "answers"}}
    later = next(step for step in steps if step["name"] == "combine")  # reads the reduce units, now several
    later["input"]["readings"] = {slot: {"all": "reduce"} if named == {"step": "reduce"} else named
                                  for slot, named in later["input"]["readings"].items()}


def test_a_combine_may_make_one_unit_for_each_unit_of_a_step(tmp_path, monkeypatch):
    """Ticket 177, slice 5: the Company combination runs once per main unit (its 100,000-row bound)."""
    steps = Artifacts().json(write(tmp_path, monkeypatch, each_answers)["manifest"])["steps"]

    assert [u["keys"]["unit"] for u in steps["reduce"]] == [f"reduce-{n}" for n in range(3)]
    slots = [u["input"]["compose"]["slots"]["answers"] for u in steps["reduce"]]
    assert slots == [{"step": "answers", "key": a["keys"]["unit"]} for a in steps["answers"]]


@pytest.mark.parametrize("units, message", [
    ({"each": "file"}, "only a read declares"),             # a combine over each file
    ({"each": "nothing"}, "a read step it requires"),            # a step it does not require
    ({"groups": 2}, "only a read declares"),
])
def test_a_combines_units_are_each_unit_of_a_step_it_requires(tmp_path, monkeypatch, units, message):
    def bad(steps):
        each_answers(steps)
        next(step for step in steps if step["name"] == "reduce")["units"] = units

    with pytest.raises(Exception, match=message):
        write(tmp_path, monkeypatch, bad)
