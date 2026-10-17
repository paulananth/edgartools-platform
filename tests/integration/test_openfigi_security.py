"""Real PG16: OpenFIGI answers join the Securities they were asked for (ticket 80).

Invented answer files through the real chain (requests.yaml, the streamed
answers reading, reduce.yaml, answers-union.yaml, combine.yaml, record.yaml,
mdm.prepare and the CUSIP Dataset Contract), then the Merge Stage beside a
13F Security:
- an equity keeps its one share class, and its US composite with that
  composite's ticker, never another country's;
- a bond's only listing gives its FIGI and its ticker, spaces kept;
- an identifier OpenFIGI did not find is set aside (`not_found_by_openfigi`);
- a record joins the Security that holds its CUSIP, and one no Security holds
  waits: OpenFIGI never creates a Security.
The rule is switched on here only, in a copy of the repo's policy.
Invented values only.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from sqlalchemy import text

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean import adapters
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, register_policy
from edgar_warehouse.rules import files
from edgar_warehouse.workers import mdm_prepare, source_combine, source_read
from tests.integration import test_clean_mdm_postgres as core
from tests.integration import test_nport_link_start as nport
from tests.support.rules_authority import register_dataset

FOLDER = files.ROOT / "sources" / "openfigi"
CODE = "openfigi.security.v1"
THIRTEENF = "sec.thirteenf.information_table.security.v1"
EQUITY, BOND, MISSING, UNHELD = "ZZ0000013", "ZZ0000021", "ZZ0000039", "ZZ0000047"  # check digits valid
# Seven more asked, never found, one to a file, so each of the 8 readings has a file.
OTHERS = ["ZZ0000054", "ZZ0000062", "ZZ0000070", "ZZ0000088", "ZZ0000096", "ZZ0000104", "ZZ0000112"]


def listing(figi, ticker, exchange, composite, share_class, sector="Equity"):
    row = {"figi": figi, "name": "EXAMPLE CORP", "ticker": ticker, "exchCode": exchange, "securityType": "Common Stock",
           "marketSector": sector, "securityType2": "Common Stock", "securityDescription": ticker}
    return row | ({"compositeFIGI": composite} if composite else {}) | ({"shareClassFIGI": share_class} if share_class else {})


NOT_FOUND = {"warning": "No identifier found."}
ANSWERS = {
    EQUITY: {"data": [listing("BBGZZ0000US1", "EXA", "US", "BBGZZ0000US1", "BBGZZ00000SC"),
                      listing("BBGZZ0000UN1", "EXA", "UN", "BBGZZ0000US1", "BBGZZ00000SC"),
                      listing("BBGZZ0000GR1", "EXB", "GR", "BBGZZ0000GR1", "BBGZZ00000SC"),
                      listing("BBGZZ0000GY1", "EXB", "GY", "BBGZZ0000GR1", "BBGZZ00000SC")]},
    BOND: {"data": [listing("BBGZZ000BND1", "EXA 5 01/01/30", "NOT LISTED", None, None, sector="Corp")]},
    MISSING: NOT_FOUND,
    UNHELD: {"data": [listing("BBGZZ000BND2", "EXC 4 01/01/31", "NOT LISTED", None, None, sector="Corp")]},
}


def capture(root: Path) -> dict[str, list[str]]:
    """Eight request and answer files of CUSIPs, as OpenFIGI's mapping takes and gives them."""
    jobs = [[EQUITY, BOND, MISSING, UNHELD], *[[other] for other in OTHERS]]
    names = []
    for number, asked in enumerate(jobs):
        name = f"{number:05d}.json"
        (root / "id_cusip").mkdir(parents=True, exist_ok=True)
        (root / "id_cusip" / name.replace(".json", ".request.json")).write_text(
            json.dumps([{"idType": "ID_CUSIP", "idValue": cusip} for cusip in asked]))
        (root / "id_cusip" / name).write_text(json.dumps([ANSWERS.get(cusip, NOT_FOUND) for cusip in asked]))
        names.append(name)
    return {"id_cusip": names}


def run(store: Artifacts, root: Path, body: dict, artifacts: list, version: int) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    manifest = store.put(root.as_uri(), {"version": version, "contract": store.put(root.as_uri(), body),
                                         "artifacts": artifacts})
    task = {"input": manifest, "output": (root / "reading.json").as_uri(), "checks": ["source.output"]}
    out = source_read.execute(task, store)
    assert source_read.verify({**task, "candidate": out}, store) == ({"source.output": True}, [])
    return out


def combine(store: Artifacts, root: Path, contract_file: str, readings: dict) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    m = store.put(root.as_uri(), {"version": 1, "contract": store.put(root.as_uri(), files.load(FOLDER / contract_file)),
                                  "readings": readings})
    task = {"input": m, "output": (root / "out.json").as_uri(), "checks": [source_combine.CHECK], "keys": {}}
    out = source_combine.execute(task, store)
    assert source_combine.verify({**task, "candidate": out}, store) == ({source_combine.CHECK: True}, [])
    return out


def prepared_records(root: Path) -> tuple[list[dict], dict[str, str]]:
    """The CUSIP contract's records, and each refused identifier with its reason."""
    store = Artifacts()
    capture_root = root / "capture"
    (name_list,) = capture(capture_root).values()

    def ref(path: Path) -> dict:
        return {"uri": path.as_uri(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def context(where: Path, path: Path, values: dict) -> dict:
        where.mkdir(parents=True, exist_ok=True)
        return store.put(where.as_uri(), {"version": 1, "input": ref(path), "values": values})

    answers_body = {k: v for k, v in files.source("openfigi").items() if k in ("source", "execution", "read")}
    readings = {}
    for number, name in enumerate(name_list, 1):
        where, batch = root / f"answers_{number}", f"id_cusip/{name.split('.')[0]}"
        request = capture_root / "id_cusip" / name.replace(".json", ".request.json")
        asked = run(store, where / "requests", files.load(FOLDER / "requests.yaml"),
                    [{"input": ref(request), "context": context(where / "rq", request, {"batch": batch})}], 2)
        answer = capture_root / "id_cusip" / name
        lookups = store.put(where.as_uri(), {"version": 2, "input": ref(answer), "sets": {"asked": {
            "readings": [asked], "table": "asked", "column": "key", "value_column": "id",
            "max_input_bytes": 1 << 20, "max_input_rows": 1000}}})
        readings[f"answers_{number}"] = run(store, where / "answers", answers_body, [{
            "input": ref(answer), "lookups": lookups,
            "context": context(where / "an", answer, {"batch": batch, "id_type": "cusip"})}], 3)
    counts = combine(store, root / "reduce", "reduce.yaml", readings)
    union = combine(store, root / "union", "answers-union.yaml", readings)
    combined = combine(store, root / "combine", "combine.yaml", {"answers": union, "counts": counts})
    piece_root = root / "record"
    piece_root.mkdir(parents=True, exist_ok=True)
    pieces = [store.put(piece_root.as_uri(), {"tables": a["tables"]}) for a in store.json(combined)["artifacts"]]
    records = run(store, piece_root, files.load(FOLDER / "record.yaml"), [
        {"input": p, "context": store.put(piece_root.as_uri(), {"version": 1, "input": p, "values": {}})}
        for p in pieces], 2)
    task = {"input": records, "output": (root / "mdm/manifest.json").as_uri(), "checks": ["mdm.prepared"],
            "keys": {"table": "security", "record_column": "record", "dataset": CODE, "policy": "0" * 64,
                     "consumer": "check", "batch_id": "check-openfigi", "as_of": "2026-10-17T00:00:00+00:00"}}
    prepared = mdm_prepare.execute(task, store)
    assert mdm_prepare.verify({**task, "candidate": prepared}, store) == ({"mdm.prepared": True}, [])
    contract = files.source("openfigi")["mdm"][CODE]["contract"]
    out, refused = [], {}
    for b in store.json(prepared)["batches"]:
        for line in (root / "mdm" / b["input"]["path"]).read_bytes().splitlines():
            row = json.loads(line)
            try:
                out.append(adapters.normalize(row, source_code=CODE, contract=contract, publication={
                    **b["input"]["publication"], "semantics": "patch", "artifact_sha256": b["input"]["sha256"],
                    "member": b["input"]["path"], "record_locator": f"{b['input']['sha256']}:{len(out)}"}))
            except adapters.UnsupportedRecord as error:
                refused[row["id"]] = error.reason
    return out, refused


def policy_body() -> dict:
    body = copy.deepcopy(files.policy())
    rule = next(r for r in body["kinds"]["security"]["rules"] if r["rule_id"] == "openfigi-security-cusip")
    body["automatic_rules"].append({"kind": "security", "family": "binding", "rule_id": rule["rule_id"],
                                    "rule_version": rule["version"], "verdict": "bind",
                                    "activation": "deterministic"})
    return body


def test_each_identifier_carries_only_its_single_levels(tmp_path):
    records, refused = prepared_records(tmp_path)
    found = {r["provenance"]["record_key"]: r["cross_references"] for r in records}
    assert found == {
        EQUITY: {"composite_figi": "BBGZZ0000US1", "share_class_figi": "BBGZZ00000SC", "openfigi_ticker": "EXA"},
        BOND: {"figi": "BBGZZ000BND1", "openfigi_ticker": "EXA 5 01/01/30"},
        UNHELD: {"figi": "BBGZZ000BND2", "openfigi_ticker": "EXC 4 01/01/31"},
    }
    assert refused == {cusip: "not_found_by_openfigi" for cusip in (MISSING, *OTHERS)}


def bound(database, source_code: str, key: str) -> str | None:
    with database.application.connect() as conn:
        return conn.scalar(text("SELECT entity_id::text FROM mdm.stage_record WHERE source_code = :s "
                                "AND record_key = :k"), {"s": source_code, "k": key})


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
    assert bound(database, CODE, UNHELD) is None
    with database.application.connect() as conn:
        (row,) = conn.execute(text("SELECT * FROM mdm.cross_reference_lookup('composite_figi', 'BBGZZ0000US1')")).all()
    assert row._mapping["record_key"] == EQUITY
