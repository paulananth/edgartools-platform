"""ticket 169: the `silver.derive` worker rebuilds a derived silver table, leaves a
receipt of its keys, and its verifier reads the table back. Every name and number
here is invented."""

from __future__ import annotations

import contextlib
import copy
import json

import pytest
from sqlalchemy import create_engine, text

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
from tests.support.patching import checked

FOLDER = files.sources_root() / "sec.company-facts"
TABLES = ("silver-company-fact.yaml", "silver-company-line-item.yaml", "silver-company-line-item-input.yaml",
          "silver-company-measure.yaml", "silver-company-measure-input.yaml")


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
        monkeypatch.setattr(measures, "from_company", lambda mdm, keys: {k: measure_tests.COMPANIES[k] for k in keys
                                                                         if k in measure_tests.COMPANIES})
        yield runtime


def test_line_items_are_rebuilt_from_the_facts_and_the_verifier_reads_them_back(silver_store):
    land(PostgresSink(silver_store), "company_fact", copy.deepcopy(line_tests.FACTS))
    store = Artifacts()
    out = silver_derive.execute(envelope("line_items"), store)
    receipt = json.loads(store.written[out["uri"]])
    with silver_store.connect() as conn:
        held = conn.execute(text("SELECT count(*) FROM silver.company_line_item")).scalar()
    assert receipt["rows"] == held > 0 and receipt["table"] == "company_line_item"
    again = Artifacts()
    silver_derive.execute(envelope("line_items"), again)  # a second run rebuilds the same table
    assert again.written == store.written
    assert silver_derive.check({**envelope("line_items"), "candidate": {"uri": out["uri"], "sha256": "x"}}, store) == (
        {"silver.derived": True}, [])


def test_the_verifier_refuses_a_table_that_no_longer_matches_its_receipt(silver_store):
    land(PostgresSink(silver_store), "company_fact", copy.deepcopy(line_tests.FACTS))
    store = Artifacts()
    out = silver_derive.execute(envelope("line_items"), store)
    with silver_store.begin() as conn:
        conn.execute(text("DELETE FROM silver.company_line_item WHERE ctid IN "
                          "(SELECT ctid FROM silver.company_line_item LIMIT 1)"))
    with pytest.raises(ValueError, match="differs from the table"):
        silver_derive.check({**envelope("line_items"), "candidate": {"uri": out["uri"], "sha256": "x"}}, store)


def test_a_build_without_the_master_database_is_refused(silver_store, monkeypatch):
    monkeypatch.setattr(silver_derive, "engines", lambda: (silver_store, None))
    with pytest.raises(ValueError, match="reads each company.s master: source the loader file"):
        silver_derive.execute(envelope("measures"), Artifacts())


def test_measures_are_rebuilt_from_the_line_items(silver_store):
    land(PostgresSink(silver_store), "company_line_item", copy.deepcopy(measure_tests.LINES))
    store = Artifacts()
    out = silver_derive.execute(envelope("measures"), store)
    assert json.loads(store.written[out["uri"]])["rows"] > 0
    assert silver_derive.check({**envelope("measures"), "candidate": {"uri": out["uri"], "sha256": "x"}}, store)[0] == {
        "silver.derived": True}


def test_each_input_table_is_its_own_build_over_the_same_query(silver_store):
    land(PostgresSink(silver_store), "company_fact", copy.deepcopy(line_tests.FACTS))
    land(PostgresSink(silver_store), "company_line_item", copy.deepcopy(measure_tests.LINES))
    for build, table in (("line_item_inputs", "company_line_item_input"), ("measure_inputs", "company_measure_input")):
        store = Artifacts()
        out = silver_derive.execute(envelope(build), store)
        receipt = json.loads(store.written[out["uri"]])
        with silver_store.connect() as conn:
            held = conn.execute(text(f"SELECT count(*) FROM silver.{table}")).scalar()
        assert receipt["table"] == table and receipt["rows"] == held > 0


def test_an_unknown_build_or_check_is_refused(silver_store):
    with pytest.raises(ValueError, match="builds one of"):
        silver_derive.execute(envelope("other"), Artifacts())
    with pytest.raises(ValueError, match="verifies silver.derived only"):
        silver_derive.execute(envelope("line_items", checks=("x",)), Artifacts())


def test_a_build_that_gives_no_rows_from_a_source_that_holds_rows_is_refused(silver_store, monkeypatch):
    from edgar_warehouse.financials import line_items

    land(PostgresSink(silver_store), "company_fact", copy.deepcopy(line_tests.FACTS))
    checked(monkeypatch, line_items, "build", lambda *a, **k: {})  # a build that wrote nothing
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
    land(sink, "company_line_item", copy.deepcopy(measure_tests.LINES))
    with silver_store.connect() as conn:
        whole = conn.execute(text("SELECT count(DISTINCT company_key) FROM silver.company_line_item")).scalar()
    one = measure_tests.LINES[0]["company_key"]
    land(sink, "company_line_item", [r for r in copy.deepcopy(measure_tests.LINES) if r["company_key"] == one])
    with silver_store.connect() as conn:
        left = conn.execute(text("SELECT count(DISTINCT company_key) FROM silver.company_line_item")).scalar()
    assert whole > 1 and left == 1


def test_links_land_as_one_row_a_period_and_a_second_build_keeps_them(postgres, monkeypatch):
    """`silver links`: the table built whole from the stored records, each build given the last one's links."""
    from edgar_warehouse.mastering import links, store as stores

    admin, _ = postgres
    edge = {"relationship_id": "invented", "type": "ISSUED_BY", "scope": "invented", "source_id": "a", "target_id": "b",
            "evidence": [{"assertion_id": "c"}], "periods": [{"valid_from": "2026-03-01T00:00:00+00:00",
                                                              "valid_from_basis": "observed", "valid_to": None,
                                                              "properties": {}}]}
    seen = []

    def calculate(db, policy, as_of, stored):
        seen.append(stored)
        return [edge], {"no_master": 2}

    with silver_database(admin) as (owner, runtime):
        silver.migrate(owner, runtime_role=RUNTIME)
        for name in ("relationship", "relationship-evidence", "relationship-path", "master-binding"):
            silver.register(owner, spec_file(files.ROOT / "silver" / f"silver-{name}.yaml", None), runtime_role=RUNTIME)
        monkeypatch.setattr(links, "calculate", calculate)
        monkeypatch.setattr(stores, "open_store", lambda engine: Master2())
        monkeypatch.setattr("edgar_warehouse.rules.registry.engine", lambda: Rules())
        monkeypatch.setattr("edgar_warehouse.rules.registry.policy", lambda conn, digest: {"relationships": {}})
        first = links.build(runtime, MasterPolicy(), "invented", "2026-11-06T00:00:00+00:00")
        links.build(runtime, MasterPolicy(), "invented", "2026-11-06T00:00:00+00:00")
        assert first == {"table": "relationship", "links": 1, "rows": 1, "bindings": 0, "waiting": {"no_master": 2}}
        assert seen[0] == {} and seen[1]["invented"]["periods"][0]["valid_from_basis"] == "observed"
        with runtime.connect() as conn:
            evidence = [tuple(r) for r in conn.execute(text("SELECT relationship_id, assertion_id FROM silver.relationship_evidence"))]
        assert evidence == [("invented", "c")]


def test_the_worker_no_longer_builds_links():
    with pytest.raises(ValueError, match="silver.derive builds one of"):
        silver_derive._build({"keys": {"build": "links", "silver": "relationship", "reads": "mastering_record"}})


@contextlib.contextmanager
def bare_tables(admin, facts: tuple, lines: tuple):
    """The two tables the floor reads, holding only company keys (each an expression over 1..count),
    behind a login with little memory and five seconds for a statement."""
    with silver_database(admin) as (owner, _):
        with owner.begin() as conn:
            conn.execute(text("CREATE SCHEMA silver"))
            conn.execute(text(f"CREATE TABLE silver.company_fact AS SELECT ({facts[0]})::text AS company_key "
                              f"FROM generate_series(1, {facts[1]}) n"))
            conn.execute(text(f"CREATE TABLE silver.company_line_item AS SELECT ({lines[0]})::text AS company_key "
                              f"FROM generate_series(1, {lines[1]}) n"))
        small = create_engine(owner.url, connect_args={"options": "-c work_mem=64kB -c statement_timeout=5000"})
        try:
            yield small
        finally:
            small.dispose()


def test_the_floor_is_answered_in_seconds_over_a_source_larger_than_memory(postgres):
    admin, _ = postgres
    with bare_tables(admin, ("n % 20000", 400000), ("n % 20000", 20000)) as small:
        silver_derive._floor(small, "line_items", 20000)


def test_the_floor_refuses_a_company_the_source_does_not_hold(postgres):
    admin, _ = postgres
    with bare_tables(admin, ("n", 3), ("n", 5)) as small:
        with pytest.raises(ValueError, match="holds 2 companies that silver.company_fact does not"):
            silver_derive._floor(small, "line_items", 5)


class Rules:
    """The Rules Database: links.build reads the policy there."""
    def connect(self):
        from contextlib import nullcontext

        return nullcontext(None)

    def dispose(self):
        pass


class MasterPolicy(Master):
    def connect(self):
        from contextlib import nullcontext

        return nullcontext(None)


class Master2:
    def close(self):
        pass

    def bindings(self):
        return []
