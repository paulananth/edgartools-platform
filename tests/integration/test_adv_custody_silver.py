"""Form ADV custody rows in silver (ticket 01).

The custody reading on invented Schedule D 5.K(3) rows, landed into `adv_custody`
(`rules/sources/iapd.adv/silver-custody.yaml`) on a disposable PostgreSQL 16. A row lands once, with
the MDM ids of its adviser (by its filing) and its custodian (by its custodian id), and the amount it
holds as a whole number; a repeat lands nothing. The Companies are fixture masters standing in for the
two targets' records. Invented values only.
"""

from __future__ import annotations

import copy

from sqlalchemy import text

from edgar_warehouse.rules import files
from edgar_warehouse.silver_writer import database as silver
from edgar_warehouse.silver_writer import spec as silver_spec
from edgar_warehouse.silver_writer.cli import spec_file
from edgar_warehouse.silver_writer.sink import PostgresSink
from edgar_warehouse.silver_writer.writer import MdmIds, land
from tests.support import masters
from tests.integration import test_mdm_postgres as core
from tests.integration.test_silver_writer_postgres import RUNTIME, silver_database

FOLDER = files.ROOT / "sources" / "iapd.adv"
FILINGS, CUSTODIANS = "iapd.adv.filings.v1", "iapd.adv.custodians.v1"
# Two custody rows of one filing: a broker-dealer named by its number, and a related person named by its name.
ROWS = [
    {"filing_id": "F1", "row": 1, "custodian_id": "bd:8-00001", "related_person": "N", "amount": "1500000000", "published": "2026-06-30T00:00:00Z"},
    {"filing_id": "F1", "row": 2, "custodian_id": "name:EXAMPLE TRUST CO", "related_person": "Y", "amount": "250000", "published": "2026-06-30T00:00:00Z"},
]


def test_the_reading_columns_are_the_specs():
    reading = set(files.load(FOLDER / "custody-csv.yaml")["read"]["tables"]["custody_facts"]["columns"])
    columns = {c["name"] for c in silver_spec.check(files.load(FOLDER / "silver-custody.yaml"))["columns"]}
    assert columns == reading  # the writer refuses a field the spec does not name


def test_a_custody_row_lands_once_with_both_companies_and_its_amount(database):
    masters.seed(database.application, [
        core.source(key="F1", source_code=FILINGS, kind="company", fields={}, identifiers={"crd": "999001"}),
        core.source(key="bd:8-00001", source_code=CUSTODIANS, kind="company", fields={}, identifiers={"bd_number": "8-00001"}),
        core.source(key="name:EXAMPLE TRUST CO", source_code=CUSTODIANS, kind="company", fields={}, identifiers={})])  # no identifier: it binds to nothing
    with silver_database(database.admin) as (owner, runtime):
        silver.migrate(owner, runtime_role=RUNTIME)
        spec = spec_file(FOLDER / "silver-custody.yaml", None)
        assert silver.register(owner, spec, runtime_role=RUNTIME)["created"] is True
        sink, ids = PostgresSink(runtime), MdmIds(database.application)
        assert land(sink, spec["table"], copy.deepcopy(ROWS), ids)["inserted"] == 2
        assert land(sink, spec["table"], copy.deepcopy(ROWS), ids)["inserted"] == 0  # the same rows change nothing
        with runtime.connect() as conn:
            rows = conn.execute(text(
                "SELECT row, amount, adviser_mdm_id IS NOT NULL, custodian_mdm_id IS NOT NULL, "
                "adviser_mdm_id = (SELECT adviser_mdm_id FROM silver.adv_custody WHERE row = 1) "
                "FROM silver.adv_custody ORDER BY row")).all()
    # The broker-dealer custodian finds its Company; one named only by its name has no identifier to
    # match by, so its id stays empty (`silver refresh-ids` fills it when it is mastered): ticket 01's name_id part.
    assert [(r[0], r[1], r[2], r[3], r[4]) for r in rows] == [(1, 1500000000, True, True, True), (2, 250000, True, False, True)]
