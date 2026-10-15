"""SEC 13F information tables, the Security Dataset Contract: its Proving Run (ticket 79).

The prepared records of the 999 local 13F information tables (the trial's
`mdm.prepare` output: one record per CUSIP over the data set, read by
`rules/sources/sec.thirteenf.information_table/`) go through
`sec.thirteenf.information_table.security.v1` and the repo's merge rules, and
are applied by the Merge Stage on a disposable PostgreSQL 16 (the MDM test
fixtures); the container is removed afterwards. Zero requests leave the machine.

The Security matching rule `security-cusip` is switched on here as a **Proving
Run activation** only: stamped "proving-run" in a copy of the policy in the
disposable database, with a stand-in verification of the CUSIP Identifier
Contract. Then everything is applied again; the second pass must change
nothing. The report holds counts only.

    PREPARED=~/edgar-local-tmp/t13f/mdm \\
    PROVING_WORK=~/.local/share/edgartools/clean-mdm/proving/thirteenf \\
    DOCKER_HOST=unix://$HOME/.colima/default/docker.sock \\
    uv run --no-sync pytest -q -s -p no:randomly .scratch/onboarding/sec.thirteenf.information_table/proving_run.py
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

SOURCE, CODE = "sec.thirteenf.information_table", "sec.thirteenf.information_table.security.v1"
AS_OF = "2026-10-14T00:00:00+00:00"
MAX_RECORDS, MAX_BYTES = 1000, 12 * 1024 * 1024


def proving_policy(approval: dict) -> dict:
    """The repo's merge rules with the Security matching rule switched on for this run."""
    body = files.policy()
    security = body["kinds"]["security"]
    security["identifiers"]["cusip"].setdefault("verification", {"corpus_sha256": "0" * 64, **approval})
    rule = next(r for r in security["rules"] if r["rule_id"] == "security-cusip")
    body["automatic_rules"] = [*body["automatic_rules"], {
        "kind": "security", "family": "binding", "rule_id": rule["rule_id"],
        "rule_version": rule["version"], "verdict": "bind", "activation": "deterministic"}]
    return body


def read(row: dict, contract: dict, policy: dict, publication: dict) -> tuple[str, dict]:
    try:
        return "assertions", normalize(row, source_code=CODE, contract=contract,
                                       publication=publication, policy=policy)
    except UnsupportedRecord as exc:
        return "deferred", deferred_record(
            source_code=CODE, publication_key=publication["publication_key"],
            record_locator=publication["record_locator"], schema_version=contract["schema_version"],
            reason=exc.reason, raw_record=row, probable_kind=exc.probable_kind,
            provenance={"artifact_sha256": publication["artifact_sha256"], "member": publication["member"],
                        "adapter_version": contract["adapter"]["version"], **exc.detail})


def counts(conn) -> dict:
    group = lambda sql: {str(k): v for k, v in conn.execute(text(sql)).all()}
    return {
        "identities": group("SELECT kind, count(*) FROM mdm.master_entity GROUP BY kind"),
        "stage_records": group("SELECT kind, count(*) FROM mdm.stage_record GROUP BY 1"),
        "waiting": group("SELECT coalesce(reason,'(none)'), count(*) FROM mdm.stage_waiting GROUP BY 1"),
        "open_reviews": group("SELECT coalesce(body->>'reason','(none)'), count(*) FROM mdm.current_record "
                              "WHERE object_type='review' AND body->'open'='true'::jsonb GROUP BY 1"),
        "decisions": group("SELECT operation, count(*) FROM mdm.decision GROUP BY 1"),
        "fields_filled": group("SELECT f.key, count(*) FROM mdm.stage_record s, "
                               "jsonb_each(s.reading->'fields') f WHERE f.value <> 'null'::jsonb GROUP BY 1"),
    }


def cusips(conn) -> Counter:
    """How many Securities hold each CUSIP."""
    return Counter(cusip for cusip, _ in conn.execute(text(
        "SELECT DISTINCT s.reading->'identifiers'->>'cusip', s.entity_id FROM mdm.stage_record s "
        "JOIN mdm.master_entity m ON m.entity_id = s.entity_id WHERE m.kind = 'security'")).all())


def test_proving_run(database):
    prepared = Path(os.environ["PREPARED"]).expanduser()
    work = Path(os.environ["PROVING_WORK"]).expanduser()
    work.mkdir(parents=True, exist_ok=True)
    approval = {"approved_by": "proving-run",
                "approved_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
                "reason": "SEC 13F Security Proving Run only; not an approval"}
    body = proving_policy(approval)
    contract = files.mdm_contract(SOURCE, CODE)
    with database.admin.begin() as conn:
        register_dataset(conn, CODE, database.registry, contract)
        policy = register_policy(conn, copy.deepcopy(body))
    stage = MergeStage(Store(database.application))
    manifest = json.loads((prepared / "manifest.json").read_bytes())
    timings, read_counts = [], Counter()

    def records(tag: str):
        for batch in manifest["batches"]:
            data = batch["input"]
            for n, line in enumerate((prepared / data["path"]).read_bytes().splitlines(), 1):
                publication = {**data["publication"], "artifact_sha256": data["sha256"], "member": data["path"],
                               "record_locator": f"{data['sha256']}:line:{n}"}
                kind, record = read(json.loads(line), contract, body, publication)
                if tag == "first":
                    read_counts[kind if kind == "assertions" else f"deferred: {record['reason']}"] += 1
                yield kind, record

    def apply_all(tag: str, checkpoint: int) -> int:
        n = 0
        for wanted in ("assertions", "deferred"):  # every reading first, then every set-aside record
            batch, size = [], 0

            def flush() -> None:
                nonlocal n, checkpoint, batch, size
                if not batch:
                    return
                n += 1
                begun = time.monotonic()
                stage.apply(batch_id=f"thirteenf-{tag}-{n}", run_id=str(uuid4()), policy_digest=policy,
                            consumer="thirteenf-proving", expected_checkpoint=checkpoint - 1,
                            checkpoint=checkpoint, as_of=AS_OF, **{wanted: list(batch)})
                timings.append({"batch": f"{tag}-{n}", wanted: len(batch),
                                "seconds": round(time.monotonic() - begun, 1)})
                checkpoint += 1
                batch, size = [], 0

            for kind, record in records(tag):
                if kind != wanted:
                    continue
                weight = len(canonical(record))
                if len(batch) >= MAX_RECORDS or size + weight > MAX_BYTES:
                    flush()
                batch.append(record)
                size += weight
            flush()
        return checkpoint

    begun = time.monotonic()
    nxt = apply_all("first", 1)
    first_seconds = round(time.monotonic() - begun, 1)
    with database.application.connect() as conn:
        after_first, first_cusips = counts(conn), cusips(conn)
    begun = time.monotonic()
    apply_all("second", nxt)
    second_seconds = round(time.monotonic() - begun, 1)
    with database.application.connect() as conn:
        after_second, second_cusips = counts(conn), cusips(conn)

    report = {
        "run": "SEC 13F, Proving Run of sec.thirteenf.information_table.security.v1",
        "policy_digest": policy,
        "prepared_batches": len(manifest["batches"]),
        "read": dict(read_counts),
        "after_first_pass": after_first,
        "after_second_pass": after_second,
        "second_pass_changed_nothing": after_first == after_second and first_cusips == second_cusips,
        "securities_by_cusip": len(first_cusips),
        "cusip_on_two_securities": sum(1 for c in first_cusips.values() if c > 1),
        "seconds": {"first_pass": first_seconds, "second_pass": second_seconds},
        "batches": len(timings),
        "slowest_batch_seconds": max((t["seconds"] for t in timings), default=0),
    }
    (work / "report.json").write_text(json.dumps(report, sort_keys=True, indent=1, default=str) + "\n")
    print(json.dumps(report, indent=1, default=str))
    assert report["second_pass_changed_nothing"]
    assert report["cusip_on_two_securities"] == 0
