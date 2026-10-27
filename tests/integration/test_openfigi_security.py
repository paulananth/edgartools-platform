"""Real PG16: OpenFIGI answers master the Securities, in one load (ticket 138).

Invented answer files through the real chain (requests.yaml, the streamed
answers reading over both folders, reduce.yaml, combine.yaml, record.yaml,
mdm.prepare and the one Dataset Contract), then the Merge Stage:
- an equity keeps its one share class, and its US composite with that
  composite's ticker, never another country's; two US composites give
  neither; a single listing that is its own US composite gives both FIGIs;
- a record carries the identifier asked, CUSIP or ISIN, and every listing's
  FIGI, each an identifier; a FIGI failing its check sets the record aside;
- an identifier OpenFIGI did not find is set aside (`not_found_by_openfigi`);
- a record joins the Security holding any of its identifiers, or creates
  one: a CUSIP answer and an ISIN answer sharing a listing FIGI make one
  Security, whichever comes first; an ISIN answer whose FIGIs lead to two
  Securities waits for review until ticket 138's merge part;
- every listing lands in silver (`silver-listing.yaml`) with the master id of
  the Security its identifier joined, or none while it waits.
OpenFIGI's three rules are switched on in a copy of the repo's policy, its
FIGI contract given a fixture verification there. Invented values only.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
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
from tests.mdm import policy_layers
from tests.integration import test_nport_link_start as nport
from tests.integration.test_silver_writer_postgres import RUNTIME, silver_database
from tests.support import source_chain as chain
from tests.support.rules_authority import register_dataset

FOLDER = files.ROOT / "sources" / "openfigi"
CODE = "openfigi.security.v3"
THIRTEENF = "sec.thirteenf.information_table.security.v1"
NPORT_ISIN = "sec.nport.security.v2"  # its ISIN-only Securities (ticket 120: one Dataset Contract)
# Invented CUSIPs and ISINs, check digits valid.
EQUITY, BOND, MISSING, UNHELD, SOLE, DOUBLE = "ZZ0000013", "ZZ0000021", "ZZ0000039", "ZZ0000047", "ZZ0000120", "ZZ0000138"
# An answer one of whose listings gives a FIGI failing its check digit.
BROKEN = "ZZ0000146"
# More asked and never found, one to a file, so each of the 8 readings has a file.
OTHERS = ["ZZ0000054", "ZZ0000062", "ZZ0000070", "ZZ0000088", "ZZ0000096", "ZZ0000104", "ZZ0000112"]
# A Japanese ISIN with no US listing: its Japanese composite is its primary listing (ticket 120).
HOME = "JP0000000091"
# An ISIN sharing a listing FIGI with one CUSIP answer (EQUITY's US composite) is that
# Security; one sharing FIGIs with two (SOLE's and DOUBLE's) leads to two (ticket 138).
SHARED, TWICE = "ZZ0000000099", "ZZ0000000107"
ISIN, ISIN_OTHERS = "ZZ0000000016", ["ZZ0000000024", "ZZ0000000032", "ZZ0000000040", "ZZ0000000057",
                                      "ZZ0000000065", "ZZ0000000073", "ZZ0000000081"]


def listing(figi, ticker, exchange, composite, share_class, sector="Equity", name="EXAMPLE CORP"):
    kind = "Common Stock" if sector == "Equity" else "Corporate Bond"
    row = {"figi": figi, **({"name": name} if name else {}), "ticker": ticker, "exchCode": exchange, "securityType": kind,
           "marketSector": sector, "securityType2": kind, "securityDescription": ticker}
    return row | ({"compositeFIGI": composite} if composite else {}) | ({"shareClassFIGI": share_class} if share_class else {})


NOT_FOUND = {"warning": "No identifier found."}
# Invented FIGIs with valid check digits (each is an identifier, ticket 138), named for
# what they stand for; BROKEN's second is the one that fails.
ANSWERS = {
    # A US composite and a German one, one share class: the US composite and its ticker only.
    EQUITY: {"data": [listing("BBGZ0000VS14", "EXA", "US", "BBGZ0000VS14", "BBGZ00000SC6"),
                      listing("BBGZ0000VN15", "EXA", "UN", "BBGZ0000VS14", "BBGZ00000SC6"),
                      listing("BBGZ0000GR13", "EXB", "GR", "BBGZ0000GR13", "BBGZ00000SC6"),
                      listing("BBGZ0000GY18", "EXB", "GY", "BBGZ0000GR13", "BBGZ00000SC6")]},
    BOND: {"data": [listing("BBGZ000BND67", "EXA 5 01/01/30", "NOT LISTED", None, None, sector="Corp")]},
    MISSING: NOT_FOUND,
    # A listing that states no name gives the record none (ticket 84).
    UNHELD: {"data": [listing("BBGZ000BND21", "EXC 4 01/01/31", "NOT LISTED", None, None, sector="Corp", name=None)]},
    # One listing that is its own US composite: its FIGI as both, one ticker.
    SOLE: {"data": [listing("BBGZ0000VS23", "EXD", "US", "BBGZ0000VS23", "BBGZ0000SC22")]},
    # Two US composites (two share classes too): no composite and no ticker.
    DOUBLE: {"data": [listing("BBGZ0000VS32", "EXE", "US", "BBGZ0000VS32", "BBGZ0000SC31"),
                      listing("BBGZ0000VS41", "EXF", "US", "BBGZ0000VS41", "BBGZ0000SC40", name="OTHER CORP")]},
    ISIN: {"data": [listing("BBGZ0000VS50", "EXG", "US", "BBGZ0000VS50", "BBGZ0000SC59"),
                    listing("BBGZ0000LN52", "EXG", "LN", "BBGZ0000LN52", "BBGZ0000SC59")]},
    # Its Japanese and German composites state different names: Japan's, from its ISIN, is primary.
    HOME: {"data": [listing("BBGZ0000JP69", "EXH", "JP", "BBGZ0000JP69", "BBGZ0000SC68", name="HOME CORP"),
                    listing("BBGZ0000GR68", "EXI", "GR", "BBGZ0000GR68", "BBGZ0000SC68", name="OTHER CORP")]},
    SHARED: {"data": [listing("BBGZ0000VS14", "EXA", "US", "BBGZ0000VS14", "BBGZ00000SC6"),
                      listing("BBGZ0000LN98", "EXA", "LN", "BBGZ0000LN98", "BBGZ00000SC6")]},
    TWICE: {"data": [listing("BBGZ0000VS23", "EXD", "US", "BBGZ0000VS23", "BBGZ0000SC22"),
                     listing("BBGZ0000VS32", "EXE", "US", "BBGZ0000VS32", "BBGZ0000SC31")]},
    BROKEN: {"data": [listing("BBGZ0000BK13", "EXJ", "US", "BBGZ0000BK13", None),
                      listing("BBGZZ0000US1", "EXJ", "UN", "BBGZ0000BK13", None)]},
}
KINDS = {"cusip": ("id_cusip", [[EQUITY, BOND, MISSING, UNHELD, SOLE, DOUBLE, BROKEN], *[[o] for o in OTHERS]]),
         "isin": ("id_isin", [[ISIN, HOME, SHARED, TWICE], *[[o] for o in ISIN_OTHERS]])}


def capture(root: Path, word: str) -> list[str]:
    """Eight request and answer files of one kind, as OpenFIGI's mapping takes and gives them."""
    kind, jobs = KINDS[word]
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
    kind, _ = KINDS[word]
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
            "context": context(where / "an", answer, {"batch": batch, "id_type": kind})}], 3))
    return readings


def read_pieces(store: Artifacts, piece_root: Path, combined: str, contract: str) -> str:
    """A source extract over a combination's pieces, as the configured run gives them."""
    piece_root.mkdir(parents=True, exist_ok=True)
    pieces = [store.put(piece_root.as_uri(), {"tables": a["tables"]}) for a in store.json(combined)["artifacts"]]
    return chain.read(store, piece_root, files.load(FOLDER / contract), [
        {"input": p, "context": store.put(piece_root.as_uri(), {"version": 1, "input": p, "values": {}})}
        for p in pieces], 2)


def prepared_records(root: Path, words: tuple[str, ...] = ("cusip", "isin"),
                     listings: list | None = None) -> tuple[list[dict], dict[str, str]]:
    """The records of one run over the answers of `words` (both kinds by
    default, ticket 138), and each refused identifier with its reason;
    `listings`, when given, also gets every listing row of the source extract."""
    store = Artifacts()
    readings = [reading for word in words for reading in answer_readings(store, root / word, word)]
    if listings is not None:
        for reading in readings:
            for artifact in store.json(reading)["artifacts"]:
                for part in artifact["partitions"]:
                    listings += store.json(part["receipt"])["tables"]["listings"]
    counts = chain.combine(store, root / "reduce", FOLDER / "reduce.yaml", {"answers": readings})
    line_counts = chain.combine(store, root / "line_counts", FOLDER / "line-counts.yaml", {"answers": readings})
    lines = chain.combine(store, root / "lines", FOLDER / "lines.yaml", {"counts": line_counts, "answers": readings})
    listing_rows = read_pieces(store, root / "listing", lines, "listing.yaml")
    combined = chain.combine(store, root / "combine", FOLDER / "combine.yaml",
                             {"counts": counts, "answers": readings, "listings": [listing_rows]})
    records = read_pieces(store, root / "record", combined, "record.yaml")
    prepared = chain.prepare(store, root / "mdm", records, {
        "table": "security", "record_column": "record", "dataset": CODE, "policy": "0" * 64,
        "consumer": "check", "batch_id": "check-openfigi", "as_of": "2026-10-17T00:00:00+00:00"})
    refused: dict[str, str] = {}
    out = chain.records(store, root / "mdm", prepared, CODE, files.source("openfigi")["mdm"][CODE]["contract"],
                        refused=refused, key="id")
    return out, refused


OPENFIGI = ("openfigi-security-cusip", "openfigi-security-isin", "openfigi-security-figi")


def policy_body() -> dict:
    """The repo's policy with OpenFIGI's three rules switched on, in this copy only (a
    Proving Run activation): they, and the FIGI contract's verification, wait for the
    operator's switch-on."""
    # N-PORT's two Security rules wait for their switch-on too (ticket 138 part B2).
    body = policy_layers.with_rules_on(files.policy(), "security", *OPENFIGI, "nport-security-cusip", "nport-security-isin")
    body["kinds"]["security"]["identifiers"]["figi"]["verification"] = {
        "corpus_sha256": "f" * 64, "approved_by": "fixture", "approved_at": "2026-10-25T00:00:00Z",
        "reason": "fixture verification: shape only, not a measurement"}
    return body


def figis(word: str) -> list[str]:
    return sorted({row["figi"] for row in ANSWERS[word]["data"]})


def test_each_identifier_carries_only_its_single_levels(tmp_path):
    records, refused = prepared_records(tmp_path, ("cusip",))
    found = {r["provenance"]["record_key"]: r.get("cross_references", {}) for r in records}
    assert found == {
        EQUITY: {"composite_figi": "BBGZ0000VS14", "share_class_figi": "BBGZ00000SC6", "openfigi_ticker": "EXA"},
        BOND: {"openfigi_ticker": "EXA 5 01/01/30"},
        UNHELD: {"openfigi_ticker": "EXC 4 01/01/31"},
        SOLE: {"composite_figi": "BBGZ0000VS23", "share_class_figi": "BBGZ0000SC22", "openfigi_ticker": "EXD"},
        DOUBLE: {},
        BROKEN: {"composite_figi": "BBGZ0000BK13", "openfigi_ticker": "EXJ"},
    }
    # A listed FIGI failing its check digit is left out; the answer stays (ticket 138).
    assert refused == {cusip: "not_found_by_openfigi" for cusip in (MISSING, *OTHERS)}
    # The CUSIP asked and every listing's FIGI (ticket 138): the FIGIs are identifiers.
    assert {r["provenance"]["record_key"]: r["identifiers"] for r in records} == {
        **{c: {"cusip": c, "figi": figis(c)} for c in found if c != BROKEN},
        BROKEN: {"cusip": BROKEN, "figi": ["BBGZ0000BK13"]}}
    # BROKEN's bad FIGI is set aside with its reason, counted, never dropped.
    assert {r["provenance"]["record_key"]: r["provenance"].get("identifiers_set_aside") for r in records}[BROKEN] == [
        {"namespace": "figi", "value": "BBGZZ0000US1", "reason": "invalid_figi"}]
    assert {r["provenance"]["record_key"]: r["identifiers"] for r in records}[EQUITY]["figi"] == [
        "BBGZ0000GR13", "BBGZ0000GY18", "BBGZ0000VN15", "BBGZ0000VS14"]
    # OpenFIGI's name, only where its listings state one (ticket 84): DOUBLE's two names give none.
    names = {r["provenance"]["record_key"]: r["fields"]["name_of_issuer"].get("value") for r in records}
    assert names == {EQUITY: "EXAMPLE CORP", BOND: "EXAMPLE CORP", UNHELD: None, SOLE: "EXAMPLE CORP", DOUBLE: None,
                     BROKEN: "EXAMPLE CORP"}


def test_an_isin_answer_carries_its_isin_and_every_listing_figi(tmp_path):
    """No pairing in the rules (ticket 138: "why do you need to read cusip results in isin
    they are not related"): the ISIN answer's record carries its own identifiers only."""
    records, refused = prepared_records(tmp_path, ("isin",))
    assert {r["provenance"]["record_key"]: r["identifiers"] for r in records} == {
        i: {"isin": i, "figi": figis(i)} for i in (ISIN, HOME, SHARED, TWICE)}
    assert refused == {isin: "not_found_by_openfigi" for isin in ISIN_OTHERS}
    assert {r["provenance"]["record_key"]: r["cross_references"] for r in records if r["provenance"]["record_key"] != TWICE} == {
        ISIN: {"composite_figi": "BBGZ0000VS50", "share_class_figi": "BBGZ0000SC59", "openfigi_ticker": "EXG"},
        HOME: {"share_class_figi": "BBGZ0000SC68", "composite_figi": "BBGZ0000JP69", "openfigi_ticker": "EXH"},
        SHARED: {"share_class_figi": "BBGZ00000SC6", "composite_figi": "BBGZ0000VS14", "openfigi_ticker": "EXA"}}


def bound(database, source_code: str, key: str) -> str | None:
    """The Security a staged record is bound to, through its survivor."""
    return core.bindings(database, source_code).get(key)


def securities(database) -> dict:
    return {k: v for k, v in core.documents(database, "entity").items()
            if v["kind"] == "security" and v.get("status") != "alias"}


def load(database, batches: list[tuple[str, list[dict]]], *registered: str):
    core.register_reading(database, THIRTEENF, core.contract_body())
    core.register_reading(database, NPORT_ISIN, core.contract_body())
    with database.admin.begin() as conn:
        register_dataset(conn, CODE, database.registry, files.mdm_contract("openfigi", CODE))
        policy = register_policy(conn, policy_body())
    stage = MergeStage(Store(database.application))
    for number, (name, records) in enumerate(batches, 1):
        nport.apply(stage, policy, name, records, number)
    return stage, policy


def test_a_record_joins_the_security_holding_its_cusip_or_creates_it(database, tmp_path):
    """A CUSIP answer joins the Security holding its CUSIP (13F's here), or creates one."""
    records, _ = prepared_records(tmp_path, ("cusip",))
    load(database, [
        ("13f", [core.source(key=cusip, source_code=THIRTEENF, kind="security",
                             fields={"name_of_issuer": "Example Corp.", "title_of_class": "COM"},
                             identifiers={"cusip": cusip}) for cusip in (EQUITY, BOND)]),
        ("openfigi", records)])
    # EQUITY and BOND joined 13F's; UNHELD, SOLE, DOUBLE and BROKEN each created one.
    assert len(securities(database)) == 6
    for cusip in (EQUITY, BOND):
        assert bound(database, CODE, cusip) == bound(database, THIRTEENF, cusip) is not None
    # OpenFIGI ranks first for the name; it states no title, so the filed one stays (ticket 84).
    joined = securities(database)[bound(database, CODE, EQUITY)]
    assert (joined["fields"]["name_of_issuer"]["value"], joined["fields"]["title_of_class"]["value"]) == (
        "EXAMPLE CORP", "COM")
    # The Security holds its CUSIP and every listing FIGI (no reverse limit).
    assert joined["status"] == "accepted" and joined["identifiers"] == {"cusip": [EQUITY], "figi": figis(EQUITY)}
    from edgar_warehouse.mdm.clean.record_reads import for_connection
    with database.application.connect() as conn:
        reader = for_connection(conn)
        subjects = reader.subjects([reader.group("cross_reference_records", "composite_figi", "BBGZ0000VS14")])
        (reading,) = reader.readings(subjects).values()
    assert reading["record_key"] == EQUITY


def test_a_filed_figi_finds_its_security_and_never_becomes_one_of_its_identifiers(database, tmp_path):
    """Design 5 (operator, 2026-10-26 14:42 ET: "Lookup only"): a 13F record's
    filed FIGI finds the Security OpenFIGI gave it to, and its unheld CUSIP
    joins that Security; a filed FIGI no Security holds is never given to the
    Security the record creates."""
    from edgar_warehouse.mdm.clean.identifier_types import TYPES
    unheld_figi = next(f"BBG00TSTXX9{d}" for d in "0123456789" if TYPES["figi"].refusal(f"BBG00TSTXX9{d}")[1] is None)
    records, _ = prepared_records(tmp_path, ("cusip",))
    load(database, [
        ("openfigi", records),
        ("13f", [core.source(key=cusip, source_code=THIRTEENF, kind="security",
                             fields={"name_of_issuer": "Example Corp.", "title_of_class": "COM"},
                             identifiers={"cusip": cusip}, cross_references={"figi": filed})
                 for cusip, filed in (("ZZ0000211", figis(EQUITY)[0]), ("ZZ0000229", unheld_figi))])])
    found = securities(database)[bound(database, THIRTEENF, "ZZ0000211")]
    assert bound(database, THIRTEENF, "ZZ0000211") == bound(database, CODE, EQUITY)
    assert found["identifiers"] == {"cusip": sorted([EQUITY, "ZZ0000211"]), "figi": figis(EQUITY)}
    created = securities(database)[bound(database, THIRTEENF, "ZZ0000229")]
    assert created["identifiers"] == {"cusip": ["ZZ0000229"]}


def test_a_held_cusip_stays_on_its_security_whatever_figi_is_filed_with_it(database, tmp_path):
    """"13F CUSIP binds first" (operator, 2026-10-27: "On, set aside put/call"): a
    13F CUSIP a Security holds stays there when its filed FIGI is another
    Security's; nothing merges and nothing waits for review."""
    records, _ = prepared_records(tmp_path, ("cusip",))
    load(database, [
        ("openfigi", records),
        ("13f", [core.source(key=BOND, source_code=THIRTEENF, kind="security", fields={"title_of_class": "NOTE"},
                             identifiers={"cusip": BOND}, cross_references={"figi": figis(EQUITY)[0]})])])
    held = securities(database)[bound(database, THIRTEENF, BOND)]
    assert bound(database, THIRTEENF, BOND) == bound(database, CODE, BOND) != bound(database, CODE, EQUITY)
    assert held["status"] == "accepted" and held["identifiers"]["cusip"] == [BOND]
    assert len(securities(database)) == len(records)


def grouping(database, records) -> list[list[str]]:
    """The record keys each Security holds, through its survivor."""
    groups: dict[str, list[str]] = {}
    for record in records:
        key = record["provenance"]["record_key"]
        groups.setdefault(bound(database, CODE, key), []).append(key)
    return sorted(sorted(keys) for keys in groups.values())


@pytest.mark.parametrize("order", ["isin_first", "cusip_first"])
def test_openfigi_answers_in_either_order_make_the_same_securities(database, tmp_path, order):
    """Ticket 138 ("first lookup if not exists then master"; part A2a, the FIGI rule
    merges): SHARED's ISIN answer shares EQUITY's US composite listing, so they are one
    Security; TWICE's FIGIs are SOLE's and DOUBLE's, so the three are one. ISIN answers
    first, TWICE creates it and SOLE and DOUBLE join it; CUSIP answers first, SOLE and
    DOUBLE are two Securities when TWICE comes, and TWICE merges them, the oldest
    surviving. Either way the same Securities, holding the same records."""
    records, _ = prepared_records(tmp_path)
    isins = [r for r in records if r["identifiers"].get("isin")]
    cusips = [r for r in records if r["identifiers"].get("cusip")]
    first, second = (isins, cusips) if order == "isin_first" else (cusips, isins)
    stage, policy = load(database, [("openfigi-1", first), ("openfigi-2", second)])
    assert grouping(database, records) == sorted([
        sorted([EQUITY, SHARED]), sorted([SOLE, DOUBLE, TWICE]),
        [BOND], [UNHELD], [BROKEN], [ISIN], [HOME]])
    assert None not in {bound(database, CODE, r["provenance"]["record_key"]) for r in records}
    assert len(securities(database)) == 7
    equity = bound(database, CODE, EQUITY)
    assert securities(database)[equity]["identifiers"] == {
        "cusip": [EQUITY], "isin": [SHARED], "figi": sorted({*figis(EQUITY), *figis(SHARED)})}
    merged = securities(database)[bound(database, CODE, TWICE)]
    assert merged["identifiers"] == {"cusip": sorted([SOLE, DOUBLE]), "isin": [TWICE],
                                     "figi": sorted({*figis(SOLE), *figis(DOUBLE)})}
    assert not [v for v in core.documents(database, "review").values() if v.get("open")]
    if order == "cusip_first":
        # The merged-away Security points at its survivor, the one created first.
        entities = core.documents(database, "entity")
        aliases = [e for e in entities.values() if e["kind"] == "security" and e.get("status") == "alias"]
        assert [a["canonical_id"] for a in aliases] == [merged["entity_id"]]
    nport.apply(stage, policy, "nport", [core.source(key=EQUITY, source_code=NPORT_ISIN, kind="security",
                                                     fields={"name_of_issuer": "EXAMPLE CORP"},
                                                     identifiers={"cusip": EQUITY, "isin": SHARED})], 3)
    assert bound(database, NPORT_ISIN, EQUITY) == equity and len(securities(database)) == 7


def test_an_isin_record_joins_the_security_holding_its_isin(database, tmp_path):
    records, _ = prepared_records(tmp_path, ("isin",))
    load(database, [
        ("nport", [core.source(key=ISIN, source_code=NPORT_ISIN, kind="security",
                               fields={"name_of_issuer": "EXAMPLE CORP"}, identifiers={"isin": ISIN})]),
        ("openfigi", [r for r in records if r["provenance"]["record_key"] == ISIN])])
    assert bound(database, CODE, ISIN) == bound(database, NPORT_ISIN, ISIN) is not None
    assert len(securities(database)) == 1


def test_every_listing_lands_in_silver_with_the_security_its_identifier_joined(database, tmp_path):
    rows: list[dict] = []
    records, _ = prepared_records(tmp_path, listings=rows)
    # The Securities' own records are keyed apart from the identifier, so only
    # OpenFIGI's Dataset Contract finds a listing's Security by its identifier.
    load(database, [
        ("13f", [core.source(key="13F-ROW-1", source_code=THIRTEENF, kind="security",
                             fields={"name_of_issuer": "EXAMPLE CORP"}, identifiers={"cusip": EQUITY})]),
        ("nport", [core.source(key="NPORT-ROW-1", source_code=NPORT_ISIN, kind="security",
                               fields={"name_of_issuer": "EXAMPLE CORP"}, identifiers={"isin": ISIN})]),
        # CUSIP answers first: TWICE's ISIN answer merges SOLE's and DOUBLE's Securities.
        ("openfigi-cusip", [r for r in records if r["identifiers"].get("cusip")]),
        ("openfigi-isin", [r for r in records if r["identifiers"].get("isin")])])
    rows = [{k: v for k, v in row.items() if k != "figi_ticker"} for row in rows]
    with silver_database(database.admin) as (owner, runtime):
        silver.migrate(owner, runtime_role=RUNTIME)
        spec = spec_file(FOLDER / "silver-listing.yaml", None)
        assert silver.register(owner, spec, runtime_role=RUNTIME)["created"] is True
        sink, ids = PostgresSink(runtime), MdmIds(database.application)
        assert land(sink, spec["table"], copy.deepcopy(rows), ids)["inserted"] == 19
        again = land(sink, spec["table"], copy.deepcopy(rows), ids)  # the same delivery changes nothing
        assert (again["inserted"], again["changed"]) == (0, 0)
        with runtime.connect() as conn:
            landed = {(r["id"], r["figi"]): r for r in conn.execute(text(
                "SELECT * FROM silver.openfigi_listing")).mappings()}
    # The answers' 11 CUSIP and 8 ISIN listings, each once; unfound identifiers give none.
    assert len(landed) == len(rows) == 19
    equity, isin = bound(database, CODE, EQUITY), bound(database, CODE, ISIN)
    assert equity == bound(database, THIRTEENF, "13F-ROW-1") is not None
    assert isin == bound(database, NPORT_ISIN, "NPORT-ROW-1") is not None
    # One master id a row (ticket 138: "master_id only"); SHARED's listings are EQUITY's Security.
    assert {k[1]: r["security_mdm_id"] for k, r in landed.items() if k[0] in (EQUITY, ISIN, SHARED)} == {
        **{f: equity for f in (*figis(EQUITY), *figis(SHARED))}, **{f: isin for f in figis(ISIN)}}
    assert landed[(EQUITY, "BBGZ0000GR13")]["ticker"] == "EXB"
    # Every FIGI but BROKEN's second passes its check; that one is flagged and still lands,
    # with the master id of BROKEN's Security (its answer kept, that FIGI left out).
    assert {k for k, r in landed.items() if r["quality"]} == {(BROKEN, "BBGZZ0000US1")}
    assert landed[(BROKEN, "BBGZZ0000US1")]["security_mdm_id"] == bound(database, CODE, BROKEN) is not None
    assert landed[(UNHELD, "BBGZ000BND21")]["security_mdm_id"] == bound(database, CODE, UNHELD) is not None
    # TWICE's FIGIs are SOLE's and DOUBLE's: it merged their Securities (part A2a), so
    # every listing of the three carries the survivor's id, never the merged-away one.
    survivor = bound(database, CODE, TWICE)
    assert survivor in securities(database)
    assert {r["security_mdm_id"] for k, r in landed.items() if k[0] in (SOLE, DOUBLE, TWICE)} == {survivor}


def test_a_securitys_fields_are_the_agreed_or_the_primary_listings_and_every_listing_is_a_detail_row(tmp_path):
    """Ticket 120 (operator, 2026-10-20: "all fields from open figi must be in the security
    master", "Use the primary exchange listing", "US, else the ISIN's country", "Detail rows
    set in config"): a field the listings agree on; else the one US composite's; else the
    ISIN country's composite's (rules/reference/published/openfigi-country-composite); else none.
    Every listing is a detail row keyed by its FIGI."""
    records, _ = prepared_records(tmp_path, ("cusip",))
    by_key = {r["provenance"]["record_key"]: r for r in records}
    equity = by_key[EQUITY]
    assert {k: equity["fields"][k]["value"] for k in ("name_of_issuer", "security_type", "security_type2",
                                                       "market_sector")} == {
        "name_of_issuer": "EXAMPLE CORP", "security_type": "Common Stock", "security_type2": "Common Stock",
        "market_sector": "Equity"}
    # The share class FIGI is a cross-reference only, never a field too (ticket 129, "Fix 4").
    assert "share_class_figi" not in equity["fields"]
    assert [(r["key"], r["exchange"], r["ticker"]) for r in equity["details"]["listings"]] == [
        ("BBGZ0000GR13", "GR", "EXB"), ("BBGZ0000GY18", "GY", "EXB"), ("BBGZ0000VN15", "UN", "EXA"),
        ("BBGZ0000VS14", "US", "EXA")]
    assert equity["details"]["listings"][3] == {"key": "BBGZ0000VS14", "exchange": "US", "ticker": "EXA",
                                                "composite_figi": "BBGZ0000VS14", "description": "EXA"}
    # Two US composites and two names: no primary listing, so no name; the type they share stays.
    double = by_key[DOUBLE]
    assert double["fields"]["name_of_issuer"].get("value") is None
    assert double["fields"]["security_type"]["value"] == "Common Stock"
    assert len(double["details"]["listings"]) == 2

    isin_records, _ = prepared_records(tmp_path / "isins", ("isin",))
    home = {r["provenance"]["record_key"]: r for r in isin_records}[HOME]
    # No US listing; the names differ; Japan's composite, from the ISIN's country, gives the name.
    assert home["fields"]["name_of_issuer"]["value"] == "HOME CORP"
    assert [r["key"] for r in home["details"]["listings"]] == ["BBGZ0000GR68", "BBGZ0000JP69"]


def test_the_country_table_in_the_reading_is_the_published_code_set():
    """The reading embeds RDM's openfigi-country-composite version 1, row for row."""
    published = Path(files.ROOT / "reference" / "published" / "openfigi-country-composite" / "1" / "canonical.jsonl")
    codes = {row["code"]: row["crosswalk"][0][2] for row in map(json.loads, published.read_text().splitlines())}
    embedded = files.source("openfigi")["read"]["references"]["country_composite"]
    assert {code: row["exchange"] for code, row in embedded.items()} == codes and len(codes) == 11


# One invented answer holding every case of the Listing currency rule (ticket 138 part B3):
# a line's currency is the last three letters of its ticker, a code N-PORT holdings file
# (rules/reference/published/nport-filed-currencies), read only where one exchange gives
# the identifier two or more lines, every ticker different and all one root (the root
# alone, as a line, gets none: "blank where none").
LINES = "ZZ0000161"
CURRENCY_CASES = {
    # exchange: [(FIGI, ticker, currency)]
    "EU": [("BBGZ000CY016", "EXKUSD", "USD"), ("BBGZ000CY025", "EXKEUR", "EUR"), ("BBGZ000CY034", "EXKGBP", "GBP")],
    "XV": [("BBGZ000CY043", "EXK", None), ("BBGZ000CY052", "EXKUSD", "USD"), ("BBGZ000CY061", "EXKCHF", "CHF")],
    # A code repeated.
    "XW": [("BBGZ000CY070", "EXKUSD", None), ("BBGZ000CY089", "EXKUSD", None)],
    # Two roots.
    "XO": [("BBGZ000CY098", "EXKUSD", None), ("BBGZ000CY105", "EXLEUR", None)],
    # One line ending in a code by chance.
    "US": [("BBGZ000CY114", "EXKUSD", None)],
    # A ticker that is only a code has no root: it is a plain ticker.
    "XA": [("BBGZ000CY123", "EUR", None), ("BBGZ000CY132", "USD", None)],
    # Letters no holding files are not a code.
    "XG": [("BBGZ000CY141", "EXKXYZ", None), ("BBGZ000CY150", "EXKUSD", None)],
    # No exchange code: the lines without one are one group, as measured.
    None: [("BBGZ000CY169", "EXMUSD", "USD"), ("BBGZ000CY178", "EXMEUR", "EUR")],
    # Two plain lines.
    "XH": [("BBGZ000CY187", "EXN", None), ("BBGZ000CY196", "EXP", None)],
    # A plain line that is not the coded lines' root.
    "XF": [("BBGZ000CY203", "EXQX", None), ("BBGZ000CY212", "EXQUSD", None)],
}


def test_a_listing_currency_is_its_tickers_code_only_where_its_exchange_lines_differ_by_code(tmp_path, monkeypatch):
    monkeypatch.setitem(ANSWERS, LINES, {"data": [
        listing(figi, ticker, exchange, None, None) for exchange, rows in CURRENCY_CASES.items()
        for figi, ticker, _ in rows]})
    monkeypatch.setitem(KINDS, "cusip", ("id_cusip", [[LINES], *[[o] for o in OTHERS]]))
    records, _ = prepared_records(tmp_path, ("cusip",))
    (record,) = records
    found = {row["key"]: row.get("currency") for row in record["details"]["listings"]}
    assert found == {figi: currency for rows in CURRENCY_CASES.values() for figi, _, currency in rows}


def test_the_currency_table_in_the_reading_is_the_published_code_set():
    """The reading embeds RDM's nport-filed-currencies version 1, row for row."""
    published = Path(files.ROOT / "reference" / "published" / "nport-filed-currencies" / "1" / "canonical.jsonl")
    codes = {row["code"] for row in map(json.loads, published.read_text().splitlines())}
    embedded = files.source("openfigi")["read"]["references"]["currency"]
    assert {code: row["code"] for code, row in embedded.items()} == {c: c for c in codes} and len(codes) == 80


def test_a_listing_detail_row_keeps_every_field_the_source_extract_gives_it():
    """listing.yaml rebuilds each detail row to add its currency: it keeps every field of
    source.yaml's `detail`, so a field added there is never dropped on the way to MDM."""
    given = files.source("openfigi")["read"]["tables"]["details"]["columns"]["detail"]["object"]["fields"]
    kept = files.load(FOLDER / "listing.yaml")["read"]["tables"]["listings"]["columns"]["detail"]["object"]["fields"]
    assert set(kept) == set(given) | {"currency"}
    assert all(kept[name] == {"value": {"path": f"detail.{name}"}} for name in given)
