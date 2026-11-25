"""Form ADV custody rows in silver (ticket 01).

The custody reading on invented Schedule D 5.K(3) rows, landed into `adv_custody`
(`sources/iapd.adv/silver-custody.yaml`) on a disposable PostgreSQL 16. A row lands once, with
the MDM ids of its adviser (by its filing) and its custodian (by its custodian id), and the amount it
holds as a whole number; a repeat lands nothing. The Companies are fixture masters standing in for the
two targets' records. Invented values only.
"""

from __future__ import annotations

import copy

from sqlalchemy import text

from edgar_warehouse.mastering import links
from edgar_warehouse.rules import files
from edgar_warehouse.silver_writer import database as silver
from edgar_warehouse.silver_writer import spec as silver_spec
from edgar_warehouse.silver_writer.cli import spec_file
from edgar_warehouse.silver_writer.sink import PostgresSink
from edgar_warehouse.silver_writer.writer import land
from tests.support import masters
from tests.integration import test_mdm_postgres as core
from tests.integration.test_silver_writer_postgres import RUNTIME, silver_database

FOLDER = files.sources_root() / "iapd.adv"
FILINGS, CUSTODIANS = "iapd.adv.filings.v2", "iapd.adv.custodians.v1"
# Two custody rows of one filing: a broker-dealer named by its number, and a related person named by its name.
ROWS = [
    {"filing_id": "F1", "row": 1, "custodian_id": "bd:8-00001", "related_person": "N", "amount": "1500000000", "published": "2026-06-30T00:00:00Z"},
    {"filing_id": "F1", "row": 2, "custodian_id": "name:EXAMPLE TRUST CO", "related_person": "Y", "amount": "250000", "published": "2026-06-30T00:00:00Z"},
]


def test_the_reading_columns_are_the_specs():
    reading = set(files.load(FOLDER / "custody-csv.yaml")["read"]["tables"]["custody_facts"]["columns"])
    columns = {c["name"] for c in silver_spec.check(files.load(FOLDER / "silver-custody.yaml"))["columns"]}
    assert columns == reading  # the writer refuses a field the spec does not name


def test_a_custody_row_lands_once_with_its_amount(database):
    with silver_database(database.admin) as (owner, runtime):
        silver.migrate(owner, runtime_role=RUNTIME)
        spec = spec_file(FOLDER / "silver-custody.yaml", None)
        assert silver.register(owner, spec, runtime_role=RUNTIME)["created"] is True
        sink = PostgresSink(runtime)
        assert land(sink, spec["table"], copy.deepcopy(ROWS))["inserted"] == 2
        assert land(sink, spec["table"], copy.deepcopy(ROWS))["inserted"] == 0  # the same rows change nothing
        with runtime.connect() as conn:
            rows = conn.execute(text("SELECT row, amount FROM silver.adv_custody ORDER BY row")).all()
    assert [(r[0], r[1]) for r in rows] == [(1, 1500000000), (2, 250000)]


def test_the_custody_fact_links_to_the_master_without_copying_its_name(database):
    engine = database.application
    role = engine.url.username
    silver.migrate(database.admin, runtime_role=role)
    for path in (FOLDER / "silver-custody.yaml", files.ROOT / "silver/silver-master-binding.yaml"):
        silver.register(database.admin, spec_file(path, None), runtime_role=role)

    fact = ROWS[0]
    name = "Example Clearing Company"
    ids = masters.seed(engine, [core.source(
        key=fact["custodian_id"], source_code=CUSTODIANS, fields={"name": name},
        identifiers={"bd_number": fact["custodian_id"].removeprefix("bd:")},
    )])
    custodian = ids[fact["custodian_id"]]
    links.bind(engine)
    land(PostgresSink(engine), "adv_custody", [dict(fact)])

    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT f.*, b.master_id FROM silver.adv_custody f JOIN silver.master_binding b"
            " ON b.source_code = :source AND b.source_key = f.custodian_id AND b.kind = 'company'"
        ), {"source": CUSTODIANS}).mappings().one()
    assert (row["filing_id"], row["row"], row["amount"], row["master_id"]) == ("F1", 1, 1500000000, custodian)
    assert name not in row.values()
    fields = masters.bodies(engine)[custodian]["fields"]
    assert fields["name"]["value"] == name
    assert "amount" not in fields
