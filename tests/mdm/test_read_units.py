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
        steps[4]["requires"], steps[4]["input"]["pieces"] = ["answers"], {"step": "answers"}

    with pytest.raises(ValueError, match="pieces are read from a source.combine step"):
        write(tmp_path, monkeypatch, from_answers)
