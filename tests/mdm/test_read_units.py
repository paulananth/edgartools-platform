"""A declared read's units (ticket 14, slice 2c): templates, companions and their refusals.
The chain they form runs end to end in `tests/integration/test_declared_chain_postgres.py`."""
import copy
import json

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean import read_units
from edgar_warehouse.mdm.clean.store import Conflict
from edgar_warehouse.mdm.clean.target_manifest import write_manifest
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
    keys = chain.capture(tmp_path / "capture")
    if tamper:
        tamper(tmp_path / "capture")
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps(keys))
    return write_manifest(source="openfigi", target="mastering_cusip", capture=str(tmp_path / "capture"),
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
    from edgar_warehouse.mdm.clean import raw_capture

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
    keys = chain.capture(tmp_path / "capture")
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps(keys))

    def written(out):
        return write_manifest(source="openfigi", target="mastering_cusip", capture=str(tmp_path / "capture"),
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
    chain.capture(tmp_path / "capture", rewrite=False)
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
        chain.capture(capture, rewrite=False)

    report = write(tmp_path, monkeypatch, tamper=large)
    assert report["manifest"] is not None and report["scope"]["documents"] == 8


def gleif_bundle(tmp_path, **inputs):
    """GLEIF's declared target over an invented one-file capture, with the run's facts and files."""
    import hashlib
    capture = tmp_path / "capture"
    capture.mkdir()
    name = "01-x-gleif-goldencopy-lei2-golden-copy.json.zip"
    (capture / name).write_bytes(b"invented")
    (capture / "receipts.jsonl").write_text(json.dumps(
        {"bytes": 8, "key": name, "sha256": hashlib.sha256(b"invented").hexdigest()}) + "\n")
    (tmp_path / "documents.json").write_text(json.dumps([name]))
    (tmp_path / "scope.json").write_text(json.dumps({"ZZ00000000000000000A00": {"selected": True}}))
    (tmp_path / "issuers.json").write_text("[]")
    run = {"facts": {"publication_count": 3},
           "run_files": {"approved_scope": str(tmp_path / "scope.json"), "nport_issuers": str(tmp_path / "issuers.json")},
           **inputs}
    return write_manifest(source="gleif", target="mastering", capture=str(capture), documents=str(tmp_path / "documents.json"),
                          capture_run="c", output=str(tmp_path / "bundle"), as_of="2026-10-19T00:00:00Z", revision=0,
                          journal=MemoryJournal(), **run)


def test_a_run_fact_and_run_files_fill_the_reading(tmp_path):
    store = Artifacts()
    (read,) = store.json(gleif_bundle(tmp_path)["manifest"])["steps"]["read"]
    document = store.json(read["input"])
    assert store.json(document["contract"])["read"]["references"]["approved_scope"] == {
        "ZZ00000000000000000A00": {"selected": True}}
    (artifact,) = document["artifacts"]
    assert store.json(artifact["context"])["values"] == {"publication_count": 3}
    assert store.json(artifact["lookups"])["sets"] == {"nport_issuers": []}


def test_a_run_without_the_declared_facts_and_files_is_refused(tmp_path):
    with pytest.raises(ValueError, match="takes facts"):
        gleif_bundle(tmp_path, facts={})


def test_a_step_naming_an_undeclared_fact_is_refused():
    from edgar_warehouse.bookkeeping.clean.config import Blocked, validate
    body = copy.deepcopy(files.source("gleif"))
    body["bookkeeping"]["targets"]["mastering"]["run"]["facts"] = []
    with pytest.raises(Blocked, match="not in the target's run"):
        validate(body, "mastering")


def test_run_arguments_read_a_fact_as_json_else_text():
    from edgar_warehouse.mdm.clean.target_manifest import run_arguments
    assert run_arguments(["n=3", "label=x"], ["scope=/s.json"]) == ({"n": 3, "label": "x"}, {"scope": "/s.json"})
    with pytest.raises(ValueError, match="each name once"):
        run_arguments(["n=3", "n=4"], None)


def test_a_run_file_that_is_not_json_is_refused(tmp_path):
    (tmp_path / "bad.json").parent.mkdir(exist_ok=True)
    (tmp_path / "bad.json").write_text("not json")
    with pytest.raises(ValueError, match="Run file approved_scope"):
        gleif_bundle(tmp_path, run_files={"approved_scope": str(tmp_path / "bad.json"),
                                          "nport_issuers": str(tmp_path / "bad.json")})


def test_a_fact_of_another_type_is_refused(tmp_path):
    with pytest.raises(ValueError, match="fact publication_count"):
        gleif_bundle(tmp_path, facts={"publication_count": "abc"})


def test_a_lookup_set_file_of_another_shape_is_refused(tmp_path):
    (tmp_path / "issuers2.json").write_text(json.dumps({"not": "a list"}))
    (tmp_path / "s2.json").write_text(json.dumps({"ZZ00000000000000000A00": {"selected": True}}))
    with pytest.raises(ValueError, match="is not lookup set nport_issuers"):
        gleif_bundle(tmp_path, run_files={"approved_scope": str(tmp_path / "s2.json"),
                                          "nport_issuers": str(tmp_path / "issuers2.json")})


def test_a_reference_the_contract_does_not_declare_empty_is_refused(tmp_path, monkeypatch):
    body = copy.deepcopy(files.source("gleif"))
    read = body["bookkeeping"]["targets"]["mastering"]["steps"][0]["input"]
    read["references"] = {"approved_scoep": {"file": "approved_scope"}}
    monkeypatch.setattr(files, "source", lambda name, *a, **k: body)
    with pytest.raises(ValueError, match="reference approved_scoep"):
        gleif_bundle(tmp_path)


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
