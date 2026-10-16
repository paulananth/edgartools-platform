"""Real PG16: an ISIN-only N-PORT Security links to its issuer (ticket 102).

The real chain on invented holdings with no usable CUSIP: the holdings and
issuer source extracts (each ISIN from the `isin` pair set), reduce.yaml,
issuer-reduce.yaml, combine.yaml, mdm.prepare dated by `period`, the ISIN
Dataset Contract, then the Merge Stage: an ISIN whose holdings state one
issuer LEI gets ISSUED_BY, starting at the quarter; an ISIN with two LEIs or
none gets no link. Invented values only.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from sqlalchemy import text

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean import adapters
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, register_policy
from edgar_warehouse.rules import files
from edgar_warehouse.workers import mdm_prepare
from tests.integration import test_clean_mdm_postgres as core
from tests.integration import test_nport_link_start as cusip
from tests.support.rules_authority import register_dataset


CODE = "sec.nport.security_isin.v1"
LEI, OTHER = cusip.LEI, "9999000000EXAMPLE024"  # invented; OTHER is LEI-shaped only
ONE, TWO, NONE = "ZZ0000000016", "ZZ0000000024", "ZZ0000000032"  # invented, check digits valid
HOLDINGS = [["4", "Example Corp", LEI, "Note"], ["5", "Example Corp", LEI, "Note"],
            ["6", "Example Corp", LEI, "Bond"], ["7", "Example Corp", OTHER, "Bond"],
            ["8", "Other Inc", "", "Bond"]]
# A holding with a usable CUSIP stays out of the ISIN's issuers: were it read
# there, ONE would hold two LEIs and lose its link.
WITH_CUSIP = ["9", "Example Corp", OTHER, "Note", "ZZ0000013"]
PAIRS = [["4", ONE], ["5", ONE], ["6", TWO], ["7", TWO], ["8", NONE], ["9", ONE]]


def policy_body() -> dict:
    """The CUSIP check's policy, with the ISIN-only Security rule switched on too."""
    body = cusip.policy_body()
    rule = next(r for r in body["kinds"]["security"]["rules"] if r["rule_id"] == "nport-isin-security-isin")
    body["kinds"]["security"]["identifiers"]["isin"].setdefault("verification", {
        "corpus_sha256": "0" * 64, "approved_by": "check", "approved_at": core.AS_OF, "reason": "check only"})
    body["automatic_rules"].append({"kind": "security", "family": "binding", "rule_id": rule["rule_id"],
                                    "rule_version": rule["version"], "verdict": "bind", "activation": "deterministic"})
    return body


def prepared_records(root: Path) -> list[dict]:
    store = Artifacts()
    root.mkdir(parents=True, exist_ok=True)
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as z:
        z.writestr("FUND_REPORTED_HOLDING.tsv", "\n".join("\t".join(r) for r in [
            cusip.COLUMNS, *([*h, ""] for h in HOLDINGS), WITH_CUSIP]) + "\n")
    raw = store.put_bytes((root / "capture.zip").as_uri(), body.getvalue())
    holdings = cusip.read(store, root / "holdings", "source.yaml", raw, cusip.Q2, lookups={"isin": PAIRS})
    issuers = cusip.read(store, root / "issuers", "issuers.yaml", raw, None, lookups={"isin": PAIRS})
    securities = cusip.combine(store, root / "reduce", "reduce.yaml", {"holdings": holdings})
    reduced = cusip.combine(store, root / "issuer-reduce", "issuer-reduce.yaml", {"issuers": issuers})
    attached = store.put(root.as_uri(), {"version": 1, "artifacts": [
        {"input": raw, "tables": {"attached": []}, "deferred": []}]})
    combined = cusip.combine(store, root / "combine", "combine.yaml",
                             {"securities": securities, "attached": attached, "issuers": reduced})
    task = {"input": combined, "output": (root / "mdm/manifest.json").as_uri(), "checks": ["mdm.prepared"],
            "keys": {"table": "security_isin", "dataset": CODE, "policy": "0" * 64, "consumer": "check",
                     "batch_id": "check-isin", "as_of": "2026-10-16T00:00:00+00:00", "effective_column": "period"}}
    prepared = mdm_prepare.execute(task, store)
    assert mdm_prepare.verify({**task, "candidate": prepared}, store) == ({"mdm.prepared": True}, [])
    contract = files.source(cusip.NAME)["mdm"][CODE]["contract"]
    out = []
    for b in store.json(prepared)["batches"]:
        for line in (root / "mdm" / b["input"]["path"]).read_bytes().splitlines():
            out.append(adapters.normalize(json.loads(line), source_code=CODE, contract=contract, publication={
                **b["input"]["publication"], "semantics": "patch", "artifact_sha256": b["input"]["sha256"],
                "member": b["input"]["path"], "record_locator": f"{b['input']['sha256']}:{len(out)}"}))
    return out


def test_an_isin_only_security_links_to_its_one_issuer(database, tmp_path):
    records = prepared_records(tmp_path)
    links = {r["provenance"]["record_key"]: [l for l in r.get("relationships") or [] if l["type"] == "ISSUED_BY"] for r in records}
    assert {k: len(v) for k, v in links.items()} == {ONE: 1, TWO: 0, NONE: 0}
    for code in (cusip.ADV, cusip.GLEIF):
        core.register_reading(database, code, core.contract_body())
    with database.admin.begin() as conn:
        register_dataset(conn, CODE, database.registry, files.mdm_contract(cusip.NAME, CODE))
        policy = register_policy(conn, policy_body())
    stage = MergeStage(Store(database.application))
    cusip.apply(stage, policy, "custodian", [core.source(
        key="custodian", source_code=cusip.ADV, fields={"name": "Example Corp"}, identifiers={"lei": LEI})], 1)
    cusip.apply(stage, policy, "gleif", [core.source(
        key=LEI, source_code=cusip.GLEIF, fields={"name": "Example Corp"}, identifiers={"lei": LEI},
        provenance={"matching": {"nport_issuer": True}})], 2)
    cusip.apply(stage, policy, "q2", records, 3)
    with database.application.connect() as conn:
        periods = [json.loads(p) if isinstance(p, str) else p for (p,) in conn.execute(text(
            "SELECT body->'periods' FROM mdm.current_record WHERE object_type='relationship' "
            "AND body->>'type'='ISSUED_BY'")).all()]
    (only,) = periods
    assert [(p["valid_from"], p["valid_from_basis"]) for p in only] == [(cusip.Q2, "observed")]
