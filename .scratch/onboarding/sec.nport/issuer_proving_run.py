"""ISSUED_BY by the issuer's LEI (ticket 22): the one Proving Run.

The GLEIF Level 1 records of the N-PORT issuers (`gleif.level1.v1`, the
28,397 LEIs the holdings name that GLEIF holds, extracted from the Golden Copy
already on this machine) go in first; then the prepared N-PORT CUSIP
Securities (`sec.nport.security.v1`, from the ticket's test run), each with
its ISSUED_BY link to the GLEIF record of its issuer's one LEI. The Merge Stage
applies them on a disposable PostgreSQL 16 (the MDM test fixtures), removed
afterwards. Zero requests leave the machine.

Part 1's three N-PORT Security matching rules and the ISIN verification are
switched on here as a **Proving Run activation** only, in a copy of the policy
in the disposable database (as part 1's Proving Run). Then everything is
applied again; the second pass must change nothing. Counts only.

    PG16_SERVER=pgserver GLEIF_ISSUERS=~/edgar-local-tmp/nissuer/gleif-issuers.jsonl \\
    PREPARED_NPORT=~/edgar-local-tmp/nissuer/mdm-security \\
    PROVING_WORK=~/.local/share/edgartools/clean-mdm/proving/nport-issuer \\
    python -m pytest -q -s -p no:randomly -p no:cacheprovider .scratch/onboarding/sec.nport/issuer_proving_run.py
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

AS_OF = "2026-10-16T00:00:00+00:00"
MAX_RECORDS, MAX_BYTES = 1000, 12 * 1024 * 1024
NPORT_RULES = ("nport-security-cusip", "nport-security-isin", "nport-isin-security-isin")
GLEIF, NPORT = "gleif.level1.v1", "sec.nport.security.v1"
APPROVAL = {"approved_by": "proving run", "approved_at": AS_OF, "reason": "Proving Run activation only"}


def proving_policy() -> dict:
    """The repo's merge rules with N-PORT's three matching rules switched on for this run."""
    body = files.policy()
    security = body["kinds"]["security"]
    security["identifiers"]["isin"].setdefault("verification", {"corpus_sha256": "0" * 64, **APPROVAL})
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


def gleif(path: Path):
    """(row, publication) for each extracted GLEIF record: [ordinal in the Golden Copy, record]."""
    for line in path.open():
        ordinal, row = json.loads(line)
        member = f"gleif-golden-copy/record={ordinal}"
        sha = hashlib.sha256(canonical(row).encode()).hexdigest()
        yield row, {"publication_key": f"{member}@{sha}", "revision": 1, "semantics": "patch",
                    "artifact_sha256": sha, "member": member, "record_locator": member}


def securities(prepared: Path):
    """(row, publication) for each prepared N-PORT CUSIP Security."""
    manifest = json.loads((prepared / "manifest.json").read_bytes())
    for batch in manifest["batches"]:
        data = batch["input"]
        for n, line in enumerate((prepared / data["path"]).read_bytes().splitlines(), 1):
            yield json.loads(line), {**data["publication"], "semantics": "patch", "artifact_sha256": data["sha256"],
                                     "member": data["path"], "record_locator": f"{data['sha256']}:line:{n}"}


def counts(conn) -> dict:
    group = lambda sql: {str(k): v for k, v in conn.execute(text(sql)).all()}
    return {
        "identities": group("SELECT kind, count(*) FROM mdm.master_entity GROUP BY kind"),
        "stage_records": group("SELECT source_code, count(*) FROM mdm.stage_record GROUP BY 1"),
        "waiting": group("SELECT coalesce(reason,'(none)'), count(*) FROM mdm.stage_waiting GROUP BY 1"),
        "open_reviews": group("SELECT coalesce(body->>'reason','(none)'), count(*) FROM mdm.current_record "
                              "WHERE object_type='review' AND body->'open'='true'::jsonb GROUP BY 1"),
        "decisions": group("SELECT operation, count(*) FROM mdm.decision GROUP BY 1"),
        "relationships": group("SELECT type || ' ' || coalesce(from_kind,'?') || ' -> ' || coalesce(to_kind,'?'), "
                               "count(DISTINCT relationship_id) FROM mdm.relationship_context GROUP BY 1"),
    }


def issued_by(conn) -> dict:
    """Links per Security, and Securities per issuer."""
    per_security = Counter(n for (n,) in conn.execute(text(
        "SELECT count(DISTINCT to_entity_id) FROM mdm.relationship_context WHERE type = 'ISSUED_BY' "
        "GROUP BY from_entity_id")).all())
    per_issuer = Counter(n for (n,) in conn.execute(text(
        "SELECT count(DISTINCT from_entity_id) FROM mdm.relationship_context WHERE type = 'ISSUED_BY' "
        "GROUP BY to_entity_id")).all())
    buckets = Counter("1" if n == 1 else "2-9" if n < 10 else "10-99" if n < 100 else "100+"
                      for n in per_issuer.elements())
    return {"links_per_security": dict(per_security), "issuers": sum(per_issuer.values()),
            "securities_per_issuer": dict(buckets)}


def lei_holders(conn) -> Counter:
    return Counter(value for value, _ in conn.execute(text(
        "SELECT DISTINCT s.reading->'identifiers'->>'lei', s.entity_id FROM mdm.stage_record s "
        "JOIN mdm.master_entity m ON m.entity_id = s.entity_id "
        "WHERE s.reading->'identifiers' ? 'lei'")).all())


def test_proving_run(database):
    work = Path(os.environ["PROVING_WORK"]).expanduser()
    work.mkdir(parents=True, exist_ok=True)
    body = proving_policy()
    contracts = {GLEIF: files.mdm_contract("gleif", GLEIF), NPORT: files.mdm_contract("sec.nport.security", NPORT)}
    with database.admin.begin() as conn:
        for code, contract in contracts.items():
            register_dataset(conn, code, database.registry, contract)
        policy = register_policy(conn, copy.deepcopy(body))
    stage = MergeStage(Store(database.application))
    issuers = Path(os.environ["GLEIF_ISSUERS"]).expanduser()
    prepared = Path(os.environ["PREPARED_NPORT"]).expanduser()
    feeds = ((GLEIF, lambda: gleif(issuers)), (NPORT, lambda: securities(prepared)))
    timings, read_counts, gleif_kinds = [], Counter(), Counter()

    def apply_all(tag, checkpoint):
        n = 0
        for code, rows in feeds:
            read_rows = [read(row, code, contracts[code], body, pub) for row, pub in rows()]
            if tag == "first":
                for kind, record in read_rows:
                    read_counts[f"{code} {kind if kind == 'assertions' else 'deferred: ' + record['reason']}"] += 1
                    if code == GLEIF and kind == "assertions":
                        gleif_kinds[record.get("kind") or "?"] += 1
            for wanted in ("assertions", "deferred"):
                batch, size = [], 0
                chosen = [record for kind, record in read_rows if kind == wanted]
                for i, record in enumerate(chosen):
                    batch.append(record)
                    size += len(canonical(record))
                    if len(batch) >= MAX_RECORDS or size > MAX_BYTES or i == len(chosen) - 1:
                        n += 1
                        begun = time.monotonic()
                        stage.apply(batch_id=f"nissuer-{tag}-{n}", run_id=str(uuid4()), policy_digest=policy,
                                    consumer="nport-issuer-proving", expected_checkpoint=checkpoint - 1,
                                    checkpoint=checkpoint, as_of=AS_OF, **{wanted: batch})
                        timings.append(round(time.monotonic() - begun, 1))
                        checkpoint += 1
                        batch, size = [], 0
                        if n % 50 == 0:
                            print(f"{tag} {code}: {n} batches", flush=True)
            print(f"{tag} {code}: applied, {n} batches so far", flush=True)
        return checkpoint

    def snapshot():
        with database.application.connect() as conn:
            return counts(conn), issued_by(conn), lei_holders(conn)

    begun = time.monotonic()
    nxt = apply_all("first", 1)
    first_seconds = round(time.monotonic() - begun, 1)
    first = snapshot()
    begun = time.monotonic()
    apply_all("second", nxt)
    second_seconds = round(time.monotonic() - begun, 1)
    second = snapshot()

    report = {
        "run": "ISSUED_BY by issuer LEI, Proving Run of sec.nport.security.v1 with gleif.level1.v1",
        "policy_digest": policy,
        "read": dict(read_counts),
        "gleif_kinds_read": dict(gleif_kinds),
        "after_first_pass": first[0],
        "after_second_pass": second[0],
        "issued_by": first[1],
        "second_pass_changed_nothing": first == second,
        "lei_on_two_entities": sum(1 for c in first[2].values() if c > 1),
        "seconds": {"first_pass": first_seconds, "second_pass": second_seconds},
        "batches": len(timings),
        "slowest_batch_seconds": max(timings, default=0),
    }
    (work / "report.json").write_text(json.dumps(report, sort_keys=True, indent=1, default=str) + "\n")
    print(json.dumps(report, indent=1, default=str))
    assert report["second_pass_changed_nothing"]
    assert report["lei_on_two_entities"] == 0
    assert set(first[1]["links_per_security"]) <= {1}
