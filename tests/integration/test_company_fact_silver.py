"""Ticket 46: every filed company fact lands in silver's `company_fact`, read by
facts.yaml's `company_fact` table and linked to its Company by CIK. Every name
and number here is invented."""

from __future__ import annotations

import copy
import json

import pytest
from decimal import Decimal

from sqlalchemy import text

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, register_policy
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from edgar_warehouse.silver_writer import database as silver
from edgar_warehouse.silver_writer import spec as silver_spec
from edgar_warehouse.silver_writer.cli import spec_file
from edgar_warehouse.silver_writer.sink import PostgresSink
from edgar_warehouse.silver_writer.writer import MdmIds, land
from tests.integration import test_clean_mdm_postgres as core
from tests.integration import test_nport_link_start as cusip
from tests.integration.test_silver_writer_postgres import RUNTIME, silver_database

FOLDER = files.ROOT / "sources" / "sec.company-facts"
COMPANY = "sec.submissions.company.v1"
FILING = {"accn": "0000000042-26-000001", "fy": 2025, "fp": "FY", "form": "10-K", "filed": "2026-02-01"}


def document(cik) -> bytes:
    return json.dumps({"cik": cik, "facts": {
        "us-gaap": {"Revenues": {"label": "Revenues", "units": {"USD": [
            {"start": "2025-01-01", "end": "2025-12-31", "val": 123456789012345678901, "frame": "CY2025", **FILING},
            # The same end in the same filing, a quarter: its own period, its own key.
            {"start": "2025-10-01", "end": "2025-12-31", "val": 30, **FILING}]}},
                    "EarningsPerShareDiluted": {"units": {"EUR/shares": [{"end": "2025-12-31", "val": 1.25, **FILING}]}}},
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            {"end": "2026-01-15", "val": 7, "accn": "0000000042-26-000001", "form": "10-K", "filed": "2026-02-01"}]}}}}}).encode()


def rows(cik="0000000042") -> list[dict]:
    return SourceEngine(files.load(FOLDER / "facts.yaml")).read(document(cik)).tables["company_fact"]


def test_each_fact_is_a_row_with_its_period_currency_and_exact_figure():
    by_value = {r["value"]: r for r in rows()}
    assert set(by_value) == {"123456789012345678901", 30, "1.25", 7}
    year, quarter, eps, shares = (by_value[v] for v in ("123456789012345678901", 30, "1.25", 7))
    assert (year["period"], quarter["period"]) == ("2025-01-01/2025-12-31", "2025-10-01/2025-12-31")
    assert (eps["period"], eps["period_start"], eps["period_end"]) == ("2025-12-31", None, "2025-12-31")
    assert [r["currency"] for r in (year, eps, shares)] == ["USD", "EUR", None]
    assert (shares["taxonomy"], shares["fiscal_year_filed"], year["frame"]) == ("dei", None, "CY2025")
    assert {r["company_key"] for r in rows()} == {"0000000042"} == {r["company_key"] for r in rows(42)}


def test_a_taxonomy_with_no_table_still_refuses_the_file():
    raw = document("0000000042").replace(b'"dei":', b'"newtax":')
    with pytest.raises(SourceRejected, match="lookup"):
        SourceEngine(files.load(FOLDER / "facts.yaml")).read(raw)


def test_the_rows_fit_the_silver_spec():
    spec = silver_spec.check(files.load(FOLDER / "silver-company-fact.yaml"))
    assert set(files.load(FOLDER / "facts.yaml")["read"]["tables"]["company_fact"]["columns"]) == {
        c["name"] for c in spec["columns"]}


def test_facts_land_exact_once_and_find_their_company(database):
    core.register_reading(database, COMPANY, core.contract_body())
    with database.admin.begin() as conn:
        policy = register_policy(conn, copy.deepcopy(files.policy()))
    cusip.apply(MergeStage(Store(database.application)), policy, "masters", [
        core.source(key="0000000042", source_code=COMPANY, kind="company", fields={},
                    identifiers={"cik": "0000000042"})], 1)
    company = core.bindings(database, COMPANY)["0000000042"]
    landed_rows = rows()
    with silver_database(database.admin) as (owner, runtime):
        silver.migrate(owner, runtime_role=RUNTIME)
        spec = spec_file(FOLDER / "silver-company-fact.yaml", None)
        assert silver.register(owner, spec, runtime_role=RUNTIME)["created"] is True
        sink, ids = PostgresSink(runtime), MdmIds(database.application)
        assert land(sink, spec["table"], copy.deepcopy(landed_rows), ids)["inserted"] == 4
        again = land(sink, spec["table"], copy.deepcopy(landed_rows), ids)  # the same file changes nothing
        assert (again["inserted"], again["changed"]) == (0, 0)
        with runtime.connect() as conn:
            landed = conn.execute(text("SELECT value, company_mdm_id FROM silver.company_fact")).all()
    assert sorted(v for v, _ in landed) == sorted(Decimal(x) for x in ("123456789012345678901", "30", "1.25", "7"))
    assert {str(m) for _, m in landed} == {company}


def test_a_figure_silver_cannot_hold_exactly_is_refused_never_rounded(database):
    too_fine = [{**rows()[0], "value": "0.00000000001", "period": "2025-01-01/2025-01-31"}]
    with silver_database(database.admin) as (owner, runtime):
        silver.migrate(owner, runtime_role=RUNTIME)
        spec = spec_file(FOLDER / "silver-company-fact.yaml", None)
        silver.register(owner, spec, runtime_role=RUNTIME)
        with pytest.raises(Blocked, match="not its column's type"):
            land(PostgresSink(runtime), spec["table"], too_fine, MdmIds(database.application))
        with runtime.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM silver.company_fact")) == 0
