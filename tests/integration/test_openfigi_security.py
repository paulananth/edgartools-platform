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
- a record joins the Security that holds its CUSIP, or creates one (ticket 120,
  OpenFIGI first; it replaced "OpenFIGI never creates a Security"); an ISIN
  answer carries the one CUSIP sharing a listing FIGI with it and joins that
  Security, and one sharing FIGIs with two CUSIPs is set aside;
- every listing lands in silver (`silver-listing.yaml`) with the MDM id of
  the Security its identifier joined, or none while it waits.
OpenFIGI first's three rules are switched on in a copy of the repo's policy.
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
NPORT_ISIN = "sec.nport.security.v2"  # its ISIN-only Securities (ticket 120: one Dataset Contract)
# Invented CUSIPs and ISINs, check digits valid.
EQUITY, BOND, MISSING, UNHELD, SOLE, DOUBLE = "ZZ0000013", "ZZ0000021", "ZZ0000039", "ZZ0000047", "ZZ0000120", "ZZ0000138"
# More asked and never found, one to a file, so each of the 8 readings has a file.
OTHERS = ["ZZ0000054", "ZZ0000062", "ZZ0000070", "ZZ0000088", "ZZ0000096", "ZZ0000104", "ZZ0000112"]
# A Japanese ISIN with no US listing: its Japanese composite is its primary listing (ticket 120).
HOME = "JP0000000091"
# Ticket 120, OpenFIGI first: an ISIN sharing a listing FIGI with one CUSIP answer (EQUITY's US
# composite) carries that CUSIP; one sharing FIGIs with two (SOLE's and DOUBLE's) is set aside.
SHARED, TWICE = "ZZ0000000099", "ZZ0000000107"
ISIN, ISIN_OTHERS = "ZZ0000000016", ["ZZ0000000024", "ZZ0000000032", "ZZ0000000040", "ZZ0000000057",
                                      "ZZ0000000065", "ZZ0000000073", "ZZ0000000081"]


def listing(figi, ticker, exchange, composite, share_class, sector="Equity", name="EXAMPLE CORP"):
    kind = "Common Stock" if sector == "Equity" else "Corporate Bond"
    row = {"figi": figi, **({"name": name} if name else {}), "ticker": ticker, "exchCode": exchange, "securityType": kind,
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
    # A listing that states no name gives the record none (ticket 84).
    UNHELD: {"data": [listing("BBGZZ000BND2", "EXC 4 01/01/31", "NOT LISTED", None, None, sector="Corp", name=None)]},
    # One listing that is its own US composite: its FIGI as both, one ticker.
    SOLE: {"data": [listing("BBGZZ0000US2", "EXD", "US", "BBGZZ0000US2", "BBGZZ0000SC2")]},
    # Two US composites (two share classes too): no composite and no ticker.
    DOUBLE: {"data": [listing("BBGZZ0000US3", "EXE", "US", "BBGZZ0000US3", "BBGZZ0000SC3"),
                      listing("BBGZZ0000US4", "EXF", "US", "BBGZZ0000US4", "BBGZZ0000SC4", name="OTHER CORP")]},
    ISIN: {"data": [listing("BBGZZ0000US5", "EXG", "US", "BBGZZ0000US5", "BBGZZ0000SC5"),
                    listing("BBGZZ0000LN5", "EXG", "LN", "BBGZZ0000LN5", "BBGZZ0000SC5")]},
    # Its Japanese and German composites state different names: Japan's, from its ISIN, is primary.
    HOME: {"data": [listing("BBGZZ0000JP6", "EXH", "JP", "BBGZZ0000JP6", "BBGZZ0000SC6", name="HOME CORP"),
                    listing("BBGZZ0000GR6", "EXI", "GR", "BBGZZ0000GR6", "BBGZZ0000SC6", name="OTHER CORP")]},
    SHARED: {"data": [listing("BBGZZ0000US1", "EXA", "US", "BBGZZ0000US1", "BBGZZ00000SC"),
                      listing("BBGZZ0000LN9", "EXA", "LN", "BBGZZ0000LN9", "BBGZZ00000SC")]},
    TWICE: {"data": [listing("BBGZZ0000US2", "EXD", "US", "BBGZZ0000US2", "BBGZZ0000SC2"),
                     listing("BBGZZ0000US3", "EXE", "US", "BBGZZ0000US3", "BBGZZ0000SC3")]},
}
KINDS = {"cusip": ("id_cusip", [[EQUITY, BOND, MISSING, UNHELD, SOLE, DOUBLE], *[[o] for o in OTHERS]], CODE),
         "isin": ("id_isin", [[ISIN, HOME, SHARED, TWICE], *[[o] for o in ISIN_OTHERS]], ISIN_CODE)}


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


def answer_readings(store: Artifacts, root: Path, word: str) -> list[str]:
    """One kind's eight answers readings (requests.yaml, then the streamed answers reading)."""
    capture_root = root / "capture"
    kind, _, _ = KINDS[word]
    name_list = capture(capture_root, word)

    def ref(path: Path) -> dict:
        return {"uri": path.as_uri(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def context(where: Path, path: Path, values: dict) -> dict:
        where.mkdir(parents=True, exist_ok=True)
        return store.put(where.as_uri(), {"version": 1, "input": ref(path), "values": values})

    answers_body = {k: v for k, v in files.source("openfigi").items() if k in ("source", "execution", "read")}
    readings = []
    for number, name in enumerate(name_list, 1):
        where, batch = root / f"{word}_answers_{number}", f"{kind}/{name.split('.')[0]}"
        request = capture_root / kind / name.replace(".json", ".request.json")
        asked = chain.read(store, where / "requests", files.load(FOLDER / "requests.yaml"),
                           [{"input": ref(request), "context": context(where / "rq", request, {"batch": batch})}], 2)
        answer = capture_root / kind / name
        lookups = store.put(where.as_uri(), {"version": 2, "input": ref(answer), "sets": {"asked": {
            "readings": [asked], "table": "asked", "column": "key", "value_column": "id",
            "max_input_bytes": 1 << 20, "max_input_rows": 1000}}})
        readings.append(chain.read(store, where / "answers", answers_body, [{
            "input": ref(answer), "lookups": lookups,
            "context": context(where / "an", answer, {"batch": batch, "id_type": word})}], 3))
    return readings


def prepared_records(root: Path, word: str = "cusip", listings: list | None = None) -> tuple[list[dict], dict[str, str]]:
    """One kind's records (`cusip` or `isin`), and each refused identifier with its reason;
    `listings`, when given, also gets every listing row of the source extract. The ISIN
    target's records come through its OpenFIGI-first steps (ticket 120): the CUSIP answers'
    `figi_ids`, then `figi_cusips` and `attach`."""
    store = Artifacts()
    _, _, code = KINDS[word]
    readings = answer_readings(store, root, word)
    if listings is not None:
        for reading in readings:
            for artifact in store.json(reading)["artifacts"]:
                for part in artifact["partitions"]:
                    listings += store.json(part["receipt"])["tables"]["listings"]
    counts = chain.combine(store, root / "reduce", FOLDER / "reduce.yaml", {"answers": readings})
    combined = chain.combine(store, root / "combine", FOLDER / "combine.yaml", {"counts": counts, "answers": readings})
    if word == "isin":
        figi_ids = chain.combine(store, root / "figi_ids", FOLDER / "figi-ids.yaml",
                                 {"answers": answer_readings(store, root, "cusip")})
        rows = chain.combine(store, root / "figi_cusips", FOLDER / "isin-figi-cusips.yaml",
                             {"answers": readings, "cusips": figi_ids})
        combined = chain.combine(store, root / "attach", FOLDER / "isin-attach.yaml",
                                 {"security": combined, "rows": rows})
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


OPENFIGI_FIRST = ("openfigi-security-cusip", "openfigi-isin-security-cusip", "openfigi-security-isin")


def policy_body() -> dict:
    """The repo's policy with OpenFIGI first's three rules switched on, in this copy only
    (a Proving Run activation, ticket 120): they wait for the operator's switch-on."""
    body = copy.deepcopy(files.policy())
    rules = {r["rule_id"]: r for r in body["kinds"]["security"]["rules"]}
    body["automatic_rules"] = [a for a in body["automatic_rules"] if a["rule_id"] not in OPENFIGI_FIRST] + [
        {"kind": "security", "family": "binding", "rule_id": rule_id, "rule_version": rules[rule_id]["version"],
         "verdict": "bind", "activation": "deterministic"} for rule_id in OPENFIGI_FIRST]
    return body


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
    # A CUSIP answer carries only its own CUSIP (ticket 120: the FIGI's CUSIP is the ISIN target's).
    assert {r["provenance"]["record_key"]: r["identifiers"] for r in records} == {c: {"cusip": c} for c in found}
    # OpenFIGI's name, only where its listings state one (ticket 84): DOUBLE's two names give none.
    names = {r["provenance"]["record_key"]: r["fields"]["name_of_issuer"].get("value") for r in records}
    assert names == {EQUITY: "EXAMPLE CORP", BOND: "EXAMPLE CORP", UNHELD: None, SOLE: "EXAMPLE CORP", DOUBLE: None}


def bound(database, source_code: str, key: str) -> str | None:
    with database.application.connect() as conn:
        return conn.scalar(text("SELECT entity_id::text FROM mdm.stage_record WHERE source_code = :s "
                                "AND record_key = :k"), {"s": source_code, "k": key})


def staged(database, source_code: str, key: str) -> int:
    """How many staged records the source holds under this key: a waiting record is staged, unbound."""
    with database.application.connect() as conn:
        return conn.scalar(text("SELECT count(*) FROM mdm.stage_record WHERE source_code = :s AND record_key = :k"),
                           {"s": source_code, "k": key})


def test_a_record_joins_the_security_holding_its_cusip_or_creates_it(database, tmp_path):
    """Ticket 120, OpenFIGI first (operator, 2026-10-23: "make the seurities run should process
    openfigi first"): a CUSIP answer joins the Security holding its CUSIP, or creates one."""
    records, _ = prepared_records(tmp_path)
    core.register_reading(database, THIRTEENF, core.contract_body())
    with database.admin.begin() as conn:
        register_dataset(conn, CODE, database.registry, files.mdm_contract("openfigi", CODE))
        policy = register_policy(conn, policy_body())
    stage = MergeStage(Store(database.application))
    nport.apply(stage, policy, "13f", [core.source(key=cusip, source_code=THIRTEENF, kind="security",
                                                   fields={"name_of_issuer": "Example Corp.", "title_of_class": "COM"},
                                                   identifiers={"cusip": cusip}) for cusip in (EQUITY, BOND)], 1)
    nport.apply(stage, policy, "openfigi", records, 2)
    securities = {k: v for k, v in core.documents(database, "entity").items() if v["kind"] == "security"}
    # EQUITY and BOND joined 13F's; UNHELD, SOLE and DOUBLE each created one.
    assert len(securities) == 5
    for cusip in (EQUITY, BOND):
        assert bound(database, CODE, cusip) == bound(database, THIRTEENF, cusip) is not None
    assert len({bound(database, CODE, c) for c in (EQUITY, BOND, UNHELD, SOLE, DOUBLE)} - {None}) == 5
    # OpenFIGI ranks first for the name, 13F last; OpenFIGI states no title, so the filed one stays (ticket 84).
    joined = securities[bound(database, CODE, EQUITY)]["fields"]
    assert (joined["name_of_issuer"]["value"], joined["title_of_class"]["value"]) == ("EXAMPLE CORP", "COM")
    with database.application.connect() as conn:
        (row,) = conn.execute(text("SELECT * FROM mdm.cross_reference_lookup('composite_figi', 'BBGZZ0000US1')")).all()
    assert row._mapping["record_key"] == EQUITY


def test_an_isin_answer_carries_the_one_cusip_sharing_its_figi(tmp_path):
    """Ticket 120 (operator, 2026-10-23: an ISIN answer finds its Security by the FIGI it shares
    with a CUSIP answer, "agreed"): one CUSIP is carried; none, none; two set it aside."""
    records, refused = prepared_records(tmp_path, "isin")
    assert {r["provenance"]["record_key"]: r["identifiers"] for r in records} == {
        ISIN: {"isin": ISIN}, HOME: {"isin": HOME}, SHARED: {"isin": SHARED, "cusip": EQUITY}}
    assert refused == {TWICE: "isin_shares_figi_with_several_cusips",
                       **{isin: "not_found_by_openfigi" for isin in ISIN_OTHERS}}


def test_openfigi_creates_the_securities_and_an_isin_joins_its_cusips(database, tmp_path):
    """OpenFIGI first, end to end in the Merge Stage: the CUSIP answers create five Securities;
    SHARED joins EQUITY's by the CUSIP it carries; ISIN and HOME create their own; then an
    N-PORT record filing EQUITY's CUSIP and SHARED's ISIN joins EQUITY's, creating none."""
    cusips, _ = prepared_records(tmp_path / "cusip")
    isins, _ = prepared_records(tmp_path / "isin", "isin")
    core.register_reading(database, NPORT_ISIN, core.contract_body())
    with database.admin.begin() as conn:
        for code in (CODE, ISIN_CODE):
            register_dataset(conn, code, database.registry, files.mdm_contract("openfigi", code))
        policy = register_policy(conn, policy_body())
    stage = MergeStage(Store(database.application))
    nport.apply(stage, policy, "openfigi-cusip", cusips, 1)
    nport.apply(stage, policy, "openfigi-isin", isins, 2)
    equity = bound(database, CODE, EQUITY)
    assert equity is not None and bound(database, ISIN_CODE, SHARED) == equity
    assert len({bound(database, ISIN_CODE, i) for i in (ISIN, HOME, SHARED)} | {equity}) == 3
    count = lambda: len({k for k, v in core.documents(database, "entity").items() if v["kind"] == "security"})
    assert count() == 7
    nport.apply(stage, policy, "nport", [core.source(key=EQUITY, source_code=NPORT_ISIN, kind="security",
                                                     fields={"name_of_issuer": "EXAMPLE CORP"},
                                                     identifiers={"cusip": EQUITY, "isin": SHARED})], 3)
    assert bound(database, NPORT_ISIN, EQUITY) == equity and count() == 7


def test_an_isin_record_carries_its_levels_and_joins_the_security_holding_it(database, tmp_path):
    records, refused = prepared_records(tmp_path, "isin")
    assert {r["provenance"]["record_key"]: r["cross_references"] for r in records} == {
        ISIN: {"composite_figi": "BBGZZ0000US5", "share_class_figi": "BBGZZ0000SC5", "openfigi_ticker": "EXG"},
        HOME: {"share_class_figi": "BBGZZ0000SC6", "composite_figi": "BBGZZ0000JP6", "openfigi_ticker": "EXH"},
        SHARED: {"share_class_figi": "BBGZZ00000SC", "composite_figi": "BBGZZ0000US1", "openfigi_ticker": "EXA"}}
    assert set(refused) == {TWICE, *ISIN_OTHERS}
    core.register_reading(database, NPORT_ISIN, core.contract_body())
    with database.admin.begin() as conn:
        register_dataset(conn, ISIN_CODE, database.registry, files.mdm_contract("openfigi", ISIN_CODE))
        policy = register_policy(conn, policy_body())
    stage = MergeStage(Store(database.application))
    nport.apply(stage, policy, "nport", [core.source(key=ISIN, source_code=NPORT_ISIN, kind="security",
                                                     fields={"name_of_issuer": "EXAMPLE CORP"},
                                                     identifiers={"isin": ISIN})], 1)
    nport.apply(stage, policy, "openfigi", [r for r in records if r["provenance"]["record_key"] == ISIN], 2)
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
        assert land(sink, spec["table"], copy.deepcopy(rows), ids)["inserted"] == 17
        again = land(sink, spec["table"], copy.deepcopy(rows), ids)  # the same delivery changes nothing
        assert (again["inserted"], again["changed"]) == (0, 0)
        with runtime.connect() as conn:
            landed = {(r["id"], r["figi"]): r for r in conn.execute(text(
                "SELECT * FROM silver.openfigi_listing")).mappings()}
    # The answers' 9 CUSIP and 8 ISIN listings, each once; unfound identifiers give none.
    assert len(landed) == len(rows) == 17
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
    # OpenFIGI first (ticket 120): UNHELD created its own Security, so its listing has its MDM id.
    assert landed[(UNHELD, "BBGZZ000BND2")]["security_mdm_id_by_cusip"] == bound(database, CODE, UNHELD) is not None
    # SHARED joined EQUITY's Security by the CUSIP sharing its FIGI; TWICE waits, so none.
    assert landed[(SHARED, "BBGZZ0000LN9")]["security_mdm_id_by_isin"] == equity
    assert landed[(TWICE, "BBGZZ0000US2")]["security_mdm_id_by_isin"] is None


def test_a_securitys_fields_are_the_agreed_or_the_primary_listings_and_every_listing_is_a_detail_row(tmp_path):
    """Ticket 120 (operator, 2026-10-20: "all fields from open figi must be in the security
    master", "Use the primary exchange listing", "US, else the ISIN's country", "Detail rows
    set in config"): a field the listings agree on; else the one US composite's; else the
    ISIN country's composite's (rules/reference/published/openfigi-country-composite); else none.
    Every listing is a detail row keyed by its FIGI."""
    records, _ = prepared_records(tmp_path / "cusip")
    by_key = {r["provenance"]["record_key"]: r for r in records}
    equity = by_key[EQUITY]
    assert {k: equity["fields"][k]["value"] for k in ("name_of_issuer", "security_type", "security_type2",
                                                       "market_sector")} == {
        "name_of_issuer": "EXAMPLE CORP", "security_type": "Common Stock", "security_type2": "Common Stock",
        "market_sector": "Equity"}
    # The share class FIGI is a cross-reference only, never a field too (ticket 129, "Fix 4").
    assert "share_class_figi" not in equity["fields"]
    assert [(r["key"], r["exchange"], r["ticker"]) for r in equity["details"]["listings"]] == [
        ("BBGZZ0000GR1", "GR", "EXB"), ("BBGZZ0000GY1", "GY", "EXB"), ("BBGZZ0000UN1", "UN", "EXA"),
        ("BBGZZ0000US1", "US", "EXA")]
    assert equity["details"]["listings"][3] == {"key": "BBGZZ0000US1", "exchange": "US", "ticker": "EXA",
                                                "composite_figi": "BBGZZ0000US1", "description": "EXA"}
    # Two US composites and two names: no primary listing, so no name; the type they share stays.
    double = by_key[DOUBLE]
    assert double["fields"]["name_of_issuer"].get("value") is None
    assert double["fields"]["security_type"]["value"] == "Common Stock"
    assert len(double["details"]["listings"]) == 2

    isin_records, _ = prepared_records(tmp_path / "isin", "isin")
    home = {r["provenance"]["record_key"]: r for r in isin_records}[HOME]
    # No US listing; the names differ; Japan's composite, from the ISIN's country, gives the name.
    assert home["fields"]["name_of_issuer"]["value"] == "HOME CORP"
    assert [r["key"] for r in home["details"]["listings"]] == ["BBGZZ0000GR6", "BBGZZ0000JP6"]


def test_the_country_table_in_the_reading_is_the_published_code_set():
    """The reading embeds RDM's openfigi-country-composite version 1, row for row."""
    published = Path(files.ROOT / "reference" / "published" / "openfigi-country-composite" / "1" / "canonical.jsonl")
    codes = {row["code"]: row["crosswalk"][0][2] for row in map(json.loads, published.read_text().splitlines())}
    embedded = files.source("openfigi")["read"]["references"]["country_composite"]
    assert {code: row["exchange"] for code, row in embedded.items()} == codes and len(codes) == 11
