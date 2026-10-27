"""Forms 3, 4 and 5 in silver: lines and owners, as SEC keeps them (ticket 25).

The SGML ownership reading on an invented joint filing, landed into
`ownership_line` and `ownership_owner` (`rules/sources/sec.ownership/silver-*.yaml`)
on a disposable PostgreSQL 16. A line lands once, with its issuer's MDM id and
its as-of and filing dates; each owner lands once, found as the Person the
ownership feed masters (its record key) or as a Company by its CIK (operator,
2026-10-22: "Lines + owners, as SEC (Recommended)"). No holding goes through
the Merge Stage. Invented values only.
"""

from __future__ import annotations

import copy

from sqlalchemy import text

from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, register_policy
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine
from edgar_warehouse.silver_writer import database as silver
from edgar_warehouse.silver_writer import spec as silver_spec
from edgar_warehouse.silver_writer.cli import spec_file
from edgar_warehouse.silver_writer.sink import PostgresSink
from edgar_warehouse.silver_writer.writer import MdmIds, land
from tests.engine.test_ownership_readings import ACCESSION, FILED, filing
from tests.engine.test_sgml_container import document, submission
from tests.integration import test_clean_mdm_postgres as core
from tests.integration import test_nport_link_start as nport
from tests.integration.test_silver_writer_postgres import RUNTIME, silver_database

FOLDER = files.ROOT / "sources" / "sec.ownership"
LINES = ("non_derivative_transaction", "non_derivative_holding", "derivative_transaction", "derivative_holding")
PERSON, COMPANY = "sec.ownership.reporting_owner.v1", "sec.submissions.company.v1"
ISSUER, HOLDER, FUND = "0000000001", "0000000002", "0000000003"  # invented CIKs
SECOND_OWNER = (f"<reportingOwner><reportingOwnerId><rptOwnerCik>{FUND}</rptOwnerCik>"
                "<rptOwnerName>Example Fund LP</rptOwnerName></reportingOwnerId>"
                "<reportingOwnerRelationship><isTenPercentOwner>1</isTenPercentOwner></reportingOwnerRelationship>"
                "</reportingOwner>")


def joint_filing() -> dict:
    """An invented Form 4 two owners file jointly, read from its SGML submission."""
    body = filing().replace(b" <nonDerivativeTable>", SECOND_OWNER.encode() + b"\n <nonDerivativeTable>", 1)
    sgml = submission(document(b"form4.xml", b"<XML>\n" + body + b"</XML>"),
                      header=f"ACCESSION NUMBER:\t{ACCESSION}\nFILED AS OF DATE:\t{FILED}\n".encode())
    return SourceEngine(files.load(FOLDER / "ownership-sgml.yaml")).read(sgml).tables


def test_the_reading_columns_are_the_specs():
    sgml = files.load(FOLDER / "ownership-sgml.yaml")["read"]["tables"]
    line = {c["name"] for c in silver_spec.check(files.load(FOLDER / "silver-line.yaml"))["columns"]}
    owner = {c["name"] for c in silver_spec.check(files.load(FOLDER / "silver-owner.yaml"))["columns"]}
    assert set().union(*(sgml[t]["columns"] for t in LINES)) == line
    assert set(sgml["reporting_owner"]["columns"]) == owner


def test_a_joint_filings_lines_land_once_and_each_owner_finds_its_master(database):
    tables = joint_filing()
    lines = [row for t in LINES for row in tables[t]]
    owners = tables["reporting_owner"]
    assert (len(lines), len(owners)) == (2, 2)
    person_key = next(o["owner_record_key"] for o in owners if o["rpt_owner_cik"] == HOLDER)
    for code in (PERSON, COMPANY):  # fixture masters stand in for each contract's records
        core.register_reading(database, code, core.contract_body())
    with database.admin.begin() as conn:
        policy = register_policy(conn, copy.deepcopy(files.policy()))
    nport.apply(MergeStage(Store(database.application)), policy, "masters", [
        core.source(key=person_key, source_code=PERSON, kind="person", fields={}, identifiers={"cik": HOLDER}),
        core.source(key=ISSUER, source_code=COMPANY, kind="company", fields={}, identifiers={"cik": ISSUER}),
        core.source(key=FUND, source_code=COMPANY, kind="company", fields={}, identifiers={"cik": FUND})], 1)
    with silver_database(database.admin) as (owner, runtime):
        silver.migrate(owner, runtime_role=RUNTIME)
        sink, ids = PostgresSink(runtime), MdmIds(database.application)
        for name, rows in (("line", lines), ("owner", owners)):
            spec = spec_file(FOLDER / f"silver-{name}.yaml", None)
            assert silver.register(owner, spec, runtime_role=RUNTIME)["created"] is True
            assert land(sink, spec["table"], copy.deepcopy(rows), ids)["inserted"] == len(rows)
            again = land(sink, spec["table"], copy.deepcopy(rows), ids)  # the same filing changes nothing
            assert (again["inserted"], again["changed"]) == (0, 0)
        with runtime.connect() as conn:
            landed = list(conn.execute(text("SELECT * FROM silver.ownership_line ORDER BY line_table")).mappings())
            found = {r["rpt_owner_cik"]: r for r in conn.execute(text("SELECT * FROM silver.ownership_owner")).mappings()}
        entity = core.bindings(database)

    # Each line once, with its issuer, the date it holds at and the filing's date.
    assert [(r["line_table"], str(r["as_of"]), str(r["filed"]), str(r["issuer_mdm_id"])) for r in landed] == [
        ("non_derivative_holding", "2026-01-05", "2026-01-07", entity[ISSUER]),
        ("non_derivative_transaction", "2026-01-05", "2026-01-07", entity[ISSUER])]
    assert str(landed[1]["shares_owned_following_transaction"]) == "1100.0000000000"
    # The person owner is its Person; the fund, mastered as a Company, its Company.
    assert (str(found[HOLDER]["person_mdm_id"]), found[HOLDER]["company_mdm_id"]) == (entity[person_key], None)
    assert (found[FUND]["person_mdm_id"], str(found[FUND]["company_mdm_id"])) == (None, entity[FUND])
    assert {str(r["issuer_mdm_id"]) for r in found.values()} == {entity[ISSUER]}
