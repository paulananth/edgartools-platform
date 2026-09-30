"""Ticket 27: the Proving Run of the Company policy with both name rules on.

The production Company policy (`company_source.POLICY`, with the operator's
approvals of the CIK rule and both name rules) is applied on a disposable
PostgreSQL 16 (the Clean MDM test fixtures) to:

- SEC: the seven bundles `mdm prepare-clean-company` built for ticket 05's
  cohort (6,414 Companies and 586 controls), from one Name Census that
  counted every SEC filer in the pinned bronze copy (76,230, 77 captures)
  and the full GLEIF Golden Copy of 2026-09-11 16:00;
- GLEIF: every Level 1 record of that Golden Copy whose LEI the census
  names for a cohort record's name, read by `gleif_source.record_evidence`
  under the repo's GLEIF contract and applied through `MergeStage.apply`.
  This is not the native consumer, which needs an acquisition publication
  proof from the Change Journal.

The datasets are registered with the test Rules authority
(`tests.support.rules_authority`), not an approved Rules Database version:
the readings are the repo's (ticket 18's), not yet approved there. Each
manifest's run and attempts are recorded in MDM by the run coordinator
(`mdm_v2.run` since platform validation slice 2a).

Then everything is applied again; the second pass must change nothing.

    PROVING_WORK=~/.local/share/edgartools/clean-mdm/proving/cm27 \\
    DOCKER_HOST=unix://$HOME/.colima/default/docker.sock \\
    uv run --no-sync pytest -q -s -p no:randomly \\
        .scratch/company-mastering/research/27_proving_run.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sqlalchemy import text

from edgar_warehouse.mdm.clean.bookkeeping import RunCoordinator
from edgar_warehouse.mdm.clean.cli import execute_manifest
from edgar_warehouse.mdm.clean.company_source import CONTRACT, POLICY, SOURCE_CODE
from edgar_warehouse.mdm.clean.gleif_source import dataset_contract, inspect_archive, record_evidence
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, digest, register_policy
from tests.integration import test_clean_mdm_postgres as core
from tests.support.rules_authority import register_dataset

postgres = core.postgres
database = core.database

GLEIF = "gleif.level1.v1"
POLICY_DIGEST = "75bd2b67"  # the approved Company policy with both name rules on (ticket 25)
GLEIF_DIR = Path.home() / ".local/share/edgartools/clean-mdm/research/gleif-20260911-1600"
ARCHIVE = GLEIF_DIR / "01-20260911-1600-gleif-goldencopy-lei2-golden-copy.json.zip"
ARCHIVE_SHA256 = "1b6cd9cda3f94269fd406ee481842ea042b699e95eb5b8124b1496d4fda36a6a"
AS_OF = "2026-09-29T15:00:00+00:00"
# A batch request is capped at 16 MiB (`commit_batch_core`); each GLEIF
# assertion carries its native record, so 1,000 of them came to 43 MB.
GLEIF_BATCH = 200
NAMED = {"0000320193": "Apple", "0000789019": "Microsoft", "0001306965": "Shell", "0000937966": "ASML"}


def cohort_leis(bundles: list[Path]) -> set[str]:
    """Every LEI the census names for a cohort record's name."""
    found = set()
    for bundle in bundles:
        for line in (bundle / "records.jsonl").open():
            record = json.loads(line)
            entry = (record.get("provenance", {}).get("matching", {}).get("name_census")
                     or record.get("name_census") or {})
            found.update(pair[0] for pair in entry.get("leis", []))
    return found


def gleif_rows(leis: set[str], metadata: dict) -> list[tuple[int, dict]]:
    rows = []

    def keep(row: dict, ordinal: int) -> None:
        if (row.get("LEI") or {}).get("$") in leis:
            rows.append((ordinal, row))

    inspect_archive(ARCHIVE.open("rb"), member="level1", metadata=metadata,
                    expected_sha256=ARCHIVE_SHA256, on_record=keep)
    return rows


def counts(conn) -> dict:
    one = lambda sql: conn.execute(text(sql)).scalar()
    group = lambda sql: {str(k): v for k, v in conn.execute(text(sql)).all()}
    return {
        "identities": group("SELECT kind, count(*) FROM mdm_v2.identity GROUP BY kind"),
        "companies_open": one("SELECT count(*) FROM mdm_v2.current_entity WHERE kind='company' AND status<>'alias'"),
        "stage_records": group("SELECT source_code||':'||kind, count(*) FROM mdm_v2.stage_record GROUP BY 1"),
        "stage_bound": group("SELECT source_code, count(*) FROM mdm_v2.stage_record WHERE entity_id IS NOT NULL GROUP BY 1"),
        "waiting": group("SELECT source_code||':'||coalesce(reason,'(none)'), count(*) FROM mdm_v2.stage_waiting GROUP BY 1"),
        "open_reviews": group("SELECT coalesce(body->>'reason','(none)'), count(*) FROM mdm_v2.projection "
                              "WHERE object_type='review' AND body->'open'='true'::jsonb GROUP BY 1"),
        "decisions": group("SELECT operation, count(*) FROM mdm_v2.decision GROUP BY 1"),
        "decisions_by_rule": group("SELECT coalesce(body->>'rule_id', body->'rule'->>'rule_id', '(none)'), count(*) "
                                   "FROM mdm_v2.decision GROUP BY 1"),
    }


def masters(conn) -> dict:
    """Each open Company's CIKs and LEIs, from the records bound to it."""
    out: dict[str, dict] = {}
    for entity, source, cik, lei in conn.execute(text(
        "SELECT entity_id::text, source_code, reading->'identifiers'->>'cik', reading->'identifiers'->>'lei' "
        "FROM mdm_v2.stage_record WHERE entity_id IS NOT NULL"
    )):
        m = out.setdefault(entity, {"ciks": set(), "leis": set()})
        if cik:
            m["ciks"].add(cik)
        if lei:
            m["leis"].add(lei)
    return out


def test_proving_run(database, tmp_path):
    work = Path(os.environ["PROVING_WORK"]).expanduser()
    out = work / "report.json"
    assert digest(POLICY).startswith(POLICY_DIGEST), "the approved Company policy changed"
    with database.admin.begin() as conn:
        register_dataset(conn, SOURCE_CODE, database.registry, CONTRACT)
        register_dataset(conn, GLEIF, database.registry, dataset_contract("level1"))
        policy = register_policy(conn, POLICY)
    store = Store(database.application)
    coordinator = RunCoordinator(store)
    stage = MergeStage(store)

    bundles = [work / "bundles" / f"chunk{n}" for n in range(1, 8)]
    timings = []

    def apply_sec() -> None:
        for bundle in bundles:
            started = time.monotonic()
            result = execute_manifest(store, coordinator, path=str(bundle / "manifest.json"),
                                      run_id=str(uuid4()), stage="mastering", limit=1000)
            timings.append({"sec": bundle.name, "seconds": round(time.monotonic() - started, 1),
                            "records": result.get("records_processed")})
            print(json.dumps(timings[-1]), flush=True)

    apply_sec()
    leis = cohort_leis(bundles)
    started = time.monotonic()
    metadata = json.loads((work / "gleif-metadata.json").read_text())
    # The matched records, cached by the LEI set they were read for, so a
    # rerun skips the 10-minute pass over the Golden Copy.
    cache = work / f"gleif-rows-{digest(sorted(leis))[:16]}.jsonl"
    if cache.exists():
        rows = [tuple(json.loads(line)) for line in cache.open()]
    else:
        rows = gleif_rows(leis, metadata)
        cache.write_text("".join(json.dumps([o, r]) + "\n" for o, r in rows))
    timings.append({"gleif_read": len(rows), "seconds": round(time.monotonic() - started, 1)})
    print(json.dumps(timings[-1]), flush=True)
    publication = {"publication_key": "gleif-golden-copy-20260911-1600", "revision": 1,
                   "artifact_sha256": ARCHIVE_SHA256, "member": "level1"}
    assertions, deferred = [], Counter()
    contract = dataset_contract("level1")
    for ordinal, row in rows:
        kind, result = record_evidence(row, member="level1", contract=contract, source_code=GLEIF,
                                       eligible_leis=leis, publication=publication, ordinal=ordinal)
        if kind == "assertion":
            assertions.append(result)
        else:
            deferred[result["reason"]] += 1

    def apply_gleif(tag: str, first_checkpoint: int) -> int:
        checkpoint = first_checkpoint
        for i in range(0, len(assertions), GLEIF_BATCH):
            started = time.monotonic()
            stage.apply(batch_id=f"gleif-{tag}-{i // GLEIF_BATCH + 1}", run_id=str(uuid4()), policy_digest=policy,
                        consumer="gleif-proving", expected_checkpoint=checkpoint - 1, checkpoint=checkpoint,
                        as_of=AS_OF, assertions=assertions[i:i + GLEIF_BATCH])
            timings.append({"gleif": f"{tag}-{i // GLEIF_BATCH + 1}", "seconds": round(time.monotonic() - started, 1)})
            print(json.dumps(timings[-1]), flush=True)
            checkpoint += 1
        return checkpoint

    next_checkpoint = apply_gleif("first", 1)
    with database.application.connect() as conn:
        after_first = counts(conn)
        first_masters = masters(conn)

    apply_sec()
    apply_gleif("second", next_checkpoint)
    with database.application.connect() as conn:
        after_second = counts(conn)
        second_masters = masters(conn)
        review_sample = [r[0] for r in conn.execute(text(
            "SELECT body FROM mdm_v2.projection WHERE object_type='review' "
            "AND body->'open'='true'::jsonb LIMIT 5"))]

    both = [m for m in first_masters.values() if m["ciks"] and m["leis"]]
    by_cik = {cik: m for m in first_masters.values() for cik in m["ciks"]}
    report = {
        "ticket": "company mastering 27, Proving Run",
        "policy": digest(POLICY),
        "population": json.loads((work / "census.json").read_text())["sec"].get("filers"),
        "cohort_leis_named_by_census": len(leis),
        "gleif_records_read": len(rows),
        "gleif_assertions": len(assertions),
        "gleif_set_aside": dict(deferred),
        "after_first_pass": after_first,
        "after_second_pass": after_second,
        "second_pass_changed_nothing": after_first == after_second and first_masters == second_masters,
        "companies_with_cik_and_lei": len(both),
        "cik_on_two_companies": sorted(c for c in by_cik
                                       if sum(c in m["ciks"] for m in first_masters.values()) > 1),
        "company_with_two_ciks": sum(len(m["ciks"]) > 1 for m in first_masters.values()),
        "company_with_two_leis": sum(len(m["leis"]) > 1 for m in first_masters.values()),
        "named": {name: {k: sorted(v) for k, v in by_cik.get(cik, {}).items()} for cik, name in NAMED.items()},
        "examples_joined": [{k: sorted(v) for k, v in m.items()} for m in both[:10]],
        "review_sample": review_sample,
        "timings": timings,
    }
    out.write_text(json.dumps(report, sort_keys=True, indent=1, default=str) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("review_sample", "timings")},
                     indent=1, default=str))
    assert report["second_pass_changed_nothing"]
