"""Real PG16: an N-PORT link starts at its quarter's data set (ticket 100).

The real chain on invented holdings: the holdings and issuer source extracts
(the run supplies `period` in each reading's context), reduce.yaml,
issuer-reduce.yaml, combine.yaml, mdm.prepare dated by `period`
(`effective_column`), the Dataset Contract, then the Merge Stage on a
disposable PostgreSQL 16: the ISSUED_BY link resolves and starts, as
observed, at the quarter; a later quarter, a later revision, keeps that start
(ticket 101). Invented values only.
"""

from __future__ import annotations

import copy
import io
import json
import zipfile
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean import adapters
from edgar_warehouse.mdm.clean.evidence import subject_key
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, register_policy
from edgar_warehouse.rules import files
from edgar_warehouse.workers import mdm_prepare, source_combine, source_read
from tests.integration import test_clean_mdm_postgres as core
from tests.support.rules_authority import register_dataset


NAME, CODE, GLEIF, ADV = "sec.nport.security", "sec.nport.security.v1", "gleif.level1.v1", "iapd.adv.custodians.v1"
FOLDER = files.ROOT / "sources" / NAME
LEI = "9999000000EXAMPLE016"  # invented, check digits valid
COLUMNS = ["HOLDING_ID", "ISSUER_NAME", "ISSUER_LEI", "ISSUER_TITLE", "ISSUER_CUSIP"]
HOLDINGS = [["1", "Example Corp", LEI, "Common", "ZZ0000013"],
            ["2", "Example Corp", LEI, "Common", "ZZ0000013"],
            ["3", "Other Inc", "", "Common", "ZZ0000021"]]
Q2, Q3 = "2026-06-30T00:00:00+00:00", "2026-09-30T00:00:00+00:00"


def capture(root: Path, holdings: list[list[str]]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "nport.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("FUND_REPORTED_HOLDING.tsv", "\n".join("\t".join(r) for r in [COLUMNS, *holdings]) + "\n")
        z.writestr("IDENTIFIERS.tsv", "HOLDING_ID\tIDENTIFIER_ISIN\n")
    return path


def read(store, root, contract_file, raw, period, lookups=None):
    root.mkdir(parents=True, exist_ok=True)
    body = {"source": NAME, **files.load(FOLDER / contract_file)}
    context = store.put(root.as_uri(), {"version": 1, "input": raw, "values": {"period": period} if period else {}})
    entry = {"input": raw, "context": context}
    if lookups is not None:
        entry["lookups"] = store.put(root.as_uri(), {"version": 1, "input": raw, "sets": lookups})
    manifest = store.put(root.as_uri(), {"version": 3 if lookups is not None else 2,
                                         "contract": store.put(root.as_uri(), body), "artifacts": [entry]})
    task = {"input": manifest, "output": (root / "reading.json").as_uri(), "checks": ["source.output"]}
    out = source_read.execute(task, store)
    assert source_read.verify({**task, "candidate": out}, store) == ({"source.output": True}, [])
    return out


def combine(store, root, contract_file, readings):
    root.mkdir(parents=True, exist_ok=True)
    m = store.put(root.as_uri(), {"version": 1, "contract": store.put(root.as_uri(), files.load(FOLDER / contract_file)),
                                  "readings": readings})
    task = {"input": m, "output": (root / "out.json").as_uri(), "checks": [source_combine.CHECK], "keys": {}}
    out = source_combine.execute(task, store)
    assert source_combine.verify({**task, "candidate": out}, store) == ({source_combine.CHECK: True}, [])
    return out


def prepared_records(root: Path, period: str, revision: int | None = None,
                     rows: list[list[str]] = HOLDINGS, umbrella: tuple[list[str], ...] = ()) -> list[dict]:
    """The quarter's Security assertions, through the real chain; `umbrella`
    pairs each fund LEI with the trust it is a sub-fund of."""
    store = Artifacts()
    zipped = capture(root, rows)
    raw = store.put_bytes((root / "capture.zip").as_uri(), zipped.read_bytes())
    holdings = read(store, root / "holdings", "source.yaml", raw, period, lookups={"isin": []})
    issuers = read(store, root / "issuers", "issuers.yaml", raw, None, lookups={"isin": [], "umbrella": list(umbrella)})
    securities = combine(store, root / "reduce", "reduce.yaml", {"holdings": holdings})
    reduced = combine(store, root / "issuer-reduce", "issuer-reduce.yaml", {"issuers": issuers})
    attached = store.put(root.as_uri(), {"version": 1, "artifacts": [
        {"input": raw, "tables": {"attached": []}, "deferred": []}]})
    combined = combine(store, root / "combine", "combine.yaml",
                       {"securities": securities, "attached": attached, "issuers": reduced})
    task = {"input": combined, "output": (root / "mdm/manifest.json").as_uri(), "checks": ["mdm.prepared"],
            "keys": {"table": "security", "dataset": CODE, "policy": "0" * 64, "consumer": "check",
                     "batch_id": f"check-{period[:10]}", "as_of": "2026-10-16T00:00:00+00:00",
                     # One quarter dates its publication by its column; quarters that
                     # follow one another are revisions stating their own time (ticket 101).
                     **({"effective_column": "period"} if revision is None else
                        {"publication_key": f"nport:{period[:10]}", "revision": str(revision),
                         "effective_at": period})}}
    prepared = mdm_prepare.execute(task, store)
    assert mdm_prepare.verify({**task, "candidate": prepared}, store) == ({"mdm.prepared": True}, [])
    contract = files.source(NAME)["mdm"][CODE]["contract"]
    out = []
    for b in store.json(prepared)["batches"]:
        assert b["input"]["publication"]["effective_at"] == period
        for line in (root / "mdm" / b["input"]["path"]).read_bytes().splitlines():
            out.append(adapters.normalize(json.loads(line), source_code=CODE, contract=contract, publication={
                **b["input"]["publication"], "semantics": "patch", "artifact_sha256": b["input"]["sha256"],
                "member": b["input"]["path"], "record_locator": f"{b['input']['sha256']}:{len(out)}"}))
    return out


def policy_body() -> dict:
    body = copy.deepcopy(files.policy())
    company = body["kinds"]["company"]
    company["identifiers"]["lei"]["verification"] = {
        "corpus_sha256": "0" * 64, "approved_by": "check", "approved_at": core.AS_OF, "reason": "check only"}
    body["kinds"]["security"]["identifiers"]["cusip"].setdefault("verification", {
        "corpus_sha256": "0" * 64, "approved_by": "check", "approved_at": core.AS_OF, "reason": "check only"})
    for kind, rule_id in (("company", "iapd-adv-custodian-lei"), ("company", "gleif-issuer-lei"),
                          ("security", "nport-security-cusip")):
        rule = next(r for r in body["kinds"][kind]["rules"] if r["rule_id"] == rule_id)
        body["automatic_rules"].append({"kind": kind, "family": "binding", "rule_id": rule_id,
                                        "rule_version": rule["version"], "verdict": "bind",
                                        "activation": "deterministic"})
    return body


def apply(stage, policy, batch, assertions, checkpoint):
    stage.apply(batch_id=batch, run_id=str(uuid4()), policy_digest=policy, consumer="check",
                expected_checkpoint=checkpoint - 1, checkpoint=checkpoint, as_of="2026-10-16T00:00:00+00:00",
                assertions=assertions)


def mastered_issuer(database):
    """The policy registered, and the issuer's Company: an ADV custodian gives it
    the LEI, and the issuer's GLEIF record joins it."""
    for code in (ADV, GLEIF):
        core.register_reading(database, code, core.contract_body())
    with database.admin.begin() as conn:
        register_dataset(conn, CODE, database.registry, files.mdm_contract(NAME, CODE))
        policy = register_policy(conn, policy_body())
    stage = MergeStage(Store(database.application))
    apply(stage, policy, "custodian", [core.source(key="custodian", source_code=ADV, fields={"name": "Example Corp"},
                                                   identifiers={"lei": LEI})], 1)
    apply(stage, policy, "gleif", [core.source(key=LEI, source_code=GLEIF, fields={"name": "Example Corp"},
                                               identifiers={"lei": LEI},
                                               provenance={"matching": {"nport_issuer": True}})], 2)
    return stage, policy


def issued_by(database):
    with database.application.connect() as conn:
        return conn.execute(text(
            "SELECT body->'periods', body->>'last_seen' FROM mdm.current_record WHERE object_type='relationship' "
            "AND body->>'type'='ISSUED_BY'")).all()


def test_an_issued_by_link_starts_at_its_quarter(database, tmp_path):
    """Without the quarter dating each publication, the link has no start and
    goes to review (`unknown_relationship_start`), as in ticket 22's Proving Run 2."""
    q2 = prepared_records(tmp_path / "q2", Q2)
    linked = [r for r in q2 if any(l["type"] == "ISSUED_BY" for l in r.get("relationships") or [])]
    assert len(q2) == 2 and len(linked) == 1
    stage, policy = mastered_issuer(database)
    apply(stage, policy, "q2", q2, 3)
    with database.application.connect() as conn:
        periods = [json.loads(p) if isinstance(p, str) else p for (p,) in conn.execute(text(
            "SELECT body->'periods' FROM mdm.current_record WHERE object_type='relationship' "
            "AND body->>'type'='ISSUED_BY'")).all()]
        reviews = conn.execute(text("SELECT body->>'reason' FROM mdm.current_record WHERE object_type='review' "
                                    "AND body->'open'='true'::jsonb")).scalars().all()
    assert "unknown_relationship_start" not in reviews
    (only,) = periods
    assert [(p["valid_from"], p["valid_from_basis"]) for p in only] == [(Q2, "observed")]


def test_a_later_quarter_keeps_the_first_start(database, tmp_path):
    q2 = prepared_records(tmp_path / "q2", Q2, revision=20262)
    q3 = prepared_records(tmp_path / "q3", Q3, revision=20263)
    stage, policy = mastered_issuer(database)
    apply(stage, policy, "q2", q2, 3)
    apply(stage, policy, "q3", q3, 4)
    ((periods, last_seen),) = issued_by(database)
    assert [(p["valid_from"], p["valid_from_basis"]) for p in periods] == [(Q2, "observed")]
    assert last_seen == Q3


def test_a_fund_series_counts_as_its_umbrella_trust(tmp_path):
    """Ticket 23 (operator, 2026-10-17: "Umbrella trust (Recommended)"): holdings
    naming a fund series and its trust give one issuer, the trust; without the
    pair the two LEIs leave the Security with no link."""
    trust = "9999000000EXAMPLE113"  # invented
    holdings = [["1", "Example Fund", LEI, "ETF", "ZZ0000013"],
                ["2", "Example Fund", LEI, "ETF", "ZZ0000013"],
                ["3", "Example Trust", trust, "ETF", "ZZ0000013"]]
    pairs = ([LEI, trust],)
    (linked,) = prepared_records(tmp_path / "with", Q2, rows=holdings, umbrella=pairs)
    def targets(record):
        return [l["target_subject"] for l in record.get("relationships") or [] if l["type"] == "ISSUED_BY"]

    assert targets(linked) == [subject_key(GLEIF, trust)]
    (unpaired,) = prepared_records(tmp_path / "without", Q2, rows=holdings)
    assert targets(unpaired) == []
