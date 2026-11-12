"""The 13F `mastering` target lands each information table's holdings in silver (ticket 183), through real
workers on PG16: read (one unit a file), the Securities' reduction, combine, record and prepare, a merge that
stands in for MDM's own (it has its worker test), then one landing a file that waits for the merge.
Every name and number is invented."""
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import frozen
import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import text

from edgar_warehouse.bookkeeping.clean.database import grant_profile
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.mdm import target_manifest
from edgar_warehouse.rules import files
from edgar_warehouse.silver_writer import database as silver
from edgar_warehouse.silver_writer.cli import spec_file
from edgar_warehouse.workers import mdm_prepare, silver_land, source_combine, source_read
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401
from tests.support.mdm_database import mdm  # noqa: F401
from tests.integration.test_silver_writer_postgres import RUNTIME, silver_database
from tests.integration.test_thirteenf_securities_target_postgres import ALSO, BAD, GOOD, SOURCE, capture
from tests.support.bookkeeping_protocol import drive

FOLDER = files.ROOT / "sources" / SOURCE


def holding(cusip, name, *, shares="100", value="5000", discretion="SOLE", put_call=""):
    return (f"<infoTable><nameOfIssuer>{name}</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>{cusip}</cusip>"
            f"<value>{value}</value><shrsOrPrnAmt><sshPrnamt>{shares}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType>"
            f"</shrsOrPrnAmt>{f'<putCall>{put_call}</putCall>' if put_call else ''}"
            f"<investmentDiscretion>{discretion}</investmentDiscretion><votingAuthority><Sole>{shares}</Sole>"
            "<Shared>0</Shared><None>0</None></votingAuthority></infoTable>")


def information_table(*holdings):
    return f"<informationTable>{''.join(holdings)}</informationTable>".encode()


def test_each_holding_lands_in_silver_after_the_merge_with_its_filing_and_facts(databases, mdm, tmp_path, monkeypatch):
    real = files.source

    def small_slices(name, *args, **kwargs):
        reading = deepcopy(real(name, *args, **kwargs))
        if name == SOURCE:
            reading["bookkeeping"]["targets"]["mastering"]["steps"][0]["units"] = {"slices": {"bytes": 1}}
        return reading
    monkeypatch.setattr(target_manifest.rules_files, "source", small_slices)
    tables = [information_table(holding(GOOD, "EXAMPLE CORP"), holding(ALSO, "OTHER CORP", discretion="DFND", put_call="Put")),
              information_table(holding(BAD, "ODD CORP", shares="7", value="9"))]
    report = target_manifest.write_manifest(**capture(tmp_path, tables))
    target = deepcopy(small_slices(SOURCE)["bookkeeping"]["targets"]["mastering"])
    assert [step["name"] for step in target["steps"][-2:]] == ["land_holding", "processed"]
    target["steps"] = target["steps"][:-1]  # the Change Journal step has its own plan test
    book = Bookkeeping(databases.runtime)
    steps = book.artifacts.json(report["manifest"])["steps"]
    del steps["processed"]
    assert len(steps["read"]) == len(steps["land_holding"]) == 2  # one unit and one landing a file
    manifest = book.artifacts.put(tmp_path.as_uri() + "/submitted", {"version": 2, "steps": steps})
    body = {"source": f"thirteenf-{uuid4().hex}", "bookkeeping": {"version": 2, "targets": {"mastering": target}}}
    saved = frozen.of("source", body["source"], body)
    rules = Artifacts().put(tmp_path.as_uri() + "/rules", saved)
    rid = book.start(rules_ref=rules, inputs_ref=manifest, target="mastering", scope={"test": body["source"]})

    order = []

    def merge(envelope, artifacts):
        assert book.tasks(rid, "silver.land", limit=100) == []  # no landing is claimable before the merge
        order.append("merge")
        return artifacts.put_bytes(envelope["output"], b"{}")

    def land(envelope, artifacts):
        order.append("land")
        return silver_land.execute(envelope, artifacts)

    workers = {"source.read": source_read, "source.combine": source_combine, "mdm.prepare": mdm_prepare,
               "mastering.merge": SimpleNamespace(execute=merge, check=lambda e, a: ({n: True for n in e["checks"]}, [])),
               "silver.land": SimpleNamespace(execute=land, check=silver_land.check)}
    for profile in workers:
        grant_profile(databases.admin, profile=profile, worker="bk_runtime")
    with silver_database(databases.admin) as (owner, runtime):
        silver.migrate(owner, runtime_role=RUNTIME)
        assert silver.register(owner, spec_file(FOLDER / "silver-holding.yaml", None), runtime_role=RUNTIME)["created"]
        monkeypatch.setattr(silver_land, "engines", lambda: (runtime, mdm.application))  # an empty MDM: no Security mastered
        monkeypatch.setattr(runtime, "dispose", lambda: None)
        monkeypatch.setattr(mdm.application, "dispose", lambda: None)
        state = drive(book, rid, databases.ledger, workers=workers)
        with runtime.connect() as conn:
            rows = {(r["accession_number"], r["holding_index"]): r for r in conn.execute(
                text("SELECT * FROM silver.thirteenf_holding")).mappings()}

    assert state["run"]["state"] == "complete"
    assert order == ["merge", "land", "land"]
    assert len(rows) == 3
    first, second = rows[("0000000042-26-000001", 1)], rows[("0000000042-26-000001", 2)]
    assert (first["cusip"], first["shares_held"], first["share_type"], first["market_value"], first["discretion_type"],
            first["put_call"]) == (GOOD, 100, "SH", 5000, "SOLE", None)
    assert (second["cusip"], second["discretion_type"], second["put_call"]) == (ALSO, "DFND", "Put")
    assert rows[("0000000042-26-000002", 1)]["cusip"] == BAD and rows[("0000000042-26-000002", 1)]["voting_auth_sole"] == 7
    assert all(r["security_mdm_id"] is None for r in rows.values())  # nothing is mastered in this empty MDM
    # Silver keeps no field of the Security: no name, title or FIGI column.
    assert not {"issuer_name", "security_title", "figi"} & set(first)
