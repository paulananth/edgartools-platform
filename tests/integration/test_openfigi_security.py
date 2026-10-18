"""Real PG16: OpenFIGI answers join the Securities they were asked for (ticket 80).

Invented answer files through the real chain (requests.yaml, the streamed
answers reading, reduce.yaml, combine.yaml, record.yaml,
mdm.prepare and the CUSIP and ISIN Dataset Contracts), then the Merge Stage beside a
13F Security:
- an equity keeps its one share class, and its US composite with that
  composite's ticker, never another country's; two US composites give
  neither; a single listing that is its own US composite gives both FIGIs;
- a bond's only listing gives its FIGI and its ticker, spaces kept;
- an identifier OpenFIGI did not find is set aside (`not_found_by_openfigi`);
- a record joins the Security that holds its CUSIP, and one no Security holds
  waits: OpenFIGI never creates a Security;
- every listing lands in silver (`silver-listing.yaml`) with the MDM id of
  the Security its identifier joined, or none while it waits.
OpenFIGI's CUSIP and ISIN rules are on in the repo's policy.
Invented values only.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from sqlalchemy import text

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, register_policy
from edgar_warehouse.rules import files
from edgar_warehouse.silver_writer import database as silver
from edgar_warehouse.silver_writer.cli import spec_file
from edgar_warehouse.silver_writer.sink import PostgresSink
from edgar_warehouse.silver_writer.writer import MdmIds, land
from tests.integration import test_clean_mdm_postgres as core
from tests.integration import test_nport_link_start as nport
from tests.integration.test_silver_writer_postgres import RUNTIME, silver_database
from tests.support import source_chain as chain
from tests.support.rules_authority import register_dataset

FOLDER = files.ROOT / "sources" / "openfigi"
CODE, ISIN_CODE = "openfigi.security.v1", "openfigi.security_isin.v1"
THIRTEENF = "sec.thirteenf.information_table.security.v1"
NPORT_ISIN = "sec.nport.security_isin.v1"
# Invented CUSIPs and ISINs, check digits valid.
EQUITY, BOND, MISSING, UNHELD, SOLE, DOUBLE = "ZZ0000013", "ZZ0000021", "ZZ0000039", "ZZ0000047", "ZZ0000120", "ZZ0000138"
# More asked and never found, one to a file, so each of the 8 readings has a file.
OTHERS = ["ZZ0000054", "ZZ0000062", "ZZ0000070", "ZZ0000088", "ZZ0000096", "ZZ0000104", "ZZ0000112"]
ISIN, ISIN_OTHERS = "ZZ0000000016", ["ZZ0000000024", "ZZ0000000032", "ZZ0000000040", "ZZ0000000057",
                                      "ZZ0000000065", "ZZ0000000073", "ZZ0000000081"]


def listing(figi, ticker, exchange, composite, share_class, sector="Equity"):
    kind = "Common Stock" if sector == "Equity" else "Corporate Bond"
    row = {"figi": figi, "name": "EXAMPLE CORP", "ticker": ticker, "exchCode": exchange, "securityType": kind,
           "marketSector": sector, "securityType2": kind, "securityDescription": ticker}
    return row | ({"compositeFIGI": composite} if composite else {}) | ({"shareClassFIGI": share_class} if share_class else {})


NOT_FOUND = {"warning": "No identifier found."}
# Invented FIGIs, named for what they stand for, not valid FIGIs: most hold a vowel or a
# wrong check digit, so silver flags them `figi_valid`. Only the rows asserted below matter.
ANSWERS = {
    # A US composite and a German one, one share class: the US composite and its ticker only.
    EQUITY: {"data": [listing("BBGZZ0000US1", "EXA", "US", "BBGZZ0000US1", "BBGZZ00000SC"),
                      listing("BBGZZ0000UN1", "EXA", "UN", "BBGZZ0000US1", "BBGZZ00000SC"),
                      listing("BBGZZ0000GR1", "EXB", "GR", "BBGZZ0000GR1", "BBGZZ00000SC"),
                      listing("BBGZZ0000GY1", "EXB", "GY", "BBGZZ0000GR1", "BBGZZ00000SC")]},
    BOND: {"data": [listing("BBGZZ000BND6", "EXA 5 01/01/30", "NOT LISTED", None, None, sector="Corp")]},
    MISSING: NOT_FOUND,
    UNHELD: {"data": [listing("BBGZZ000BND2", "EXC 4 01/01/31", "NOT LISTED", None, None, sector="Corp")]},
    # One listing that is its own US composite: its FIGI as both, one ticker.
    SOLE: {"data": [listing("BBGZZ0000US2", "EXD", "US", "BBGZZ0000US2", "BBGZZ0000SC2")]},
    # Two US composites (two share classes too): no composite and no ticker.
    DOUBLE: {"data": [listing("BBGZZ0000US3", "EXE", "US", "BBGZZ0000US3", "BBGZZ0000SC3"),
                      listing("BBGZZ0000US4", "EXF", "US", "BBGZZ0000US4", "BBGZZ0000SC4")]},
    ISIN: {"data": [listing("BBGZZ0000US5", "EXG", "US", "BBGZZ0000US5", "BBGZZ0000SC5"),
                    listing("BBGZZ0000LN5", "EXG", "LN", "BBGZZ0000LN5", "BBGZZ0000SC5")]},
}
KINDS = {"cusip": ("id_cusip", [[EQUITY, BOND, MISSING, UNHELD, SOLE, DOUBLE], *[[o] for o in OTHERS]], CODE),
         "isin": ("id_isin", [[ISIN], *[[o] for o in ISIN_OTHERS]], ISIN_CODE)}


def capture(root: Path, word: str) -> list[str]:
    """Eight request and answer files of one kind, as OpenFIGI's mapping takes and gives them."""
    kind, jobs, _ = KINDS[word]
    (root / kind).mkdir(parents=True, exist_ok=True)
    names = []
    for number, asked in enumerate(jobs):
        name = f"{number:05d}.json"
        (root / kind / name.replace(".json", ".request.json")).write_text(
            json.dumps([{"idType": kind.upper(), "idValue": value} for value in asked]))
        (root / kind / name).write_text(json.dumps([ANSWERS.get(value, NOT_FOUND) for value in asked]))
        names.append(name)
    return names


def prepared_records(root: Path, word: str = "cusip", listings: list | None = None) -> tuple[list[dict], dict[str, str]]:
    """One kind's records (`cusip` or `isin`), and each refused identifier with its reason;
    `listings`, when given, also gets every listing row of the source extract."""
    store = Artifacts()
    capture_root = root / "capture"
    kind, _, code = KINDS[word]
    name_list = capture(capture_root, word)

    def ref(path: Path) -> dict:
        return {"uri": path.as_uri(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def context(where: Path, path: Path, values: dict) -> dict:
        where.mkdir(parents=True, exist_ok=True)
        return store.put(where.as_uri(), {"version": 1, "input": ref(path), "values": values})

    answers_body = {k: v for k, v in files.source("openfigi").items() if k in ("source", "execution", "read")}
    readings = {}
    for number, name in enumerate(name_list, 1):
        where, batch = root / f"answers_{number}", f"{kind}/{name.split('.')[0]}"
        request = capture_root / kind / name.replace(".json", ".request.json")
        asked = chain.read(store, where / "requests", files.load(FOLDER / "requests.yaml"),
                           [{"input": ref(request), "context": context(where / "rq", request, {"batch": batch})}], 2)
        answer = capture_root / kind / name
        lookups = store.put(where.as_uri(), {"version": 2, "input": ref(answer), "sets": {"asked": {
            "readings": [asked], "table": "asked", "column": "key", "value_column": "id",
            "max_input_bytes": 1 << 20, "max_input_rows": 1000}}})
        readings[f"answers_{number}"] = chain.read(store, where / "answers", answers_body, [{
            "input": ref(answer), "lookups": lookups,
            "context": context(where / "an", answer, {"batch": batch, "id_type": word})}], 3)
    if listings is not None:
        for reading in readings.values():
            for artifact in store.json(reading)["artifacts"]:
                for part in artifact["partitions"]:
                    listings += store.json(part["receipt"])["tables"]["listings"]
    counts = chain.combine(store, root / "reduce", FOLDER / "reduce.yaml", readings)
    combined = chain.combine(store, root / "combine", FOLDER / "combine.yaml", {"counts": counts})
    piece_root = root / "record"
    piece_root.mkdir(parents=True, exist_ok=True)
    pieces = [store.put(piece_root.as_uri(), {"tables": a["tables"]}) for a in store.json(combined)["artifacts"]]
    records = chain.read(store, piece_root, files.load(FOLDER / "record.yaml"), [
        {"input": p, "context": store.put(piece_root.as_uri(), {"version": 1, "input": p, "values": {}})}
        for p in pieces], 2)
    prepared = chain.prepare(store, root / "mdm", records, {
        "table": "security", "record_column": "record", "dataset": code, "policy": "0" * 64,
        "consumer": "check", "batch_id": "check-openfigi", "as_of": "2026-10-17T00:00:00+00:00"})
    refused: dict[str, str] = {}
    out = chain.records(store, root / "mdm", prepared, code, files.source("openfigi")["mdm"][code]["contract"],
                        refused=refused, key="id")
    return out, refused


def policy_body() -> dict:
    """The live policy: OpenFIGI's CUSIP and ISIN rules are on (2026-10-17, 2026-10-18)."""
    return copy.deepcopy(files.policy())


def test_each_identifier_carries_only_its_single_levels(tmp_path):
    records, refused = prepared_records(tmp_path)
    found = {r["provenance"]["record_key"]: r.get("cross_references", {}) for r in records}
    assert found == {
        EQUITY: {"composite_figi": "BBGZZ0000US1", "share_class_figi": "BBGZZ00000SC", "openfigi_ticker": "EXA"},
        BOND: {"figi": "BBGZZ000BND6", "openfigi_ticker": "EXA 5 01/01/30"},
        UNHELD: {"figi": "BBGZZ000BND2", "openfigi_ticker": "EXC 4 01/01/31"},
        SOLE: {"figi": "BBGZZ0000US2", "composite_figi": "BBGZZ0000US2", "share_class_figi": "BBGZZ0000SC2",
               "openfigi_ticker": "EXD"},
        DOUBLE: {},
    }
    assert refused == {cusip: "not_found_by_openfigi" for cusip in (MISSING, *OTHERS)}


def bound(database, source_code: str, key: str) -> str | None:
    with database.application.connect() as conn:
        return conn.scalar(text("SELECT entity_id::text FROM mdm.stage_record WHERE source_code = :s "
                                "AND record_key = :k"), {"s": source_code, "k": key})


def staged(database, source_code: str, key: str) -> int:
    """How many staged records the source holds under this key: a waiting record is staged, unbound."""
    with database.application.connect() as conn:
        return conn.scalar(text("SELECT count(*) FROM mdm.stage_record WHERE source_code = :s AND record_key = :k"),
                           {"s": source_code, "k": key})


def test_a_record_joins_the_security_holding_its_cusip_and_never_creates_one(database, tmp_path):
    records, _ = prepared_records(tmp_path)
    core.register_reading(database, THIRTEENF, core.contract_body())
    with database.admin.begin() as conn:
        register_dataset(conn, CODE, database.registry, files.mdm_contract("openfigi", CODE))
        policy = register_policy(conn, policy_body())
    stage = MergeStage(Store(database.application))
    nport.apply(stage, policy, "13f", [core.source(key=cusip, source_code=THIRTEENF, kind="security",
                                                   fields={"name_of_issuer": "EXAMPLE CORP"},
                                                   identifiers={"cusip": cusip}) for cusip in (EQUITY, BOND)], 1)
    nport.apply(stage, policy, "openfigi", records, 2)
    securities = {k for k, v in core.documents(database, "entity").items() if v["kind"] == "security"}
    assert len(securities) == 2
    for cusip in (EQUITY, BOND):
        assert bound(database, CODE, cusip) == bound(database, THIRTEENF, cusip) is not None
    # Waiting: staged and unbound, never a Security of its own.
    assert staged(database, CODE, UNHELD) == 1 and bound(database, CODE, UNHELD) is None
    with database.application.connect() as conn:
        (row,) = conn.execute(text("SELECT * FROM mdm.cross_reference_lookup('composite_figi', 'BBGZZ0000US1')")).all()
    assert row._mapping["record_key"] == EQUITY


def test_an_isin_record_carries_its_levels_and_joins_the_security_holding_it(database, tmp_path):
    records, refused = prepared_records(tmp_path, "isin")
    assert {r["provenance"]["record_key"]: r["cross_references"] for r in records} == {
        ISIN: {"composite_figi": "BBGZZ0000US5", "share_class_figi": "BBGZZ0000SC5", "openfigi_ticker": "EXG"}}
    assert refused == {isin: "not_found_by_openfigi" for isin in ISIN_OTHERS}
    core.register_reading(database, NPORT_ISIN, core.contract_body())
    with database.admin.begin() as conn:
        register_dataset(conn, ISIN_CODE, database.registry, files.mdm_contract("openfigi", ISIN_CODE))
        policy = register_policy(conn, policy_body())
    stage = MergeStage(Store(database.application))
    nport.apply(stage, policy, "nport", [core.source(key=ISIN, source_code=NPORT_ISIN, kind="security",
                                                     fields={"name_of_issuer": "EXAMPLE CORP"},
                                                     identifiers={"isin": ISIN})], 1)
    nport.apply(stage, policy, "openfigi", records, 2)
    assert bound(database, ISIN_CODE, ISIN) == bound(database, NPORT_ISIN, ISIN) is not None
    assert len({k for k, v in core.documents(database, "entity").items() if v["kind"] == "security"}) == 1


def test_every_listing_lands_in_silver_with_the_security_its_identifier_joined(database, tmp_path):
    rows: list[dict] = []
    records, _ = prepared_records(tmp_path / "cusip", listings=rows)
    isin_records, _ = prepared_records(tmp_path / "isin", "isin", listings=rows)
    core.register_reading(database, THIRTEENF, core.contract_body())
    core.register_reading(database, NPORT_ISIN, core.contract_body())
    with database.admin.begin() as conn:
        for code in (CODE, ISIN_CODE):
            register_dataset(conn, code, database.registry, files.mdm_contract("openfigi", code))
        policy = register_policy(conn, policy_body())
    stage = MergeStage(Store(database.application))
    # The Securities' own records are keyed apart from the identifier, so only
    # OpenFIGI's Dataset Contract finds a listing's Security by its identifier.
    nport.apply(stage, policy, "13f", [core.source(key="13F-ROW-1", source_code=THIRTEENF, kind="security",
                                                   fields={"name_of_issuer": "EXAMPLE CORP"},
                                                   identifiers={"cusip": EQUITY})], 1)
    nport.apply(stage, policy, "nport", [core.source(key="NPORT-ROW-1", source_code=NPORT_ISIN, kind="security",
                                                     fields={"name_of_issuer": "EXAMPLE CORP"},
                                                     identifiers={"isin": ISIN})], 2)
    nport.apply(stage, policy, "openfigi", records + isin_records, 3)
    rows = [{k: v for k, v in row.items() if k != "figi_ticker"} for row in rows]
    with silver_database(database.admin) as (owner, runtime):
        silver.migrate(owner, runtime_role=RUNTIME)
        spec = spec_file(FOLDER / "silver-listing.yaml", None)
        assert silver.register(owner, spec, runtime_role=RUNTIME)["created"] is True
        sink, ids = PostgresSink(runtime), MdmIds(database.application)
        assert land(sink, spec["table"], copy.deepcopy(rows), ids)["inserted"] == 11
        again = land(sink, spec["table"], copy.deepcopy(rows), ids)  # the same delivery changes nothing
        assert (again["inserted"], again["changed"]) == (0, 0)
        with runtime.connect() as conn:
            landed = {(r["id"], r["figi"]): r for r in conn.execute(text(
                "SELECT * FROM silver.openfigi_listing")).mappings()}
    # The answers' 9 CUSIP and 2 ISIN listings, each once; unfound identifiers give none.
    assert len(landed) == len(rows) == 11
    equity, isin = bound(database, CODE, EQUITY), bound(database, ISIN_CODE, ISIN)
    assert equity == bound(database, THIRTEENF, "13F-ROW-1") is not None
    assert isin == bound(database, NPORT_ISIN, "NPORT-ROW-1") is not None
    assert {k[1]: (r["security_mdm_id_by_cusip"], r["security_mdm_id_by_isin"])
            for k, r in landed.items() if k[0] in (EQUITY, ISIN)} == {
        **{f: (equity, None) for f in ("BBGZZ0000US1", "BBGZZ0000UN1", "BBGZZ0000GR1", "BBGZZ0000GY1")},
        **{f: (None, isin) for f in ("BBGZZ0000US5", "BBGZZ0000LN5")}}
    assert landed[(EQUITY, "BBGZZ0000GR1")]["ticker"] == "EXB"
    # A FIGI off its declared shape (a vowel among its eight) is flagged and still lands;
    # so is one of the right shape whose check digit is wrong (ticket 107: GR's is 8).
    assert landed[(EQUITY, "BBGZZ0000US1")]["quality"] == ["figi_valid"]
    assert "figi_valid" in landed[(EQUITY, "BBGZZ0000GR1")]["quality"]
    assert landed[(BOND, "BBGZZ000BND6")]["quality"] is None
    # UNHELD waits in MDM, so its listing keeps an empty MDM id.
    assert landed[(UNHELD, "BBGZZ000BND2")]["security_mdm_id_by_cusip"] is None
