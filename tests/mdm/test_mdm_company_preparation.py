"""Company preparation's input manifest from the receipt-bound raw capture
(Issue 20 slice 20c): the caller's inputs are checked before anything is
frozen. The records the target's workers produce are tested on PG16
(`tests/integration/test_company_mastering_target_postgres.py`)."""

import json
from pathlib import Path

import pytest

from edgar_warehouse.mdm.target_manifest import write_manifest
from edgar_warehouse.mdm.name_count import _sec_population
from edgar_warehouse.mdm.name_count_file import write_name_count
from edgar_warehouse.mdm.store import Conflict
from tests.mdm.test_name_count import gleif
from tests.support.name_count_inputs import gleif_archive, gleif_reading
from tests.support.memory_journal import MemoryJournal
from tests.support.sec_capture import CATALOG, address, catalog, document, key, write_capture

APPLE, MSFT, ACME = 320193, 789019, 42
GLEIF = [gleif("HWUPKR0MPOU8FGXBT394", "Apple Inc.")]
PINS = {"capture_run": "capture-1", "catalog_run": "catalog-1", "observed_at": "2026-09-30T02:20:28+00:00",
        "as_of": "2026-09-29T15:00:00Z", "revision": 0}


def documents(changes=None):
    found = {
        APPLE: document(APPLE, "Apple Inc.", forms=("10-Q", "10-K", "10-K"), former=["APPLE COMPUTER INC"],
                        business=address(street="ONE APPLE PARK WAY", city="CUPERTINO", state="CA")),
        MSFT: document(MSFT, "MICROSOFT CORP", business=address(street="ONE MICROSOFT WAY", city="REDMOND",
                                                                 state="WA", zip_code="98052")),
        ACME: document(ACME, "ACME HOLDINGS PLC", business=address(street="1 KING ST", city="LONDON", state="X0",
                                                                    zip_code="EC2", country="UNITED KINGDOM",
                                                                    country_code="GB")),
    }
    return {**found, **(changes or {})}


CATALOG_ROWS = catalog((APPLE, "Apple Inc.", "AAPL", "Nasdaq"), (MSFT, "MICROSOFT CORP", "MSFT", "Nasdaq"),
                       (APPLE, "Apple Inc.", "AAPL", "Nasdaq"), (APPLE, "Apple Inc.", "APLE", "OTC"))


@pytest.fixture
def capture(tmp_path):
    return name_count_capture(tmp_path, documents(), CATALOG_ROWS)


def name_count_capture(tmp_path, found, rows):
    folder, population = write_capture(tmp_path / "capture", found, rows)
    (tmp_path / "g").mkdir()
    archive, metadata, _ = gleif_archive(tmp_path / "g", GLEIF)
    filers = [(f"{cik:010d}", d["name"], [n["name"] for n in d["formerNames"]]) for cik, d in found.items()]
    name_count = tmp_path / "name-count.json"
    write_name_count(capture=str(folder), population=str(population), gleif_metadata=str(metadata),
                         gleif_reading=gleif_reading(tmp_path / "r", archive, _sec_population(filers)[1], len(GLEIF)),
                         output=str(name_count), catalog=CATALOG)
    return folder, population, name_count


def prepare(tmp_path, capture, ciks=(APPLE, MSFT, ACME), output="bundle", name_count=None, observed_at=None,
            load_mode="default", revision=PINS["revision"], force=False, journal=None):
    """The Company mastering target's input manifest, planned by the generic writer (ticket 177)."""
    folder, population, counted = capture
    listed = tmp_path / f"documents-{output}.json"
    listed.write_text(json.dumps([key(c) for c in ciks] + [CATALOG]))
    report = write_manifest(
        source="sec.company", target="mastering", capture=str(folder), documents=str(listed),
        capture_run=PINS["capture_run"], output=str(tmp_path / output), as_of=PINS["as_of"], revision=revision,
        journal=journal or MemoryJournal(), force=force,
        facts={"capture_run": PINS["capture_run"], "catalog_run": PINS["catalog_run"],
               "observed_at": observed_at or PINS["observed_at"], "load_mode": load_mode},
        run_files={"name_count": str(name_count or counted)})
    return report, Path(tmp_path / output)


def test_the_manifest_is_content_addressed_and_written_once(tmp_path, capture):
    report, _ = prepare(tmp_path, capture)
    assert prepare(tmp_path, capture)[0] == report
    assert report["target"] == "mastering" and report["scope"]["documents"] == 4
    assert report["publication"]["publication_key"].startswith("capture-1:sec.company:")
    assert prepare(tmp_path, capture, revision=1)[0]["manifest"] != report["manifest"]


def test_a_different_catalog_is_a_different_publication(tmp_path, capture):
    first = prepare(tmp_path, capture)[0]
    other = name_count_capture(tmp_path / "other", documents(), catalog((APPLE, "Apple Inc.", "AAPL", "Nasdaq")))
    second = prepare(tmp_path / "other", other)[0]
    assert first["scope"]["receipts_sha256"] != second["scope"]["receipts_sha256"]
    assert first["publication"]["publication_key"] != second["publication"]["publication_key"]


def test_a_name_count_that_did_not_count_this_capture_is_refused(tmp_path, capture):
    _, _, name_count = name_count_capture(tmp_path / "other", documents(), catalog())
    with pytest.raises(Conflict, match="did not count"):
        prepare(tmp_path, capture, name_count=name_count)


def test_a_document_that_differs_from_its_receipt_is_refused(tmp_path, capture):
    folder, *_ = capture
    (folder / "bronze" / key(MSFT).removeprefix("warehouse/bronze/")).write_text(json.dumps({"name": "CHANGED"}))
    with pytest.raises(Conflict, match="differs from its receipt"):
        prepare(tmp_path, capture)


def test_a_bundle_names_at_most_512_distinct_documents(tmp_path, capture):
    folder, population, name_count = capture
    listed = tmp_path / "documents.json"
    for keys in ([], [f"bronze/main/{n}.json" for n in range(513)]):
        listed.write_text(json.dumps(keys))
        with pytest.raises(ValueError, match="1..512 distinct"):
            write_manifest(source="sec.company", target="mastering", capture=str(folder), documents=str(listed),
                           capture_run="capture-1", output=str(tmp_path / "x"), as_of=PINS["as_of"], revision=0,
                           journal=MemoryJournal(),
                           facts={"capture_run": "c", "catalog_run": "d", "observed_at": PINS["observed_at"],
                                  "load_mode": "default"}, run_files={"name_count": str(name_count)})


def test_another_observation_time_or_load_mode_is_another_consumer(tmp_path, capture):
    """The consumer and batch ids name what shapes the rows, so a changed rerun never reuses a batch key."""
    first = prepare(tmp_path, capture)[0]["publication"]
    later = prepare(tmp_path, capture, observed_at="2026-10-01T00:00:00+00:00")[0]["publication"]
    reloaded = prepare(tmp_path, capture, load_mode="full")[0]["publication"]
    assert first["publication_key"] == later["publication_key"] == reloaded["publication_key"]
    assert len({first["consumer"], later["consumer"], reloaded["consumer"]}) == 3
    assert len({first["batch_id"], later["batch_id"], reloaded["batch_id"]}) == 3
