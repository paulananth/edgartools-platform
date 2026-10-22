"""N-PORT holdings for silver, each a lookup row (ticket 79).

The real chain on invented holdings: holding.yaml (with each filing's series,
registrant and date), holding-combine.yaml (an ISIN folded into a CUSIP) and
holding-rows.yaml. Each row's `security_key` must be a record key the Security
contract makes from the same holdings (test_nport_isin_link's chain), so the
silver writer finds its Security by lookup; the holder is the fund series, or
the registrant for a filing naming none. Invented values only.
"""

from __future__ import annotations

import copy
import io
import zipfile
from pathlib import Path

from sqlalchemy import text

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, register_policy
from edgar_warehouse.rules import files
from edgar_warehouse.silver_writer import database as silver
from edgar_warehouse.silver_writer import spec as silver_spec
from edgar_warehouse.silver_writer.cli import spec_file
from edgar_warehouse.silver_writer.sink import PostgresSink
from edgar_warehouse.silver_writer.writer import MdmIds, land
from tests.integration import test_clean_mdm_postgres as core
from tests.integration import test_nport_isin_link as isin
from tests.integration import test_nport_link_start as cusip
from tests.integration.test_silver_writer_postgres import RUNTIME, silver_database
from tests.support import source_chain as chain

FOLDER = cusip.FOLDER
# A-1's series filed lower-case; A-2's "N/A" is no series: the registrant's own.
INFO = {"A-1": "s000000001", "A-2": "N/A"}
REGISTRANTS = [["A-1", "0000000001"], ["A-2", "0000000002"]]
FOLD = {"cusip": isin.CUSIP, "isin": isin.ONE, "cusip_offers": 1, "isin_offers": 1}


def holding_rows(root: Path, attached: list[dict] = ()) -> list[dict]:
    store = Artifacts()
    root.mkdir(parents=True, exist_ok=True)
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as z:
        z.writestr("FUND_REPORTED_HOLDING.tsv", "\n".join("\t".join(r) for r in [
            cusip.COLUMNS, *([*h, ""] for h in isin.HOLDINGS), isin.WITH_CUSIP]) + "\n")
        z.writestr("SUBMISSION.tsv", "ACCESSION_NUMBER\tFILING_DATE\n"
                   + "".join(f"{a}\t{d}\n" for a, d in cusip.FILINGS.items()))
        z.writestr("FUND_REPORTED_INFO.tsv", "ACCESSION_NUMBER\tSERIES_ID\n"
                   + "".join(f"{a}\t{s}\n" for a, s in INFO.items()))
    raw = store.put_bytes((root / "capture.zip").as_uri(), body.getvalue())
    series = cusip.read(store, root / "series", "holding-series.yaml", raw, None)
    pairs = [[r["accession"], r["series_id"]] for a in store.json(series)["artifacts"]
             for part in a.get("partitions", []) for r in store.json(part["receipt"])["tables"]["series"]]
    assert pairs == [["A-1", "S000000001"]]  # "N/A" gives no pair: a lookup never holds an empty value
    holdings = cusip.read(store, root / "holding", "holding.yaml", raw, cusip.Q2, lookups={
        "isin": isin.PAIRS, "series": pairs, "registrant": REGISTRANTS,
        "filed": cusip.filed_pairs(store, root, raw)})
    attached_reading = store.put(root.as_uri(), {"version": 1, "artifacts": [
        {"input": raw, "tables": {"attached": list(attached)}, "deferred": []}]})
    combined = cusip.combine(store, root / "combine", "holding-combine.yaml",
                             {"holdings": holdings, "attached": attached_reading})
    pieces = [store.put(root.as_uri(), {"tables": a["tables"]}) for a in store.json(combined)["artifacts"]]
    reading = chain.read(store, root / "rows", files.load(FOLDER / "holding-rows.yaml"), [
        {"input": p, "context": store.put(root.as_uri(), {"version": 1, "input": p, "values": {}})}
        for p in pieces], 2)
    return [row for artifact in store.json(reading)["artifacts"] for row in artifact["tables"]["holding"]]


def test_each_holding_names_the_security_record_its_holdings_make(tmp_path):
    rows = {r["holding_id"]: r for r in holding_rows(tmp_path / "rows", [FOLD])}
    keys = {r["provenance"]["record_key"] for r in isin.prepared_records(tmp_path / "securities", attached=[FOLD])}
    # ONE's ISIN-only holdings (4, 5) are the CUSIP's Security (ticket 120); 9 is
    # filed with the CUSIP itself; TWO and NONE keep their ISINs.
    assert {h: r["security_key"] for h, r in rows.items()} == {
        "4": isin.CUSIP, "5": isin.CUSIP, "6": isin.TWO, "7": isin.TWO, "8": isin.NONE, "9": isin.CUSIP}
    assert {r["security_key"] for r in rows.values()} <= keys
    assert len(rows) == len(isin.HOLDINGS) + 1  # every filed holding is a row


def test_an_isin_folded_into_no_cusip_keeps_its_own_security(tmp_path):
    rows = {r["holding_id"]: r for r in holding_rows(tmp_path / "rows")}
    keys = {r["provenance"]["record_key"] for r in isin.prepared_records(tmp_path / "securities")}
    assert rows["4"]["security_key"] == rows["5"]["security_key"] == isin.ONE
    assert {r["security_key"] for r in rows.values()} <= keys


def test_the_holder_is_the_series_else_the_registrant(tmp_path):
    rows = holding_rows(tmp_path / "rows", [FOLD])
    by_filing = {(r["accession"], r["series_id"], r["registrant_cik"], r["filed"], r["period"]) for r in rows}
    assert by_filing == {("A-1", "S000000001", "0000000001", "2026-06-05", cusip.Q2),
                         ("A-2", None, "0000000002", "2026-05-28", cusip.Q2)}


def test_the_rows_fit_the_silver_spec():
    spec = silver_spec.check(files.load(FOLDER / "silver-holding.yaml"))
    rows_contract = files.load(FOLDER / "holding-rows.yaml")
    assert set(rows_contract["read"]["tables"]["holding"]["columns"]) == {c["name"] for c in spec["columns"]}


SECURITY, FUND, REGISTRANT = "sec.nport.security.v2", "sec.nport.fund.v1", "sec.nport.registrant.v1"


def bound(database, source_code: str, key: str) -> str | None:
    with database.application.connect() as conn:
        return conn.scalar(text("SELECT entity_id::text FROM mdm.stage_record WHERE source_code = :s "
                                "AND record_key = :k"), {"s": source_code, "k": key})


def test_each_row_lands_with_its_holder_and_security_found_by_lookup(database, tmp_path):
    """The silver writer finds each MDM id by the row's keys, among the records each
    link's Dataset Contract staged; no holding record goes through the Merge Stage."""
    rows = holding_rows(tmp_path / "rows", [FOLD])
    for code in (SECURITY, FUND, REGISTRANT):  # fixture masters stand in for each contract's records
        core.register_reading(database, code, core.contract_body())
    with database.admin.begin() as conn:
        policy = register_policy(conn, copy.deepcopy(files.policy()))
    stage = MergeStage(Store(database.application))
    cusip.apply(stage, policy, "masters", [
        core.source(key=isin.CUSIP, source_code=SECURITY, kind="security", fields={},
                    identifiers={"cusip": isin.CUSIP}),
        core.source(key="S000000001", source_code=FUND, kind="fund_structure", fields={},
                    identifiers={"sec_series_id": "S000000001"}),
        core.source(key="0000000001", source_code=REGISTRANT, kind="company", fields={},
                    identifiers={"cik": "0000000001"})], 1)
    with silver_database(database.admin) as (owner, runtime):
        silver.migrate(owner, runtime_role=RUNTIME)
        spec = spec_file(FOLDER / "silver-holding.yaml", None)
        assert silver.register(owner, spec, runtime_role=RUNTIME)["created"] is True
        sink, ids = PostgresSink(runtime), MdmIds(database.application)
        assert land(sink, spec["table"], copy.deepcopy(rows), ids)["inserted"] == len(rows)
        again = land(sink, spec["table"], copy.deepcopy(rows), ids)  # the same delivery changes nothing
        assert (again["inserted"], again["changed"]) == (0, 0)
        with runtime.connect() as conn:
            landed = {r["holding_id"]: r for r in conn.execute(text("SELECT * FROM silver.nport_holding")).mappings()}
    security, fund = bound(database, SECURITY, isin.CUSIP), bound(database, FUND, "S000000001")
    registrant = bound(database, REGISTRANT, "0000000001")
    assert None not in (security, fund, registrant)
    # 4 and 5 (ONE, folded) and 9 (the CUSIP) are the CUSIP's Security; A-1's are the fund's.
    assert {h: str(landed[h]["security_mdm_id"]) for h in ("4", "5", "9")} == {"4": security, "5": security, "9": security}
    assert {str(r["fund_mdm_id"]) for h, r in landed.items() if r["accession"] == "A-1"} == {fund}
    assert {str(r["registrant_mdm_id"]) for r in landed.values() if r["accession"] == "A-1"} == {registrant}
    # A-2 names no series and its registrant is not mastered: empty ids, the row still lands.
    a2 = [r for r in landed.values() if r["accession"] == "A-2"]
    assert a2 and all(r["fund_mdm_id"] is None and r["registrant_mdm_id"] is None for r in a2)
    # TWO and NONE have no Security mastered here: empty, never another Security's id.
    assert landed["6"]["security_mdm_id"] is None and landed["8"]["security_mdm_id"] is None


def test_a_link_pointed_at_another_dataset_contract_finds_nothing(database, tmp_path):
    rows = [r for r in holding_rows(tmp_path / "rows", [FOLD]) if r["holding_id"] == "9"]
    core.register_reading(database, SECURITY, core.contract_body())
    with database.admin.begin() as conn:
        policy = register_policy(conn, copy.deepcopy(files.policy()))
    cusip.apply(MergeStage(Store(database.application)), policy, "masters", [
        core.source(key=isin.CUSIP, source_code=SECURITY, kind="security", fields={},
                    identifiers={"cusip": isin.CUSIP})], 1)
    spec = files.load(FOLDER / "silver-holding.yaml")
    for link in spec["links"]:
        if link["kind"] == "security":
            link["source_code"] = "sec.thirteenf.information_table.security.v1"
    with silver_database(database.admin) as (owner, runtime):
        silver.migrate(owner, runtime_role=RUNTIME)
        assert silver.register(owner, silver_spec.check(spec), runtime_role=RUNTIME)["created"] is True
        land(PostgresSink(runtime), spec["table"], rows, MdmIds(database.application))
        with runtime.connect() as conn:
            assert conn.scalar(text("SELECT security_mdm_id FROM silver.nport_holding")) is None
