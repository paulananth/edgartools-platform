"""Real PG16: an adviser links to its custodians (ticket 75).

The real chain on two invented monthly Form ADV files: the filings and custody
source extracts (each file's month end in their context), combine.yaml,
mdm.prepare (filings and custodians, dated by `published`; custodians one per
file), the two Dataset Contracts, then the Merge Stage with the Form ADV
matching rules switched on in a copy of the policy. A custodian named by its
BD number or by its LEI is linked; one named only by name waits; a custodian
named again in a later month keeps one link, its start at the first month and
its `last_seen` at the later one. Invented values only.
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
from edgar_warehouse.mdm.clean.store import Store, canonical, register_policy
from edgar_warehouse.rules import files
from edgar_warehouse.workers import mdm_prepare, source_combine, source_read
from tests.integration import test_clean_mdm_postgres as core
from tests.support.rules_authority import register_dataset

NAME, FILINGS, CUSTODIANS = "iapd.adv", "iapd.adv.filings.v1", "iapd.adv.custodians.v1"
FOLDER = files.ROOT / "sources" / NAME
CRD, BD, LEI = "999001", "8-99901", "9999000000EXAMPLE016"  # invented; the LEI's check digits are valid
MAY, JUNE = "2026-05-31T00:00:00+00:00", "2026-06-30T00:00:00+00:00"
BASE = ["FilingID", "DateSubmitted", "1A", "1B1", "1D", "1E1", "1P", "1F1-Street 1", "1F1-Street 2",
        "1F1-City", "1F1-State", "1F1-Country", "1F1-Postal"]
CUSTODY = ["Filing ID", "5K(3)(a)", "5K(3)(b)", "5K(3)(c) City", "5K(3)(c) State", "5K(3)(c) Country",
           "5K(3)(d)", "5K(3)(e)", "5K(3)(f)", "5K(3)(g)"]


def filing(filing_id: str) -> list[str]:
    return [filing_id, "05/20/2026 10:00:00 AM", "EXAMPLE ADVISERS LLC", "", "801-99901", CRD, "",
            "1 Example Way", "", "Example City", "NY", "United States", "10001"]


def custody(filing_id: str, name: str, bd: str = "", lei: str = "") -> list[str]:
    return [filing_id, name, "", "Example City", "NY", "United States", "N", bd, lei, "1000"]


MONTHS = {
    # May: one custodian by BD number (named twice: one link), one by LEI, one by name only.
    MAY: ([filing("F1")], [custody("F1", "EXAMPLE CLEARING LLC", bd=BD),
                           custody("F1", "EXAMPLE CLEARING LLC", bd=BD),
                           custody("F1", "EXAMPLE BANK NA", lei=LEI),
                           custody("F1", "EXAMPLE TRUST CO")]),
    # June: the adviser's next filing names the BD custodian again.
    JUNE: ([filing("F2")], [custody("F2", "EXAMPLE CLEARING LLC", bd=BD)]),
}


def csv_text(header: list[str], rows: list[list[str]]) -> str:
    return "\n".join(",".join(f'"{v}"' for v in r) for r in [header, *rows]) + "\n"


def read(store, root: Path, contract_file: str, raw: dict, published: str) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    body = {"source": NAME, "execution": {"profile": "source.read", "workers": 1, "max_artifacts": 1},
            **files.load(FOLDER / contract_file)}
    context = store.put(root.as_uri(), {"version": 1, "input": raw, "values": {"published": published}})
    manifest = store.put(root.as_uri(), {"version": 2, "contract": store.put(root.as_uri(), body),
                                         "artifacts": [{"input": raw, "context": context}]})
    task = {"input": manifest, "output": (root / "reading.json").as_uri(), "checks": ["source.output"]}
    out = source_read.execute(task, store)
    assert source_read.verify({**task, "candidate": out}, store) == ({"source.output": True}, [])
    return out


def prepare(store, root: Path, reading: dict, table: str, code: str, **keys) -> list[dict]:
    task = {"input": reading, "output": (root / "manifest.json").as_uri(), "checks": ["mdm.prepared"],
            "keys": {"table": table, "dataset": code, "policy": "0" * 64, "consumer": "check",
                     "batch_id": f"check-{code}", "as_of": "2026-10-16T00:00:00+00:00",
                     "effective_column": "published", **keys}}
    prepared = mdm_prepare.execute(task, store)
    assert mdm_prepare.verify({**task, "candidate": prepared}, store) == ({"mdm.prepared": True}, [])
    contract = files.source(NAME)["mdm"][code]["contract"]
    out = []
    for b in store.json(prepared)["batches"]:
        for line in (root / b["input"]["path"]).read_bytes().splitlines():
            out.append(adapters.normalize(json.loads(line), source_code=code, contract=contract, publication={
                **b["input"]["publication"], "semantics": "patch", "artifact_sha256": b["input"]["sha256"],
                "member": b["input"]["path"], "record_locator": f"{b['input']['sha256']}:{len(out)}"}))
    return out


def month(root: Path, published: str) -> tuple[list[dict], list[dict]]:
    """One monthly file's custodian and filing assertions, through the real chain."""
    store = Artifacts()
    root.mkdir(parents=True, exist_ok=True)
    tag = published[:7].replace("-", "")
    base, rows = MONTHS[published]
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as z:
        z.writestr(f"IA_ADV_Base_A_{tag}.csv", csv_text(BASE, base))
        z.writestr(f"IA_Schedule_D_5K3_{tag}.csv", csv_text(CUSTODY, rows))
    raw = store.put_bytes((root / "capture.zip").as_uri(), body.getvalue())
    filings = read(store, root / "filings", "adviser-filings-csv.yaml", raw, published)
    custody_rows = read(store, root / "custody", "custody-csv.yaml", raw, published)
    m = store.put(root.as_uri(), {"version": 1, "contract": store.put(root.as_uri(), files.load(FOLDER / "combine.yaml")),
                                  "readings": {"filings": filings, "custody": custody_rows}})
    task = {"input": m, "output": (root / "combine/out.json").as_uri(), "checks": [source_combine.CHECK], "keys": {}}
    combined = source_combine.execute(task, store)
    assert source_combine.verify({**task, "candidate": combined}, store) == ({source_combine.CHECK: True}, [])
    custodians = prepare(store, root / "mdm-custodians", custody_rows, "custody", CUSTODIANS, distinct_on=["custodian_id"])
    advisers = prepare(store, root / "mdm-filings", combined, "filings", FILINGS)
    return custodians, advisers


def policy_body() -> dict:
    body = copy.deepcopy(files.policy())
    company = body["kinds"]["company"]
    for namespace in ("crd", "lei", "bd_number"):
        company["identifiers"][namespace].setdefault("verification", {
            "corpus_sha256": "0" * 64, "approved_by": "check", "approved_at": core.AS_OF, "reason": "check only"})
    for rule_id in ("iapd-adv-crd", "iapd-adv-custodian-lei", "iapd-adv-custodian-bd"):
        rule = next(r for r in company["rules"] if r["rule_id"] == rule_id)
        body["automatic_rules"].append({"kind": "company", "family": "binding", "rule_id": rule_id,
                                        "rule_version": rule["version"], "verdict": "bind",
                                        "activation": "deterministic"})
    return body


def test_an_adviser_links_to_its_custodians_across_months(database, tmp_path):
    may_custodians, may_filings = month(tmp_path / "may", MAY)
    june_custodians, june_filings = month(tmp_path / "june", JUNE)
    (may_filing,) = may_filings
    custodian_subjects = {subject_key(CUSTODIANS, canonical([MAY, f"{p}{v}"])) for p, v in
                          (("bd:", BD), ("lei:", LEI), ("name:", "EXAMPLE TRUST CO"))}
    assert {l["target_subject"] for l in may_filing["relationships"]} == custodian_subjects
    assert {subject_key(CUSTODIANS, r["provenance"]["record_key"]) for r in may_custodians} == custodian_subjects
    assert len(may_custodians) == 3  # the BD custodian's two rows are one record
    with database.admin.begin() as conn:
        for code in (FILINGS, CUSTODIANS):
            register_dataset(conn, code, database.registry, files.mdm_contract(NAME, code))
        policy = register_policy(conn, policy_body())
    stage = MergeStage(Store(database.application))
    for n, (batch, records) in enumerate([("may-custodians", may_custodians), ("may-filings", may_filings),
                                          ("june-custodians", june_custodians), ("june-filings", june_filings)], 1):
        stage.apply(batch_id=batch, run_id=str(uuid4()), policy_digest=policy, consumer="check",
                    expected_checkpoint=n - 1, checkpoint=n, as_of="2026-10-16T00:00:00+00:00",
                    assertions=records)
    with database.application.connect() as conn:
        links = [json.loads(b) if isinstance(b, str) else b for (b,) in conn.execute(text(
            "SELECT body FROM mdm.current_record WHERE object_type='relationship' AND body->>'type'='CUSTODIAN'")).all()]

    named = {body["fields"]["name"]["value"]: entity for entity, body in core.documents(database, "entity").items()}
    assert len(links) == 2  # BD and LEI custodians; the one named only by name waits
    by_target = {l["target_id"]: l for l in links}
    bd_link, lei_link = by_target[named["EXAMPLE CLEARING LLC"]], by_target[named["EXAMPLE BANK NA"]]
    assert {l["source_id"] for l in links} == {named["EXAMPLE ADVISERS LLC"]}
    assert [(p["valid_from"], p["valid_from_basis"]) for p in bd_link["periods"]] == [(MAY, "observed")]
    assert bd_link["last_seen"] == JUNE
    assert [(p["valid_from"], p["valid_from_basis"]) for p in lei_link["periods"]] == [(MAY, "observed")]
    assert lei_link["last_seen"] == MAY
