"""Company preparation's input manifest from the receipt-bound raw capture
(Issue 20 slice 20c): the caller's inputs are checked before anything is
frozen. The records the target's workers produce are tested on PG16
(`tests/integration/test_company_mastering_target_postgres.py`)."""

import json
from pathlib import Path

import pytest

from edgar_warehouse.mdm.clean.company_prepare import write_company_manifest
from edgar_warehouse.mdm.clean.name_census import _sec_population
from edgar_warehouse.mdm.clean.name_frequency import write_name_frequency
from edgar_warehouse.mdm.clean.store import Conflict
from tests.mdm.test_clean_name_census import gleif
from tests.support.name_census_inputs import gleif_archive, gleif_reading
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
    return census_capture(tmp_path, documents(), CATALOG_ROWS)


def census_capture(tmp_path, found, rows):
    folder, population = write_capture(tmp_path / "capture", found, rows)
    (tmp_path / "g").mkdir()
    archive, metadata, _ = gleif_archive(tmp_path / "g", GLEIF)
    filers = [(f"{cik:010d}", d["name"], [n["name"] for n in d["formerNames"]]) for cik, d in found.items()]
    census = tmp_path / "name-census.json"
    write_name_frequency(capture=str(folder), population=str(population), gleif_metadata=str(metadata),
                         gleif_reading=gleif_reading(tmp_path / "r", archive, _sec_population(filers)[1], len(GLEIF)),
                         output=str(census))
    return folder, population, census


def prepare(tmp_path, capture, ciks=(APPLE, MSFT, ACME), output="bundle", **changes):
    folder, population, census = capture
    listed = tmp_path / f"documents-{output}.json"
    listed.write_text(json.dumps([key(c) for c in ciks]))
    args = {"capture": str(folder), "documents": str(listed), "population": str(population), "catalog": CATALOG,
            "name_census": str(census), "output": str(tmp_path / output), **PINS, **changes}
    return write_company_manifest(**args), Path(args["output"])


def test_the_manifest_is_content_addressed_and_written_once(tmp_path, capture):
    report, _ = prepare(tmp_path, capture)
    assert prepare(tmp_path, capture)[0] == report
    assert report["scope"]["ciks"] == [APPLE, MSFT, ACME] and report["target"] == "mastering"
    assert report["publication"]["publication_key"].startswith("capture-1:sec_submissions:")
    assert prepare(tmp_path, capture, revision=1)[0]["manifest"] != report["manifest"]


def test_a_different_catalog_is_a_different_publication(tmp_path, capture):
    first = prepare(tmp_path, capture)[0]
    other = census_capture(tmp_path / "other", documents(), catalog((APPLE, "Apple Inc.", "AAPL", "Nasdaq")))
    second = prepare(tmp_path / "other", other)[0]
    assert first["scope"]["receipts_sha256"] != second["scope"]["receipts_sha256"]
    assert first["publication"]["publication_key"] != second["publication"]["publication_key"]


def test_a_census_that_did_not_count_this_capture_is_refused(tmp_path, capture):
    _, _, census = census_capture(tmp_path / "other", documents(), catalog())
    with pytest.raises(Conflict, match="did not count"):
        prepare(tmp_path, capture, name_census=str(census))


def test_a_document_outside_the_population_is_refused(tmp_path, capture):
    folder, population, census = capture
    population.write_text(json.dumps([key(APPLE), key(MSFT)]))
    with pytest.raises(Conflict, match="did not count"):
        prepare(tmp_path, capture)


def test_a_document_that_differs_from_its_receipt_is_refused(tmp_path, capture):
    folder, *_ = capture
    (folder / "bronze" / key(MSFT).removeprefix("warehouse/bronze/")).write_text(json.dumps({"name": "CHANGED"}))
    with pytest.raises(Conflict, match="differs from its receipt"):
        prepare(tmp_path, capture)


def test_a_bundle_names_main_documents_only_and_at_most_512(tmp_path, capture):
    folder, population, census = capture
    listed = tmp_path / "documents.json"
    too_many = [f"bronze/main/{n}.json" for n in range(513)]
    for keys, message in [([CATALOG], "main submissions documents only"), ([], "1..512 distinct"),
                          (too_many, "1..512 distinct")]:
        listed.write_text(json.dumps(keys))
        with pytest.raises(ValueError, match=message):
            write_company_manifest(capture=str(folder), documents=str(listed), population=str(population),
                                   catalog=CATALOG, name_census=str(census), output=str(tmp_path / "x"), **PINS)
