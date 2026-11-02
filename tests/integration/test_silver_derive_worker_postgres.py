"""ticket 169: the `silver.derive` worker rebuilds a derived silver table, leaves a
receipt of its keys, and its verifier reads the table back. Every name and number
here is invented."""

from __future__ import annotations

import copy
import json

import pytest
from sqlalchemy import text

from edgar_warehouse.financials import measures
from edgar_warehouse.rules import files
from edgar_warehouse.silver_writer import database as silver
from edgar_warehouse.silver_writer.cli import spec_file
from edgar_warehouse.silver_writer.sink import PostgresSink
from edgar_warehouse.silver_writer.writer import land
from edgar_warehouse.workers import silver_derive
from tests.integration import test_company_line_item_silver as line_tests
from tests.integration import test_company_measure_silver as measure_tests
from tests.integration.test_silver_land_worker_postgres import Artifacts
from tests.integration.test_silver_writer_postgres import RUNTIME, silver_database

FOLDER = files.ROOT / "sources" / "sec.company-facts"
TABLES = ("silver-company-fact.yaml", "silver-company-line-item.yaml", "silver-company-measure.yaml")


def envelope(build, checks=("silver.derived",)):
    wrote = silver_derive.BUILDS.get(build)
    return {"checks": list(checks), "output": f"memory://{build}.json",
            "keys": {"unit": build, "build": build, "silver": wrote, "reads": silver_derive.SOURCES.get(build)},
            "input": {"uri": "memory://in.json", "sha256": "invented"}}


class Master:
    """The MDM engine the worker opens; it only has to be disposed."""

    def dispose(self):
        pass


@pytest.fixture
def silver_store(postgres, monkeypatch):
    admin, _ = postgres
    with silver_database(admin) as (owner, runtime):
        silver.migrate(owner, runtime_role=RUNTIME)
        for name in TABLES:
            silver.register(owner, spec_file(FOLDER / name, None), runtime_role=RUNTIME)
        monkeypatch.setattr(silver_derive, "engines", lambda: (runtime, Master()))
        monkeypatch.setattr(runtime, "dispose", lambda: None)
        # the Company masters: none are registered, so no row finds a master id
        monkeypatch.setattr("edgar_warehouse.silver_writer.writer.MdmIds", lambda mdm: line_tests.no_masters)
        monkeypatch.setattr(measures, "from_company", lambda mdm, keys: {k: measure_tests.COMPANIES[k] for k in keys
                                                                         if k in measure_tests.COMPANIES})
        yield runtime


def test_line_items_are_rebuilt_from_the_facts_and_the_verifier_reads_them_back(silver_store):
    land(PostgresSink(silver_store), "company_fact", copy.deepcopy(line_tests.FACTS), line_tests.no_masters)
    store = Artifacts()
    out = silver_derive.execute(envelope("line_items"), store)
    receipt = json.loads(store.written[out["uri"]])
    with silver_store.connect() as conn:
        held = conn.execute(text("SELECT count(*) FROM silver.company_line_item")).scalar()
    assert receipt["rows"] == held > 0 and receipt["table"] == "company_line_item"
    again = Artifacts()
    silver_derive.execute(envelope("line_items"), again)  # a second run rebuilds the same table
    assert again.written == store.written
    assert silver_derive.verify({**envelope("line_items"), "candidate": {"uri": out["uri"], "sha256": "x"}}, store) == (
        {"silver.derived": True}, [])


def test_the_verifier_refuses_a_table_that_no_longer_matches_its_receipt(silver_store):
    land(PostgresSink(silver_store), "company_fact", copy.deepcopy(line_tests.FACTS), line_tests.no_masters)
    store = Artifacts()
    out = silver_derive.execute(envelope("line_items"), store)
    with silver_store.begin() as conn:
        conn.execute(text("DELETE FROM silver.company_line_item WHERE ctid IN "
                          "(SELECT ctid FROM silver.company_line_item LIMIT 1)"))
    with pytest.raises(ValueError, match="differs from the table"):
        silver_derive.verify({**envelope("line_items"), "candidate": {"uri": out["uri"], "sha256": "x"}}, store)


def test_a_build_without_the_master_database_is_refused(silver_store, monkeypatch):
    monkeypatch.setattr(silver_derive, "engines", lambda: (silver_store, None))
    with pytest.raises(ValueError, match="MDM_DATABASE_URL"):
        silver_derive.execute(envelope("measures"), Artifacts())


def test_measures_are_rebuilt_from_the_line_items(silver_store):
    land(PostgresSink(silver_store), "company_line_item", copy.deepcopy(measure_tests.LINES), line_tests.no_masters)
    store = Artifacts()
    out = silver_derive.execute(envelope("measures"), store)
    assert json.loads(store.written[out["uri"]])["rows"] > 0
    assert silver_derive.verify({**envelope("measures"), "candidate": {"uri": out["uri"], "sha256": "x"}}, store)[0] == {
        "silver.derived": True}


def test_an_unknown_build_or_check_is_refused(silver_store):
    with pytest.raises(ValueError, match="builds one of"):
        silver_derive.execute(envelope("other"), Artifacts())
    with pytest.raises(ValueError, match="verifies silver.derived only"):
        silver_derive.execute(envelope("line_items", checks=("x",)), Artifacts())


def test_a_build_that_gives_no_rows_from_a_source_that_holds_rows_is_refused(silver_store, monkeypatch):
    from edgar_warehouse.financials import line_items

    land(PostgresSink(silver_store), "company_fact", copy.deepcopy(line_tests.FACTS), line_tests.no_masters)
    monkeypatch.setattr(line_items, "build", lambda *a, **k: {})  # a build that wrote nothing
    with pytest.raises(ValueError, match="is empty although"):
        silver_derive.execute(envelope("line_items"), Artifacts())


def test_a_unit_that_names_other_tables_than_its_build_is_refused(silver_store):
    wrong = envelope("line_items")
    wrong["keys"]["reads"] = "company_line_item"
    with pytest.raises(ValueError, match="writes company_line_item and reads company_fact"):
        silver_derive.execute(wrong, Artifacts())


def test_a_snapshot_delivery_of_some_companies_removes_the_others(silver_store):
    """Why a derived table is rebuilt whole: the writer deletes every row a snapshot delivery lacks."""
    sink = PostgresSink(silver_store)
    land(sink, "company_line_item", copy.deepcopy(measure_tests.LINES), line_tests.no_masters)
    with silver_store.connect() as conn:
        whole = conn.execute(text("SELECT count(DISTINCT company_key) FROM silver.company_line_item")).scalar()
    one = measure_tests.LINES[0]["company_key"]
    land(sink, "company_line_item", [r for r in copy.deepcopy(measure_tests.LINES) if r["company_key"] == one],
         line_tests.no_masters)
    with silver_store.connect() as conn:
        left = conn.execute(text("SELECT count(DISTINCT company_key) FROM silver.company_line_item")).scalar()
    assert whole > 1 and left == 1
