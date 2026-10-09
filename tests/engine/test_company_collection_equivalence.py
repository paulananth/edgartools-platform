"""Qualify collection/join behavior only; full Company preparation stays retained."""
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from tests.support.retired_company_preparation import _business_addresses, _catalog_tickers, _filed_forms
from edgar_warehouse.rules.source_engine import SourceEngine
from edgar_warehouse.workers import source_combine
from tests.engine.test_source_combine import envelope, group, join, plan, reading, table


def fixtures():
    companies = [{"cik": 1}, {"cik": 2}, {"cik": 3}]
    filings = [{"cik": cik, "form": form, "last_sync_run_id": "run"} for cik, form in
               [(1, "10-Q"), (1, "8-K"), (1, "10-K"), (1, "10-K"), (2, "20-F"), (2, "6-K"), (3, ""), (None, "13F-HR")]]
    tickers = [{"cik": cik, "ticker": ticker, "source_rank": rank, "last_sync_run_id": "catalog"} for cik, ticker, rank in
               [(1, "B", 2), (1, "A", 1), (1, "A", 3), (2, "UK", 1), (3, "", None), (None, "IGNORED", None)]]
    address = lambda street: {"street": street, "street2": None, "city": "City", "region": "DE", "postal_code": "12345", "country": "US"}
    addresses = [{"cik": cik, "address_type": kind, "street1": street, "street2": "", "city": "City",
                  "zip_code": "12345", "state_or_country": "DE", "country_code": None, "last_sync_run_id": "run", "address": address(street)}
                 for cik, kind, street in [(1, "business", "first"), (1, "mailing", "mail"), (1, "business", "last"), (2, "business", "foreign")]]
    addresses[-1].update(state_or_country="", country_code="X0", address={
        "street": "foreign", "street2": None, "city": "City", "region": None, "postal_code": "12345", "country": "GB"})
    return companies, filings, tickers, addresses


def combination():
    return plan({
        "forms": group("ref", "filings", "cik", "form", order_by=("form",), distinct=True, checks={"last_sync_run_id": "run"}),
        "tickers": group("ref", "tickers", "cik", "ticker", order_by=("source_rank", "ticker"), distinct=True, checks={"last_sync_run_id": "catalog"}),
        "addresses": group("ref", "addresses", "cik", "address", mode="last", where={"address_type": "business"}, checks={"last_sync_run_id": "run"})},
        {"companies": table("main", "companies", {"forms": join("forms"), "tickers": join("tickers"), "business_address": join("addresses")})})


def parquet(tmp_path, name, rows):
    path = tmp_path / name
    pq.write_table(pa.Table.from_pylist([{k: v for k, v in row.items() if k != "address"} for row in rows]), path)
    return pq.ParquetFile(path)


def projected(refs):
    # Use the configured engine's text-null policy before grouping, as a feed
    # must declare; the collector itself does not guess empty-string semantics.
    spec = {"read": {"format": "json", "tables": {
        "filings": {"each": "filings", "columns": {"cik": {"integer": {"path": "cik"}},
            "form": {"text": {"path": "form", "trim": False, "null_if": [""]}}, "last_sync_run_id": {"text": {"path": "last_sync_run_id"}}}},
        "tickers": {"each": "tickers", "columns": {"cik": {"integer": {"path": "cik"}},
            "ticker": {"text": {"path": "ticker", "trim": False, "null_if": [""]}}, "source_rank": {"integer": {"path": "source_rank"}},
            "last_sync_run_id": {"text": {"path": "last_sync_run_id"}}}},
        "addresses": {"each": "addresses", "columns": {"cik": {"integer": {"path": "cik"}},
            "address_type": {"text": {"path": "address_type"}}, "address": {"value": {"path": "address"}},
            "last_sync_run_id": {"text": {"path": "last_sync_run_id"}}}}}}}
    return SourceEngine(spec).read(json.dumps(refs).encode()).tables


def test_configured_collection_matches_retained_forms_tickers_and_address_selection(tmp_path):
    companies, filings, tickers, addresses = fixtures()
    expected = {"forms": _filed_forms({"run_id": "run"}, parquet(tmp_path, "filings.parquet", filings)),
                "tickers": _catalog_tickers({"run_id": "catalog"}, parquet(tmp_path, "tickers.parquet", tickers)),
                "business_address": _business_addresses({"run_id": "run"}, parquet(tmp_path, "addresses.parquet", addresses))}
    store = Artifacts()
    refs = {"main": reading(store, tmp_path, {"companies": companies}), "ref": reading(store, tmp_path, projected({
        "filings": filings, "tickers": tickers, "addresses": addresses}))}
    work = envelope(store, tmp_path, combination(), refs)
    result = source_combine.execute(work, store)
    assert source_combine.verify({**work, "candidate": result}, store) == ({source_combine.CHECK: True}, [])
    actual = store.json(result)["artifacts"][0]["tables"]["companies"]
    assert actual == [{**company, **{field: values.get(company["cik"], None if field == "business_address" else [])
                                   for field, values in expected.items()}} for company in companies]
    assert actual[0]["forms"] == ["10-K", "10-Q", "8-K"]
    assert actual[0]["tickers"] == ["A", "B"]
    assert actual[0]["business_address"]["street"] == "last"
    assert actual[1]["business_address"]["country"] == "GB"
    # Address derivation was provided as explicit fixture input; this qualifies
    # collection/selection, not Company raw-address conversion or census joins.


@pytest.mark.parametrize("source", ["filings", "tickers", "addresses"])
def test_capture_mismatch_is_refused_even_for_a_skipped_key_or_filtered_row(tmp_path, source):
    companies, filings, tickers, addresses = fixtures()
    refs = {"filings": filings, "tickers": tickers, "addresses": addresses}
    index = 1 if source == "addresses" else -1
    refs[source][index]["last_sync_run_id"] = "foreign"
    oracle = {"filings": _filed_forms, "tickers": _catalog_tickers, "addresses": _business_addresses}[source]
    from edgar_warehouse.mdm.clean.store import Conflict
    with pytest.raises(Conflict): oracle({"run_id": "catalog" if source == "tickers" else "run"}, parquet(tmp_path, "rows.parquet", refs[source]))
    store = Artifacts()
    work = envelope(store, tmp_path, combination(), {"main": reading(store, tmp_path, {"companies": companies}),
                    "ref": reading(store, tmp_path, projected(refs))})
    with pytest.raises(ValueError, match="row check failed"): source_combine.execute(work, store)
    assert not (tmp_path / "output").exists()
