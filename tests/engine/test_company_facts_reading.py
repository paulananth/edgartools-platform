"""The company facts source extract (`rules/sources/sec.company-facts/facts.yaml`, ticket 45).

One table per taxonomy, one row per concept, its units kept whole; every figure
exact, a bigint or a big decimal, never a float (tickets 128 and 134; operator,
2026-10-22: "For financial projects never use integer's use only bigint or big
decimal"). A taxonomy with no table refuses the file (ticket 40). Every name and
number here is invented.
"""
import json
from decimal import Decimal

import pytest

from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected

CONTRACT = files.load(files.ROOT / "sources" / "sec.company-facts" / "facts.yaml")
TAXONOMIES = ["dei", "ecd", "ffd", "ifrs-full", "invest", "rxp", "srt", "us-gaap", "vip"]


def document(cik=123, taxonomy="us-gaap", units=None) -> bytes:
    units = units if units is not None else {"USD": [{"start": "2025-01-01", "end": "2025-12-31", "val": 1500,
                                                     "accn": "0000000000-26-000001", "fy": 2025, "fp": "FY",
                                                     "form": "10-K", "filed": "2026-02-01"}]}
    return json.dumps({"cik": cik, "entityName": "Example Widgets Inc",
                       "facts": {taxonomy: {"Revenues": {"label": "Revenues", "description": "An invented description.",
                                                         "units": units}}}}).encode()


def read(raw: bytes) -> dict:
    return SourceEngine(CONTRACT).read(raw).tables


def test_one_table_per_taxonomy_and_every_taxonomy_is_known():
    tables = read(document())
    assert set(tables) == {"taxonomies", "company_fact"} | {"concepts_" + t.replace("-", "_") for t in TAXONOMIES}
    assert sorted(CONTRACT["read"]["references"]["taxonomies"]) == TAXONOMIES
    assert tables["taxonomies"] == [{"taxonomy": "us-gaap", "known": True}]
    [row] = tables["concepts_us_gaap"]
    assert {k: row[k] for k in ("cik", "concept", "label")} == {"cik": 123, "concept": "Revenues", "label": "Revenues"}


def test_every_taxonomy_table_reads_the_same_columns_from_its_own_taxonomy():
    tables = CONTRACT["read"]["tables"]
    for taxonomy in TAXONOMIES:
        table = tables["concepts_" + taxonomy.replace("-", "_")]
        assert table["each"]["entries"]["path"] == f"facts.{taxonomy}"
        assert table["columns"] == tables["concepts_us_gaap"]["columns"], taxonomy


@pytest.mark.parametrize("cik", [123, "0000000123", "0000123"])
def test_the_cik_is_one_bigint_whether_filed_as_a_number_or_as_padded_text(cik):
    assert read(document(cik=cik))["concepts_us_gaap"][0]["cik"] == 123


def test_every_figure_is_exact_never_a_float():
    figures = ["2.50", "0.1000000000000000055511151231257827", "12345678901234567.89", "-0.000001",
               "123456789012345678901", "1500"]
    raw = document(units={"USD": [{"end": "2025-12-31", "val": "FIGURE"}]})
    for figure in figures:
        body = raw.replace(b'"FIGURE"', figure.encode())
        [fact] = read(body)["concepts_us_gaap"][0]["units"]["USD"]
        assert not isinstance(fact["val"], float), figure
        assert Decimal(str(fact["val"])) == Decimal(figure)
        assert str(fact["val"]) == figure, "the filed digits are kept as filed"


def test_a_fact_lands_whole_with_every_field_silver_needs():
    fact = {"start": "2025-01-01", "end": "2025-12-31", "val": 1500, "accn": "0000000000-26-000001", "fy": 2025,
            "fp": "FY", "form": "10-K", "filed": "2026-02-01", "frame": "CY2025"}
    [landed] = read(document(units={"USD": [fact]}))["concepts_us_gaap"][0]["units"]["USD"]
    assert landed == fact


@pytest.mark.parametrize("raw", [
    b'[]', b'{"cik": 1, "facts": []}', b'{"facts": {"us-gaap": {}}}', b'{"cik": null, "facts": {}}',
    b'{"cik": 1, "facts": {"us-gaap": [1]}}', b'{"cik": 1, "facts": {"us-gaap": {"Revenues": {"label": "x"}}}}',
    b'{"cik": 1, "facts": {"us-gaap": {"Revenues": 5}}}'])
def test_a_file_of_another_shape_is_refused_never_dropped(raw):
    with pytest.raises(SourceRejected):
        read(raw)


def test_a_taxonomy_with_no_table_refuses_the_file():
    with pytest.raises(SourceRejected) as refused:
        read(document(taxonomy="new-taxonomy"))
    assert refused.value.code == "lookup_missing"


def test_an_empty_document_lands_nothing_and_a_concept_with_no_facts_lands():
    assert all(rows == [] for rows in read(b"{}").values())
    [row] = read(document(units={}))["concepts_us_gaap"]
    assert row["units"] == {}
