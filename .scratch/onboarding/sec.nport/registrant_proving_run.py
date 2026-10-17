"""N-PORT registrant as a Company (ticket 79, part 2): the one Proving Run.

The SEC Companies of the cm27 cohort (`sec.submissions.company.v1`, already
switched on) whose CIK an N-PORT registrant also files under go in first; then
the 1,947 prepared registrant records (`sec.nport.registrant.v1`) go through
their Dataset Contract and the repo's merge rules. The Merge Stage applies
them on a disposable PostgreSQL 16 (the MDM test fixtures); the container is
removed afterwards. Zero requests leave the machine.

`nport-registrant-cik` is switched on here as a **Proving Run activation**
only, in a copy of the policy in the disposable database. Then everything is
applied again; the second pass must change nothing. Counts only.

    PREPARED_REGISTRANT=~/edgar-local-tmp/nreg/mdm \\
    PROVING_WORK=~/.local/share/edgartools/clean-mdm/proving/nport-registrant \\
    uv run --no-sync pytest -q -s -p no:randomly .scratch/onboarding/sec.nport/registrant_proving_run.py
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sqlalchemy import text

from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
from edgar_warehouse.mdm.clean.evidence import deferred_record
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, canonical, register_policy
from edgar_warehouse.rules import files
from tests.integration import test_clean_mdm_postgres as core
from tests.support.rules_authority import register_dataset

postgres = core.postgres
database = core.database

AS_OF = "2026-10-15T00:00:00+00:00"
MAX_RECORDS, MAX_BYTES = 1000, 12 * 1024 * 1024
RULE = "nport-registrant-cik"
COMPANY, REGISTRANT = "sec.submissions.company.v1", "sec.nport.registrant.v1"
COHORT = Path.home() / ".local/share/edgartools/clean-mdm/proving/cm27/bundles"

def proving_policy() -> dict:
    """The repo's merge rules with the registrant's matching rule switched on for this run."""
    body = files.policy()
    rule = next(r for r in body["kinds"]["company"]["rules"] if r["rule_id"] == RULE)
    if RULE not in {r["rule_id"] for r in body["automatic_rules"]}:
        body["automatic_rules"].append({
            "kind": "company", "family": "binding", "rule_id": RULE,
            "rule_version": rule["version"], "verdict": "bind", "activation": "deterministic"})
    return body

def read(row, code, contract, policy, publication):
    try:
        return "assertions", normalize(row, source_code=code, contract=contract, publication=publication, policy=policy)
    except UnsupportedRecord as exc:
        return "deferred", deferred_record(
            source_code=code, publication_key=publication["publication_key"],
            record_locator=publication["record_locator"], schema_version=contract["schema_version"],
            reason=exc.reason, raw_record=row, probable_kind=exc.probable_kind,
            provenance={"artifact_sha256": publication["artifact_sha256"], "member": publication["member"],
                        "adapter_version": contract["adapter"]["version"], **exc.detail})

def registrants(prepared: Path):
    """(row, publication) for each prepared registrant record."""
    manifest = json.loads((prepared / "manifest.json").read_bytes())
    for batch in manifest["batches"]:
        data = batch["input"]
        for n, line in enumerate((prepared / data["path"]).read_bytes().splitlines(), 1):
            yield json.loads(line), {**data["publication"], "semantics": "patch", "artifact_sha256": data["sha256"], "member": data["path"],
                                     "record_locator": f"{data['sha256']}:line:{n}"}

def cohort(ciks: set[int]):
    """(row, publication) for each cm27 SEC Company holding one of these CIKs."""
    seen = set()
    for records in sorted(COHORT.glob("chunk*/records.jsonl")):
        for line in records.open():
            row = json.loads(line)
            cik = int(row.get("cik") or 0)
            if cik in ciks and cik not in seen:
                seen.add(cik)
                member = f"cm27/cik={cik}"
                sha = hashlib.sha256(canonical(row).encode()).hexdigest()
                yield row, {"publication_key": f"{member}@{sha}", "revision": 1, "artifact_sha256": sha,
                            "member": member, "record_locator": member}

def counts(conn) -> dict:
    group = lambda sql: {str(k): v for k, v in conn.execute(text(sql)).all()}
    return {
        "identities": group("SELECT kind, count(*) FROM mdm.master_entity GROUP BY kind"),
        "stage_records": group("SELECT source_code, count(*) FROM mdm.stage_record GROUP BY 1"),
        "waiting": group("SELECT coalesce(reason,'(none)'), count(*) FROM mdm.stage_waiting GROUP BY 1"),
        "open_reviews": group("SELECT coalesce(body->>'reason','(none)'), count(*) FROM mdm.current_record "
                              "WHERE object_type='review' AND body->'open'='true'::jsonb GROUP BY 1"),
        "decisions": group("SELECT operation, count(*) FROM mdm.decision GROUP BY 1"),
    }

def companies_by_feeds(conn) -> dict:
    return {str(k): v for k, v in conn.execute(text(
        "SELECT feeds, count(*) FROM (SELECT s.entity_id, string_agg(DISTINCT s.source_code, ' + ' "
        "ORDER BY s.source_code) AS feeds FROM mdm.stage_record s JOIN mdm.master_entity m "
        "ON m.entity_id = s.entity_id WHERE m.kind = 'company' GROUP BY 1) t GROUP BY 1")).all()}

def cik_holders(conn) -> Counter:
    return Counter(value for value, _ in conn.execute(text(
        "SELECT DISTINCT s.reading->'identifiers'->>'cik', s.entity_id FROM mdm.stage_record s "
        "JOIN mdm.master_entity m ON m.entity_id = s.entity_id "
        "WHERE m.kind = 'company' AND s.reading->'identifiers' ? 'cik'")).all())

def test_proving_run(database):
    work = Path(os.environ["PROVING_WORK"]).expanduser()
    work.mkdir(parents=True, exist_ok=True)
    body = proving_policy()
    contracts = {code: files.mdm_contract(source, code) for source, code in (
        ("sec.submissions.company", COMPANY), ("sec.nport.registrant", REGISTRANT))}
    with database.admin.begin() as conn:
        for code, contract in contracts.items():
            register_dataset(conn, code, database.registry, contract)
        policy = register_policy(conn, copy.deepcopy(body))
    stage = MergeStage(Store(database.application))
    prepared = Path(os.environ["PREPARED_REGISTRANT"]).expanduser()
    ciks = {int(row.get("cik") or 0) for row, _ in registrants(prepared)}
    feeds = ((COMPANY, lambda: cohort(ciks)), (REGISTRANT, lambda: registrants(prepared)))
    timings, read_counts = [], Counter()

    def apply_all(tag, checkpoint):
        n = 0
        for code, rows in feeds:
            read_rows = [read(row, code, contracts[code], body, pub) for row, pub in rows()]
            if tag == "first":
                for kind, record in read_rows:
                    read_counts[f"{code} {kind if kind == 'assertions' else 'deferred: ' + record['reason']}"] += 1
            for wanted in ("assertions", "deferred"):
                batch, size = [], 0
                chosen = [record for kind, record in read_rows if kind == wanted]
                for i, record in enumerate(chosen):
                    weight = len(canonical(record))
                    batch.append(record)
                    size += weight
                    if len(batch) >= MAX_RECORDS or size > MAX_BYTES or i == len(chosen) - 1:
                        n += 1
                        begun = time.monotonic()
                        stage.apply(batch_id=f"nreg-{tag}-{n}", run_id=str(uuid4()), policy_digest=policy,
                                    consumer="nport-registrant-proving", expected_checkpoint=checkpoint - 1,
                                    checkpoint=checkpoint, as_of=AS_OF, **{wanted: batch})
                        timings.append(round(time.monotonic() - begun, 1))
                        checkpoint += 1
                        batch, size = [], 0
            print(f"{tag} {code}: applied, {n} batches so far", flush=True)
        return checkpoint

    def snapshot():
        with database.application.connect() as conn:
            return counts(conn), cik_holders(conn), companies_by_feeds(conn)

    begun = time.monotonic()
    nxt = apply_all("first", 1)
    first_seconds = round(time.monotonic() - begun, 1)
    first = snapshot()
    begun = time.monotonic()
    apply_all("second", nxt)
    second_seconds = round(time.monotonic() - begun, 1)
    second = snapshot()

    report = {
        "run": "N-PORT registrant as a Company, Proving Run of sec.nport.registrant.v1",
        "policy_digest": policy,
        "registrant_ciks": len(ciks),
        "read": dict(read_counts),
        "after_first_pass": first[0],
        "after_second_pass": second[0],
        "second_pass_changed_nothing": first == second,
        "companies_by_feeds": first[2],
        "ciks_held": len(first[1]),
        "cik_on_two_companies": sum(1 for c in first[1].values() if c > 1),
        "seconds": {"first_pass": first_seconds, "second_pass": second_seconds},
        "batches": len(timings),
        "slowest_batch_seconds": max(timings, default=0),
    }
    (work / "report.json").write_text(json.dumps(report, sort_keys=True, indent=1, default=str) + "\n")
    print(json.dumps(report, indent=1, default=str))
    assert report["second_pass_changed_nothing"]
    assert report["cik_on_two_companies"] == 0
    assert first[0]["identities"].get("company") == len(ciks)
