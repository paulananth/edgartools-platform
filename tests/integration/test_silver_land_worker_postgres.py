"""ticket 169: the `silver.land` worker lands one reading's table in silver,
leaves a receipt, and its verifier reads silver back. Every name and number
here is invented."""

from __future__ import annotations

import copy
import json

import pytest
from sqlalchemy import text

from edgar_warehouse.rules import files
from edgar_warehouse.silver_writer import database as silver
from edgar_warehouse.silver_writer.cli import spec_file
from edgar_warehouse.workers import silver_land
from tests.integration.test_company_fact_silver import FOLDER, rows
from tests.integration.test_silver_writer_postgres import RUNTIME, silver_database


class Artifacts:
    """What the worker asks of the artifact store: the verified receipt, and writing one."""

    def __init__(self):
        self.written = {}

    def put_bytes(self, uri, data):
        self.written[uri] = data
        return {"uri": uri, "sha256": "invented"}

    def verified(self, ref, **_):
        return self.written[ref["uri"]]


def envelope(checks=("silver.landed",)):
    return {"checks": list(checks), "output": "memory://land/0.json",
            "keys": {"unit": "facts-0", "table": "company_fact", "silver": "company_fact"},
            "input": {"uri": "memory://facts/0.json", "sha256": "invented"}}


@pytest.fixture
def landed(database, monkeypatch):
    two_filers = [{"tables": {"company_fact": rows("0000000042")}}, {"tables": {"company_fact": rows("0000000043")}}]
    monkeypatch.setattr(silver_land, "_artifacts", lambda envelope, artifacts: iter(copy.deepcopy(two_filers)))
    with silver_database(database.admin) as (owner, runtime):
        silver.migrate(owner, runtime_role=RUNTIME)
        assert silver.register(owner, spec_file(FOLDER / "silver-company-fact.yaml", None), runtime_role=RUNTIME)["created"]
        monkeypatch.setattr(silver_land, "engines", lambda: (runtime, database.application))
        monkeypatch.setattr(runtime, "dispose", lambda: None)
        monkeypatch.setattr(database.application, "dispose", lambda: None)
        yield runtime


def test_the_worker_lands_every_filer_once_and_the_verifier_confirms(landed):
    store = Artifacts()
    out = silver_land.execute(envelope(), store)
    receipt = json.loads(store.written[out["uri"]])
    assert receipt["rows"] == 8 and receipt["distinct_keys"] == 8
    with landed.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM silver.company_fact")).scalar() == 8
    again = Artifacts()
    silver_land.execute(envelope(), again)  # a retry lands the same rows: nothing changes
    with landed.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM silver.company_fact")).scalar() == 8
    assert again.written == store.written
    candidate = {"uri": out["uri"], "sha256": "invented"}
    assert silver_land.verify({**envelope(), "candidate": candidate}, store) == ({"silver.landed": True}, [])


def test_the_verifier_refuses_when_silver_lacks_a_key_the_reading_holds(landed):
    store = Artifacts()
    out = silver_land.execute(envelope(), store)
    with landed.begin() as conn:
        conn.execute(text("DELETE FROM silver.company_fact WHERE company_key = '0000000043'"))
    with pytest.raises(ValueError, match="lacks keys"):
        silver_land.verify({**envelope(), "candidate": {"uri": out["uri"], "sha256": "invented"}}, store)


def test_the_worker_verifies_only_its_own_check(landed):
    with pytest.raises(ValueError, match="verifies silver.landed only"):
        silver_land.execute(envelope(checks=("other",)), Artifacts())


def test_other_units_rows_cannot_hide_a_missing_key(landed, database):
    """Another unit's filer lands too, so silver holds more rows than this unit's reading; one of
    this unit's own rows is then gone. A count of the table would pass; the unit's own keys do not."""
    from edgar_warehouse.silver_writer.relational import DatabaseSink
    from edgar_warehouse.silver_writer.writer import land
    from tests.support.old_master_ids import OldIds as MdmIds

    store = Artifacts()
    out = silver_land.execute(envelope(), store)
    land(DatabaseSink(landed), "company_fact", rows("0000000099"), MdmIds(database.application))
    with landed.begin() as conn:
        conn.execute(text("DELETE FROM silver.company_fact WHERE ctid IN "
                          "(SELECT ctid FROM silver.company_fact WHERE company_key = '0000000043' LIMIT 1)"))
        assert conn.execute(text("SELECT count(*) FROM silver.company_fact")).scalar() >= 8
    with pytest.raises(ValueError, match="lacks keys"):
        silver_land.verify({**envelope(), "candidate": {"uri": out["uri"], "sha256": "invented"}}, store)
