"""N-PORT Fund (ticket 79, part 3): the one Proving Run.

The 12,944 prepared Fund records (`sec.nport.fund.v1`, one per fund series)
go through their Dataset Contract and the repo's merge rules, and the Merge
Stage applies them on a disposable PostgreSQL 16 (the MDM test fixtures); the
container is removed afterwards. Zero requests leave the machine.

`nport-fund-series` and `nport-fund-lei` are switched on here as a **Proving
Run activation** only, in a copy of the policy in the disposable database,
with stand-in verifications of the series id and LEI Identifier Contracts.
Then everything is applied again; the second pass must change nothing.
Counts only.

    PREPARED_FUND=~/edgar-local-tmp/nfund/mdm \\
    PROVING_WORK=~/.local/share/edgartools/clean-mdm/proving/nport-fund \\
    DOCKER_HOST=unix://$HOME/.colima/default/docker.sock \\
    uv run --no-sync pytest -q -s -p no:randomly .scratch/onboarding/sec.nport/fund_proving_run.py
"""

from __future__ import annotations

import copy
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

AS_OF = "2026-10-16T00:00:00+00:00"
MAX_RECORDS, MAX_BYTES = 1000, 12 * 1024 * 1024
RULES = ("nport-fund-series", "nport-fund-lei")
FUND = "sec.nport.fund.v1"


def proving_policy(approval: dict) -> dict:
    """The repo's merge rules with the Fund's two matching rules switched on for this run."""
    body = files.policy()
    fund = body["kinds"]["fund_structure"]
    for namespace in ("sec_series_id", "lei"):
        fund["identifiers"][namespace].setdefault("verification", {"corpus_sha256": "0" * 64, **approval})
    active = {r["rule_id"] for r in body["automatic_rules"]}
    for rule in fund["rules"]:
        if rule["rule_id"] in RULES and rule["rule_id"] not in active:
            body["automatic_rules"].append({
                "kind": "fund_structure", "family": "binding", "rule_id": rule["rule_id"],
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
    """(row, publication) for each prepared Fund record."""
    manifest = json.loads((prepared / "manifest.json").read_bytes())
    for batch in manifest["batches"]:
        data = batch["input"]
        for n, line in enumerate((prepared / data["path"]).read_bytes().splitlines(), 1):
            yield json.loads(line), {**data["publication"], "semantics": "patch", "artifact_sha256": data["sha256"], "member": data["path"],
                                     "record_locator": f"{data['sha256']}:line:{n}"}


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


def funds_by_feeds(conn) -> dict:
    return {str(k): v for k, v in conn.execute(text(
        "SELECT feeds, count(*) FROM (SELECT s.entity_id, string_agg(DISTINCT s.source_code, ' + ' "
        "ORDER BY s.source_code) AS feeds FROM mdm.stage_record s JOIN mdm.master_entity m "
        "ON m.entity_id = s.entity_id WHERE m.kind = 'fund_structure' GROUP BY 1) t GROUP BY 1")).all()}


def holders(conn, namespace: str) -> Counter:
    """How many Funds hold each identifier of a namespace."""
    return Counter(value for value, _ in conn.execute(text(
        "SELECT DISTINCT s.reading->'identifiers'->>:ns, s.entity_id FROM mdm.stage_record s "
        "JOIN mdm.master_entity m ON m.entity_id = s.entity_id "
        "WHERE m.kind = 'fund_structure' AND s.reading->'identifiers' ? :ns"), {"ns": namespace}).all())


def test_proving_run(database):
    work = Path(os.environ["PROVING_WORK"]).expanduser()
    work.mkdir(parents=True, exist_ok=True)
    approval = {"approved_by": "proving-run", "approved_at": "2026-10-16T00:00:00+00:00",
                "reason": "N-PORT Fund Proving Run only; not an approval"}
    body = proving_policy(approval)
    contract = files.mdm_contract("sec.nport.fund", FUND)
    with database.admin.begin() as conn:
        register_dataset(conn, FUND, database.registry, contract)
        policy = register_policy(conn, copy.deepcopy(body))
    stage = MergeStage(Store(database.application))
    prepared = Path(os.environ["PREPARED_FUND"]).expanduser()
    timings, read_counts = [], Counter()

    def apply_all(tag, checkpoint):
        n = 0
        read_rows = [read(row, FUND, contract, body, pub) for row, pub in registrants(prepared)]
        if tag == "first":
            for kind, record in read_rows:
                read_counts[kind if kind == "assertions" else "deferred: " + record["reason"]] += 1
        for wanted in ("assertions", "deferred"):
            batch, size = [], 0
            chosen = [record for kind, record in read_rows if kind == wanted]
            for i, record in enumerate(chosen):
                batch.append(record)
                size += len(canonical(record))
                if len(batch) >= MAX_RECORDS or size > MAX_BYTES or i == len(chosen) - 1:
                    n += 1
                    begun = time.monotonic()
                    stage.apply(batch_id=f"nfund-{tag}-{n}", run_id=str(uuid4()), policy_digest=policy,
                                consumer="nport-fund-proving", expected_checkpoint=checkpoint - 1,
                                checkpoint=checkpoint, as_of=AS_OF, **{wanted: batch})
                    timings.append(round(time.monotonic() - begun, 1))
                    checkpoint += 1
                    batch, size = [], 0
        print(f"{tag}: applied, {n} batches", flush=True)
        return checkpoint

    def snapshot():
        with database.application.connect() as conn:
            return counts(conn), holders(conn, "sec_series_id"), holders(conn, "lei"), funds_by_feeds(conn)

    begun = time.monotonic()
    nxt = apply_all("first", 1)
    first_seconds = round(time.monotonic() - begun, 1)
    first = snapshot()
    begun = time.monotonic()
    apply_all("second", nxt)
    second_seconds = round(time.monotonic() - begun, 1)
    second = snapshot()

    report = {
        "run": "N-PORT Fund, Proving Run of sec.nport.fund.v1",
        "policy_digest": policy,
        "read": dict(read_counts),
        "after_first_pass": first[0],
        "after_second_pass": second[0],
        "second_pass_changed_nothing": first == second,
        "funds_by_feeds": first[3],
        "series_ids_held": len(first[1]),
        "series_id_on_two_funds": sum(1 for c in first[1].values() if c > 1),
        "leis_held": len(first[2]),
        "lei_on_two_funds": sum(1 for c in first[2].values() if c > 1),
        "seconds": {"first_pass": first_seconds, "second_pass": second_seconds},
        "batches": len(timings),
        "slowest_batch_seconds": max(timings, default=0),
    }
    (work / "report.json").write_text(json.dumps(report, sort_keys=True, indent=1, default=str) + "\n")
    print(json.dumps(report, indent=1, default=str))
    assert report["second_pass_changed_nothing"]
    assert report["series_id_on_two_funds"] == 0
    assert report["lei_on_two_funds"] == 0
