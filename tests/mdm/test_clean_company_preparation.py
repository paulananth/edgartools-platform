"""Company preparation from the receipt-bound raw capture (Issue 20 L4): the
configured workers read each main document, the Name Census and the exchange
catalog, combine them per Company, and the bundle re-verifies every worker."""

import json
from pathlib import Path

import pytest

from edgar_warehouse.mdm.clean import limits
from edgar_warehouse.mdm.clean.company_prepare import prepare_company_bundle, verify_company_bundle
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
    return prepare_company_bundle(**args), Path(args["output"])


def records(bundle):
    batches = json.loads((bundle / "manifest.json").read_text())["batches"]
    return {r["cik"]: r for b in batches for r in map(json.loads, (bundle / b["input"]["path"]).read_text().splitlines())}


def test_the_bundle_is_pinned_verified_and_idempotent(tmp_path, capture):
    report, bundle = prepare(tmp_path, capture)
    assert verify_company_bundle(str(bundle), expected=report)["records"] == 3
    assert prepare(tmp_path, capture)[0] == report
    manifest = json.loads((bundle / "manifest.json").read_text())
    (batch,) = manifest["batches"]
    assert batch["input"]["path"] == "records.0.jsonl" and batch["checkpoint"] == 1
    assert batch["input"]["record_count"] == 3 and manifest["scope"]["ciks"] == [APPLE, MSFT, ACME]
    assert batch["input"]["publication"]["publication_key"].startswith("capture-1:sec_submissions:")


def test_forms_tickers_and_address_come_from_the_documents_and_the_catalog(tmp_path, capture):
    found = records(prepare(tmp_path, capture)[1])
    assert found[APPLE]["forms"] == ["10-K", "10-Q"]
    assert found[APPLE]["tickers"] == ["AAPL", "APLE"]  # catalog rank order, listed once
    assert found[MSFT]["tickers"] == ["MSFT"] and found[ACME]["tickers"] == []
    assert found[APPLE]["business_address"]["street"] == "ONE APPLE PARK WAY"
    assert found[ACME]["business_address"]["country"] == "GB"
    assert found[APPLE]["last_sync_run_id"] == "capture-1"


def test_a_filer_without_a_business_address_carries_none(tmp_path):
    found = documents({MSFT: document(MSFT, "MICROSOFT CORP")})
    capture = census_capture(tmp_path, found, CATALOG_ROWS)
    assert records(prepare(tmp_path, capture)[1])[MSFT].get("business_address") is None


def test_each_record_names_its_bronze_document_and_its_name_census_entry(tmp_path, capture):
    folder, *_ = capture
    receipts = {r["key"]: r["sha256"] for r in map(json.loads, (folder / "receipts.jsonl").read_text().splitlines())}
    found = records(prepare(tmp_path, capture)[1])
    for cik, record in found.items():
        assert record["_origin"]["bronze"] == {"object": key(cik), "sha256": receipts[key(cik)], "locator": "$"}
        assert record["raw_object_id"] == receipts[key(cik)]
    assert found[APPLE]["name_census"]["leis"][0][0] == "HWUPKR0MPOU8FGXBT394"


def test_a_different_catalog_is_a_different_publication(tmp_path, capture):
    first = prepare(tmp_path, capture)[0]
    other = census_capture(tmp_path / "other", documents(), catalog((APPLE, "Apple Inc.", "AAPL", "Nasdaq")))
    second = prepare(tmp_path / "other", other)[0]
    assert first["scope"]["receipts_sha256"] != second["scope"]["receipts_sha256"]


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


def test_an_existing_bundle_with_other_content_is_never_overwritten(tmp_path, capture):
    prepare(tmp_path, capture)
    with pytest.raises(Conflict, match="different content"):
        prepare(tmp_path, capture, revision=1)


@pytest.mark.parametrize("member", ["records.0.jsonl", "manifest.json", "name-census.json", "workers/proof.json"])
def test_a_changed_member_fails_verification(tmp_path, capture, member):
    report, bundle = prepare(tmp_path, capture)
    path = bundle / member
    data = path.read_bytes()
    path.write_bytes(data[:-2] + (b"0" if data[-2:-1] != b"0" else b"1") + data[-1:])  # same length
    with pytest.raises(Conflict, match="differs"):
        verify_company_bundle(str(bundle), expected=report)


def test_a_bundle_names_main_documents_only_and_at_most_512(tmp_path, capture):
    folder, population, census = capture
    listed = tmp_path / "documents.json"
    too_many = [f"bronze/main/{n}.json" for n in range(513)]
    for keys, message in [([CATALOG], "main submissions documents only"), ([], "1..512 distinct"),
                          (too_many, "1..512 distinct")]:
        listed.write_text(json.dumps(keys))
        with pytest.raises(ValueError, match=message):
            prepare_company_bundle(capture=str(folder), documents=str(listed), population=str(population),
                                   catalog=CATALOG, name_census=str(census), output=str(tmp_path / "x"), **PINS)


def test_a_bundle_is_cut_by_the_records_byte_budget_and_still_verifies(tmp_path, capture, monkeypatch):
    whole = prepare(tmp_path, capture, output="whole")[1]
    monkeypatch.setattr(limits, "BATCH_RECORD_BYTES", 1)  # past its first record, every record its own batch
    report, bundle = prepare(tmp_path, capture, output="cut")
    batches = json.loads((bundle / "manifest.json").read_text())["batches"]
    assert [b["input"]["record_count"] for b in batches] == [1, 1, 1]
    assert [(b["expected_checkpoint"], b["checkpoint"]) for b in batches] == [(0, 1), (1, 2), (2, 3)]
    assert len({b["consumer"] for b in batches}) == 1 and len({b["batch_id"] for b in batches}) == 3
    assert len({b["input"]["publication"]["publication_key"] for b in batches}) == 1
    assert verify_company_bundle(str(bundle), expected=report)["records"] == 3
    assert records(bundle) == records(whole)
