"""Person feed 1: the Proving Run of `person-cik` (operator: "Yes", 2026-10-01).

Every SEC submissions document of the pinned capture (all-76230) is read
for the Person kind through the unchanged reading path
(`adapters.normalize` under `sec.submissions.person.v1`'s Dataset Contract
and the repo's merge rules, with `sec-person-candidate` switched on by the
operator) and applied by the Merge Stage on a disposable PostgreSQL 16 (the
Clean MDM test fixtures). The container is removed afterwards; nothing
shared is touched. Zero requests leave the machine.

No Person reader exists yet, so this script stands in for one: each
document is one publication, keyed by its member name and sha256 from
`receipts.jsonl`.

`person-cik` is switched on here as a **Proving Run activation**: its
Identifier Contract's verification is stamped "proving-run", as ticket 05
did for Company's CIK rule. The body the operator is asked to approve
differs only in those three fields. Then everything is applied again; the
second pass must change nothing.

    PROVING_WORK=~/.local/share/edgartools/clean-mdm/proving/person-feed-1 \\
    [PROVING_LIMIT=<n documents, for a small first run>] \\
    [PROVING_SAMPLE=<n documents, a seeded random cohort>] \\
    DOCKER_HOST=unix://$HOME/.colima/default/docker.sock \\
    uv run --no-sync pytest -q -s -p no:randomly \\
        .scratch/onboarding/sec.submissions.person/proving_run.py
"""

from __future__ import annotations

import copy
import json
import os
import random
import re
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
from edgar_warehouse.mdm.clean.store import Store, canonical, digest, register_policy
from edgar_warehouse.rules import files
from tests.integration import test_clean_mdm_postgres as core
from tests.support.rules_authority import register_dataset

postgres = core.postgres
database = core.database

SOURCE = "sec.submissions.person"
SOURCE_CODE = "sec.submissions.person.v1"
CAPTURE = Path.home() / ".local/share/edgartools/clean-mdm/captures/sec.submissions.company/all-76230"
RECEIPTS_SHA256 = "3aee020551b37090e638b4e73d24a0119cc59456548557c883d1c032b6d5c247"
AS_OF = "2026-10-01T14:00:00+00:00"
# `write_batch` caps a request at 16 MiB; a set-aside record carries its
# whole document (up to 4.4 MB), so batches are cut by size as well.
MAX_RECORDS, MAX_BYTES = 1000, 12 * 1024 * 1024
SEED = 20261001
COHORT = Path.home() / ".local/share/edgartools/clean-mdm/proving/cm27/bundles"


def documents() -> list[dict]:
    """Each filer's document, as `receipts.jsonl` lists it, sorted by key."""
    found = []
    for line in (CAPTURE / "receipts.jsonl").open():
        receipt = json.loads(line)
        key = receipt.get("key", "")
        if re.search(r"CIK\d{10}\.json$", key) and "/pagination/" not in key:
            found.append(receipt)
    return sorted(found, key=lambda r: r["key"])


def proving_policy(approval: dict) -> dict:
    """The repo's merge rules with `person-cik` switched on for this run."""
    body = files.policy()
    person = body["kinds"]["person"]
    person["identifiers"]["cik"]["verification"] = {"corpus_sha256": RECEIPTS_SHA256, **approval}
    rule = next(r for r in person["rules"] if r["rule_id"] == "person-cik")
    body["automatic_rules"] = [*body["automatic_rules"], {
        "kind": "person", "family": "binding", "rule_id": rule["rule_id"],
        "rule_version": rule["version"], "verdict": "bind", "activation": "deterministic"}]
    return body


def read(receipt: dict, contract: dict, policy: dict) -> tuple[str, dict]:
    member = receipt["key"].removeprefix("warehouse/bronze/")
    raw = (CAPTURE / "bronze" / member).read_bytes()
    publication = {"publication_key": f"{member}@{receipt['sha256']}", "revision": 1,
                   "artifact_sha256": receipt["sha256"], "member": member, "record_locator": member}
    row = json.loads(raw)
    try:
        return "assertion", normalize(row, source_code=SOURCE_CODE, contract=contract,
                                      publication=publication, policy=policy)
    except UnsupportedRecord as exc:
        return "deferred", deferred_record(
            source_code=SOURCE_CODE, publication_key=publication["publication_key"],
            record_locator=member, schema_version=contract["schema_version"], reason=exc.reason,
            raw_record=row, probable_kind=exc.probable_kind,
            provenance={"artifact_sha256": receipt["sha256"], "member": member,
                        "adapter_version": contract["adapter"]["version"], **exc.detail})


def counts(conn) -> dict:
    one = lambda sql: conn.execute(text(sql)).scalar()
    group = lambda sql: {str(k): v for k, v in conn.execute(text(sql)).all()}
    return {
        "identities": group("SELECT kind, count(*) FROM mdm.master_entity GROUP BY kind"),
        "stage_records": group("SELECT kind, count(*) FROM mdm.stage_record GROUP BY 1"),
        "stage_bound": one("SELECT count(*) FROM mdm.stage_record WHERE entity_id IS NOT NULL"),
        "waiting": group("SELECT coalesce(reason,'(none)')||' / '||coalesce(probable_kind,'-'), count(*) "
                         "FROM mdm.stage_waiting GROUP BY 1"),
        "open_reviews": group("SELECT coalesce(body->>'reason','(none)'), count(*) FROM mdm.current_record "
                              "WHERE object_type='review' AND body->'open'='true'::jsonb GROUP BY 1"),
        "decisions": group("SELECT operation, count(*) FROM mdm.decision GROUP BY 1"),
        "decisions_by_actor": group("SELECT body->>'actor', count(*) FROM mdm.decision GROUP BY 1"),
    }


def people(conn) -> dict[str, set[str]]:
    """Each Person's CIKs, from the records bound to it."""
    out: dict[str, set[str]] = {}
    for entity, cik in conn.execute(text(
        "SELECT s.entity_id::text, s.reading->'identifiers'->>'cik' FROM mdm.stage_record s "
        "JOIN mdm.master_entity m ON m.entity_id = s.entity_id WHERE m.kind = 'person'"
    )):
        out.setdefault(entity, set()).add(cik)
    return out


def population_pass(every: list[dict], policy: dict) -> dict:
    """The classification rule over every document, with no database: how
    many are people, and whether any of them is in Company's cohort."""
    from edgar_warehouse.mdm.clean.classification import fired, resolve_rule

    named = files.mdm_contract(SOURCE, SOURCE_CODE)["adapter"]["classification"]
    rule, doc = resolve_rule(policy, named), policy["kinds"]["person"]
    steps, ciks = Counter(), set()
    for receipt in every:
        member = receipt["key"].removeprefix("warehouse/bronze/")
        row = json.loads((CAPTURE / "bronze" / member).read_bytes())
        verdict, step = fired(rule, row, doc)
        steps[f"{step} ({verdict})"] += 1
        if verdict == "person":
            ciks.add(str(row.get("cik")).zfill(10))
    cohort = company_cohort_ciks()
    return {"filers": len(every), "steps": dict(sorted(steps.items())), "persons": len(ciks),
            "person_ciks_in_company_cohort": sorted(ciks & cohort), "company_cohort_ciks": len(cohort)}


def company_cohort_ciks() -> set[str]:
    """The CIKs of Company mastering ticket 27's cohort: 6,414 Companies and
    586 controls, every one a filer Company's rule read as a company."""
    found = set()
    for bundle in sorted(p for p in COHORT.glob("chunk*") if p.is_dir()):
        for line in (bundle / "records.jsonl").open():
            cik = json.loads(line).get("cik")
            if cik:
                found.add(str(cik).zfill(10))
    return found


def test_proving_run(database):
    work = Path(os.environ["PROVING_WORK"]).expanduser()
    work.mkdir(parents=True, exist_ok=True)
    limit = int(os.environ.get("PROVING_LIMIT", "0")) or None
    assert hashlib_sha256(CAPTURE / "receipts.jsonl") == RECEIPTS_SHA256, "the pinned capture changed"
    approval = {"approved_by": "proving-run",
                "approved_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
                "reason": "Person feed 1 Proving Run only; not an approval"}
    body = proving_policy(approval)
    contract = files.mdm_contract(SOURCE, SOURCE_CODE)
    with database.admin.begin() as conn:
        register_dataset(conn, SOURCE_CODE, database.registry, contract)
        policy = register_policy(conn, copy.deepcopy(body))
    stage = MergeStage(Store(database.application))
    every = documents()
    sample = int(os.environ.get("PROVING_SAMPLE", "0")) or None
    # A seeded random cohort, as Company's CIK proof used one (ticket 05):
    # every new Person costs a growing snapshot (ticket 05b), so the whole
    # population does not fit a Proving Run yet.
    receipts = (sorted(random.Random(SEED).sample(every, sample), key=lambda r: r["key"])
                if sample else every[:limit])
    population = population_pass(every, body)
    timings, read_counts = [], Counter()

    def apply_all(tag: str, checkpoint: int) -> int:
        # Set-aside records and readings go in separate batches: a batch that
        # proposes new Persons is recorded whole as one match proposal, and
        # set-aside records carry their whole document.
        pending = {"assertions": ([], [0]), "deferred": ([], [0])}
        n = 0

        def flush(key: str) -> None:
            nonlocal n, checkpoint
            records, size = pending[key]
            if not records:
                return
            n += 1
            started = time.monotonic()
            stage.apply(batch_id=f"person-{tag}-{n}", run_id=str(uuid4()), policy_digest=policy,
                        consumer="person-proving", expected_checkpoint=checkpoint - 1,
                        checkpoint=checkpoint, as_of=AS_OF, **{key: list(records)})
            timings.append({"batch": f"{tag}-{n}", key: len(records),
                            "seconds": round(time.monotonic() - started, 1)})
            if n % 10 == 0:
                print(json.dumps(timings[-1]), flush=True)
            checkpoint += 1
            records.clear()
            size[0] = 0

        # Every reading first, then every set-aside record. A batch that
        # proposes new Persons hashes a snapshot that scans all readings and
        # open reviews (`match_proposal_snapshot`), and each set-aside record
        # opens a review: interleaved, every batch is slower than the last
        # (finding, 2026-10-01: batch 70 ran over 40 minutes).
        for wanted in ("assertions", "deferred"):
            for receipt in receipts:
                kind, record = read(receipt, contract, body)
                key = "assertions" if kind == "assertion" else "deferred"
                if key != wanted:
                    continue
                if tag == "first":
                    read_counts[kind if kind == "assertion" else f"deferred: {record['reason']}"] += 1
                records, size = pending[key]
                weight = len(canonical(record))
                if len(records) >= MAX_RECORDS or size[0] + weight > MAX_BYTES:
                    flush(key)
                records.append(record)
                size[0] += weight
            flush(wanted)
        return checkpoint

    started = time.monotonic()
    next_checkpoint = apply_all("first", 1)
    first_seconds = round(time.monotonic() - started, 1)
    with database.application.connect() as conn:
        after_first, first_people = counts(conn), people(conn)
    started = time.monotonic()
    apply_all("second", next_checkpoint)
    second_seconds = round(time.monotonic() - started, 1)
    with database.application.connect() as conn:
        after_second, second_people = counts(conn), people(conn)
        review_sample = [r[0] for r in conn.execute(text(
            "SELECT body FROM mdm.current_record WHERE object_type='review' "
            "AND body->'open'='true'::jsonb LIMIT 5"))]

    person_ciks = Counter(c for ciks in first_people.values() for c in ciks)
    cohort = company_cohort_ciks()
    report = {
        "run": "person feed 1, Proving Run of person-cik",
        "policy_digest": policy,
        "receipts_sha256": RECEIPTS_SHA256,
        "documents": len(receipts),
        "cohort": {"sample": sample, "seed": SEED if sample else None, "limit": limit},
        "population": population,
        "read": dict(read_counts),
        "after_first_pass": after_first,
        "after_second_pass": after_second,
        "second_pass_changed_nothing": after_first == after_second and first_people == second_people,
        "persons": len(first_people),
        "cik_on_two_persons": sorted(c for c, k in person_ciks.items() if k > 1),
        "person_with_two_ciks": sum(len(c) > 1 for c in first_people.values()),
        "person_ciks_in_company_cohort": sorted(set(person_ciks) & cohort),
        "company_cohort_ciks": len(cohort),
        "review_sample": review_sample,
        "seconds": {"first_pass": first_seconds, "second_pass": second_seconds},
        "timings": timings,
    }
    name = (f"report-sample-{sample}.json" if sample else
            "report.json" if limit is None else f"report-limit-{limit}.json")
    (work / name).write_text(json.dumps(report, sort_keys=True, indent=1, default=str) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("review_sample", "timings")},
                     indent=1, default=str))
    assert report["second_pass_changed_nothing"]


def hashlib_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
