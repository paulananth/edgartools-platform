"""N-PORT Security (ticket 79, part 1, with OpenFIGI, ticket 80): the one Proving Run.

The prepared records of SEC 13F (`sec.thirteenf.information_table.security.v1`,
already switched on) and of N-PORT 2026q2 (`sec.nport.security.v1` by CUSIP,
`sec.nport.security_isin.v1` by ISIN) go through their Dataset Contracts and the
repo's merge rules, and the Merge Stage applies them, in that order, on a
disposable PostgreSQL 16 (the MDM test fixtures); the container is removed
afterwards. Zero requests leave the machine.

The three N-PORT matching rules are switched on here as a **Proving Run
activation** only, in a copy of the policy in the disposable database, with a
stand-in verification of the ISIN Identifier Contract. Then everything is
applied again; the second pass must change nothing. Counts only.

    PREPARED_13F=~/edgar-local-tmp/t13f/mdm \\
    PREPARED_NPORT=~/edgar-local-tmp/figi-attach \\
    PROVING_WORK=~/.local/share/edgartools/clean-mdm/proving/nport \\
    uv run --no-sync pytest -q -s -p no:randomly .scratch/onboarding/sec.nport/proving_run.py
"""

from __future__ import annotations

import copy
import json
import os
import sys
import time
from collections import Counter
from datetime import UTC, datetime
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
NPORT_RULES = ("nport-security-cusip", "nport-security-isin", "nport-isin-security-isin")
# (source folder, source code, prepared folder under its environment variable)
FEEDS = (("sec.thirteenf.information_table", "sec.thirteenf.information_table.security.v1", "PREPARED_13F", "."),
         ("sec.nport.security", "sec.nport.security.v1", "PREPARED_NPORT", "mdm-security"),
         ("sec.nport.security", "sec.nport.security_isin.v1", "PREPARED_NPORT", "mdm-security_isin"))

def proving_policy(approval: dict) -> dict:
    """The repo's merge rules with N-PORT's three matching rules switched on for this run."""
    body = files.policy()
    security = body["kinds"]["security"]
    security["identifiers"]["isin"].setdefault("verification", {"corpus_sha256": "0" * 64, **approval})
    active = {r["rule_id"] for r in body["automatic_rules"]}
    for rule in security["rules"]:
        if rule["rule_id"] in NPORT_RULES and rule["rule_id"] not in active:
            body["automatic_rules"].append({
                "kind": "security", "family": "binding", "rule_id": rule["rule_id"],
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

def counts(conn) -> dict:
    group = lambda sql: {str(k): v for k, v in conn.execute(text(sql)).all()}
    return {
        "identities": group("SELECT kind, count(*) FROM mdm.master_entity GROUP BY kind"),
        "stage_records": group("SELECT source_code, count(*) FROM mdm.stage_record GROUP BY 1"),
        "waiting": group("SELECT coalesce(reason,'(none)'), count(*) FROM mdm.stage_waiting GROUP BY 1"),
        "open_reviews": group("SELECT coalesce(body->>'reason','(none)'), count(*) FROM mdm.current_record "
                              "WHERE object_type='review' AND body->'open'='true'::jsonb GROUP BY 1"),
        "decisions": group("SELECT operation, count(*) FROM mdm.decision GROUP BY 1"),
        "fields_filled": group("SELECT f.key, count(*) FROM mdm.stage_record s, "
                               "jsonb_each(s.reading->'fields') f WHERE f.value <> 'null'::jsonb GROUP BY 1"),
    }

def holders(conn, namespace: str) -> Counter:
    """How many Securities hold each identifier of a namespace."""
    return Counter(value for value, _ in conn.execute(text(
        "SELECT DISTINCT s.reading->'identifiers'->>:ns, s.entity_id FROM mdm.stage_record s "
        "JOIN mdm.master_entity m ON m.entity_id = s.entity_id "
        "WHERE m.kind = 'security' AND s.reading->'identifiers' ? :ns"), {"ns": namespace}).all())

def sources_per_security(conn) -> dict:
    return {str(k): v for k, v in conn.execute(text(
        "SELECT feeds, count(*) FROM (SELECT s.entity_id, string_agg(DISTINCT s.source_code, ' + ' "
        "ORDER BY s.source_code) AS feeds FROM mdm.stage_record s JOIN mdm.master_entity m "
        "ON m.entity_id = s.entity_id WHERE m.kind = 'security' GROUP BY 1) t GROUP BY 1")).all()}

def test_proving_run(database):
    work = Path(os.environ["PROVING_WORK"]).expanduser()
    work.mkdir(parents=True, exist_ok=True)
    approval = {"approved_by": "proving-run", "approved_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
                "reason": "N-PORT Security Proving Run only; not an approval"}
    body = proving_policy(approval)
    contracts = {code: files.mdm_contract(source, code) for source, code, _, _ in FEEDS}
    with database.admin.begin() as conn:
        for code, contract in contracts.items():
            register_dataset(conn, code, database.registry, contract)
        policy = register_policy(conn, copy.deepcopy(body))
    stage = MergeStage(Store(database.application))
    timings, read_counts = [], Counter()

    def records(tag, code, prepared):
        manifest = json.loads((prepared / "manifest.json").read_bytes())
        for batch in manifest["batches"]:
            data = batch["input"]
            for n, line in enumerate((prepared / data["path"]).read_bytes().splitlines(), 1):
                publication = {**data["publication"], "artifact_sha256": data["sha256"], "member": data["path"],
                               "record_locator": f"{data['sha256']}:line:{n}"}
                kind, record = read(json.loads(line), code, contracts[code], body, publication)
                if tag == "first":
                    read_counts[f"{code} {kind if kind == 'assertions' else 'deferred: ' + record['reason']}"] += 1
                yield kind, record

    def apply_all(tag, checkpoint):
        n = 0
        for _, code, env, folder in FEEDS:
            prepared = Path(os.environ[env]).expanduser() / folder
            for wanted in ("assertions", "deferred"):
                batch, size = [], 0

                def flush():
                    nonlocal n, checkpoint, batch, size
                    if not batch:
                        return
                    n += 1
                    begun = time.monotonic()
                    stage.apply(batch_id=f"nport-{tag}-{n}", run_id=str(uuid4()), policy_digest=policy,
                                consumer="nport-proving", expected_checkpoint=checkpoint - 1,
                                checkpoint=checkpoint, as_of=AS_OF, **{wanted: list(batch)})
                    timings.append(round(time.monotonic() - begun, 1))
                    checkpoint += 1
                    batch, size = [], 0

                for kind, record in records(tag, code, prepared):
                    if kind != wanted:
                        continue
                    weight = len(canonical(record))
                    if len(batch) >= MAX_RECORDS or size + weight > MAX_BYTES:
                        flush()
                    batch.append(record)
                    size += weight
                flush()
            print(f"{tag} {code}: applied, {n} batches so far", flush=True)
        return checkpoint

    def snapshot():
        with database.application.connect() as conn:
            return counts(conn), holders(conn, "cusip"), holders(conn, "isin"), sources_per_security(conn)

    begun = time.monotonic()
    nxt = apply_all("first", 1)
    first_seconds = round(time.monotonic() - begun, 1)
    first = snapshot()
    begun = time.monotonic()
    apply_all("second", nxt)
    second_seconds = round(time.monotonic() - begun, 1)
    second = snapshot()

    report = {
        "run": "N-PORT Security with OpenFIGI, Proving Run of sec.nport.security.v1 and sec.nport.security_isin.v1",
        "policy_digest": policy,
        "read": dict(read_counts),
        "after_first_pass": first[0],
        "after_second_pass": second[0],
        "second_pass_changed_nothing": first == second,
        "securities_by_feeds": first[3],
        "cusips_held": len(first[1]),
        "cusip_on_two_securities": sum(1 for c in first[1].values() if c > 1),
        "isins_held": len(first[2]),
        "isin_on_two_securities": sum(1 for c in first[2].values() if c > 1),
        "seconds": {"first_pass": first_seconds, "second_pass": second_seconds},
        "batches": len(timings),
        "slowest_batch_seconds": max(timings, default=0),
    }
    (work / "report.json").write_text(json.dumps(report, sort_keys=True, indent=1, default=str) + "\n")
    print(json.dumps(report, indent=1, default=str))
    assert report["second_pass_changed_nothing"]
    assert report["cusip_on_two_securities"] == 0
    assert report["isin_on_two_securities"] == 0
