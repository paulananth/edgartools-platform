"""Automatic whole-capture preparation, with invented records and real Rust reading."""
import copy
import json
import zipfile
from contextlib import contextmanager

import pytest

from edgar_warehouse.mdm.evidence import assertion
from edgar_warehouse.rules import files, preparation
from edgar_warehouse.rules.driving import RunStopped
from tests.support.waterfall import capture, native

OPTIONS = {"kind": "company", "holder_source": "sec.company.v1", "files": "*lei2-golden-copy*",
           "completeness": "full_publication",
           "full_filename": r"[0-9]{8}-[0-9]{4}-gleif-goldencopy-lei2-golden-copy[.]json[.]zip",
           "count_fact": "publication_count"}
ADDRESS = {"street": "1 Example Way", "city": "Exampleton", "postcode": "12345", "country": "US"}
AS_OF = "2026-11-11T12:00:00+00:00"


def filer(key="0000000017", name="INVENTED CO", revision=1, effective_at=None):
    return assertion(source_code=OPTIONS["holder_source"], record_key=key, publication_key="invented",
                     revision=revision, effective_at=effective_at, kind="company", identifiers={"cik": key},
                     fields={"name": name, "state_of_incorporation": "DE"},
                     provenance={"matching": {"address": ADDRESS, "business_country": "US"}})


class Store:
    def __init__(self, records):
        self.records, self.applied = records, {}

    def rows(self, statement, values):
        return [(json.dumps(r),) for r in self.records]


def serve(monkeypatch, store):
    @contextmanager
    def registered(_, environment):
        yield store

    monkeypatch.setattr(preparation, "registered_store", registered)
    # The shared-engine database behavior is qualified separately by storage-adapter tests.
    from edgar_warehouse.mastering import merge

    def apply(db, settings, source, pairs, **kwargs):
        changed = {k: p for k, p in pairs.items() if db.applied.get(k) != p}
        db.applied.update(changed)
        return {"records": len(changed)}

    monkeypatch.setattr(merge, "apply_pairs", apply)


def run(folder, target, *, count=1):
    return preparation._waterfall(options=OPTIONS, capture=folder, folder=target, facts={"publication_count": count},
                                 as_of=AS_OF, deadline=float("inf"), say=lambda _: None, environment={})


def test_complete_native_capture_prepares_a_unique_pair_and_unchanged_repeat_does_not_read_or_apply_again(tmp_path, monkeypatch):
    db = Store([filer()])
    serve(monkeypatch, db)
    folder = capture(tmp_path / "capture", [native()])
    first = run(folder, tmp_path / "prepared")
    assert (first["filers"], first["pairs"], first["applied"]) == (1, 1, 1)
    assert db.applied["0000000017"]["lei"] == "00000000000000000000"

    monkeypatch.setattr(preparation, "project_capture", lambda *a, **k: pytest.fail("unchanged capture re-read"))
    repeated = run(folder, tmp_path / "prepared")
    assert repeated["input_digest"] == first["input_digest"]
    assert repeated["applied"] == 0
    assert repeated["publication"]["evidence"] == "source-declared-complete-capture"
    assert "content_date" not in repeated["publication"]


@pytest.mark.parametrize("reverse", [False, True])
def test_current_source_revision_is_selected_by_the_shared_kernel_not_sql_order(tmp_path, monkeypatch, reverse):
    versions = [filer(name="RETIRED NAME", revision=1), filer(revision=2)]
    if reverse:
        versions.reverse()
    db = Store(versions)
    serve(monkeypatch, db)
    result = run(capture(tmp_path / "capture", [native()]), tmp_path / "prepared")
    assert (result["filers"], result["pairs"]) == (1, 1)


def test_a_future_source_revision_is_not_a_current_pairing_input(tmp_path, monkeypatch):
    db = Store([filer(), filer(name="FUTURE NAME", revision=2, effective_at="2027-01-01T00:00:00+00:00")])
    serve(monkeypatch, db)
    result = run(capture(tmp_path / "capture", [native()]), tmp_path / "prepared")
    assert (result["filers"], result["pairs"]) == (1, 1)


@pytest.mark.parametrize("name,pairs", [(None, 1), ({"op": "retract"}, 0)])
def test_pairing_uses_folded_current_fields_without_rewriting_the_patch(tmp_path, monkeypatch, name, pairs):
    db = Store([filer(), filer(name=name, revision=2)])
    original_fields = copy.deepcopy(db.records[-1]["fields"])
    serve(monkeypatch, db)
    result = run(capture(tmp_path / "capture", [native()]), tmp_path / "prepared")
    assert (result["filers"], result["pairs"]) == (1, pairs)
    assert db.records[-1]["fields"] == original_fields


def test_a_shared_name_on_either_side_prepares_no_binding(tmp_path, monkeypatch):
    for side in ("holder", "publication"):
        db = Store([filer()] + ([filer("0000000018")] if side == "holder" else []))
        serve(monkeypatch, db)
        rows = [native()] + ([native(lei="00000000000000000001")] if side == "publication" else [])
        result = run(capture(tmp_path / side, rows), tmp_path / (side + "-prepared"), count=len(rows))
        assert (result["pairs"], result["applied"], db.applied) == (0, 0, {})


def test_changed_population_invalidates_the_cached_projection(tmp_path, monkeypatch):
    db = Store([filer()])
    serve(monkeypatch, db)
    folder = capture(tmp_path / "capture", [native()])
    first = run(folder, tmp_path / "prepared")
    db.records.append(filer("0000000018"))
    changed = run(folder, tmp_path / "prepared")
    assert changed["input_digest"] != first["input_digest"]
    assert changed["pairs"] == 0
    # New ambiguity does not silently undo an accepted earlier binding.
    assert db.applied["0000000017"]["lei"] == "00000000000000000000"


def test_cached_pairs_do_not_bypass_a_damaged_capture_receipt(tmp_path, monkeypatch):
    db = Store([filer()])
    serve(monkeypatch, db)
    folder = capture(tmp_path / "capture", [native()])
    run(folder, tmp_path / "prepared")
    archive = next(folder.glob("*.zip"))
    archive.write_bytes(archive.read_bytes() + b"changed")
    from edgar_warehouse.mastering import merge
    monkeypatch.setattr(merge, "apply_pairs", lambda *a, **k: pytest.fail("damaged cached capture applied"))
    with pytest.raises(ValueError):
        run(folder, tmp_path / "prepared")


def test_interrupted_application_reuses_verified_input_and_applies_it_on_retry(tmp_path, monkeypatch):
    db = Store([filer()])
    serve(monkeypatch, db)
    from edgar_warehouse.mastering import merge
    apply = merge.apply_pairs
    monkeypatch.setattr(merge, "apply_pairs", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("interrupted")))
    folder = capture(tmp_path / "capture", [native()])
    with pytest.raises(RuntimeError, match="interrupted"):
        run(folder, tmp_path / "prepared")
    assert db.applied == {}
    monkeypatch.setattr(merge, "apply_pairs", apply)
    monkeypatch.setattr(preparation, "project_capture", lambda *a, **k: pytest.fail("verified projection re-read"))
    assert run(folder, tmp_path / "prepared")["applied"] == 1


def test_a_damaged_or_incomplete_capture_makes_no_pairs_durable(tmp_path, monkeypatch):
    db = Store([filer()])
    serve(monkeypatch, db)
    folder = capture(tmp_path / "capture", [native()])
    with pytest.raises(ValueError, match="record count"):
        run(folder, tmp_path / "wrong-count", count=2)
    assert db.applied == {}
    archive = next(folder.glob("*.zip"))
    archive.write_bytes(archive.read_bytes()[:-10])
    with pytest.raises((ValueError, zipfile.BadZipFile)):
        run(folder, tmp_path / "damaged")
    assert db.applied == {}


def test_the_current_source_declares_automatic_preparation_and_an_unknown_method_is_refused(tmp_path):
    reading = files.source("gleif")
    assert reading["bookkeeping"]["targets"]["mastering"]["preparation"] == [
        {"method": "waterfall", "options": OPTIONS}]
    other = copy.deepcopy(reading)
    other["bookkeeping"]["targets"]["mastering"]["preparation"][0]["method"] = "invented_unknown"
    with pytest.raises(RunStopped, match="Unknown automatic preparation"):
        preparation.prepare_load(reading=other, target="mastering", capture=tmp_path, folder=tmp_path,
                                 facts=[], as_of=AS_OF, deadline=float("inf"), say=lambda _: None, environment={})


@pytest.mark.parametrize("key", ["20260101-0000-gleif-goldencopy-lei2-golden-copy-delta.json.zip",
                                "20260101-0000-gleif-goldencopy-lei2-golden-copy-partial.json.zip",
                                "invented-lei2-golden-copy.json.zip"])
def test_delta_partial_and_unrecognized_filenames_are_refused_even_with_matching_counts(tmp_path, monkeypatch, key):
    db = Store([filer()])
    serve(monkeypatch, db)
    with pytest.raises(RunStopped, match="exactly one complete"):
        run(capture(tmp_path / "capture", [native()], key=key), tmp_path / "prepared")
    assert db.applied == {}


def test_registered_preparation_uses_the_selected_worker_environment_and_disposes_on_refusal(monkeypatch):
    from edgar_warehouse import database_connections
    from edgar_warehouse.mdm import connections

    seen = []

    class Engine:
        @contextmanager
        def connect(self):
            yield object()

        def dispose(self):
            seen.append("disposed")

    selected = {"selected-worker": "invented"}
    monkeypatch.setattr(connections, "engine_from_environment",
                        lambda name, environment, restricted: seen.append((name, environment, restricted)) or Engine())
    monkeypatch.setattr(database_connections, "storage_adapter",
                        lambda: type("Adapter", (), {"registered_policy": lambda self, conn, digest: None})())
    # The value is only a presence marker: connection construction is stubbed above.
    selected["MDM_DATABASE_URL"] = "invented-present"
    with pytest.raises(RunStopped, match="registered mastering policy"):
        with preparation.registered_store("invented-policy", selected):
            pytest.fail("unregistered policy was admitted")
    assert seen == [("MDM_DATABASE_URL", selected, True), "disposed"]


def test_an_explicit_connection_environment_overrides_ambient_values(monkeypatch):
    from edgar_warehouse.mdm import connections

    calls = []
    adapter = type("Adapter", (), {"connect": lambda self, *a, **k: calls.append((a, k)) or "engine"})()
    monkeypatch.setattr(connections, "storage_adapter", lambda: adapter)
    monkeypatch.setenv("MDM_DATABASE_URL", "not-a-connection")
    selected = {"MDM_DATABASE_URL": "postgresql://invented:invented@localhost/invented",
                "MDM_APPLICATION_ROLE": "invented_worker"}
    assert connections.engine_from_environment("MDM_DATABASE_URL", selected) == "engine"
    assert calls == [((selected["MDM_DATABASE_URL"], "postgresql"), {"runtime_role": "invented_worker"})]
