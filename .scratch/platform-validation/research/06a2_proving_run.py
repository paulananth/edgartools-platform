"""Platform validation 06a2: ticket 27's Proving Run with GLEIF's accounting-
parent links added (operator: "Yes", 2026-10-01).

It is ticket 27's run with these changes: the policy is the repo's
(GLEIF's relationship file among Company's sources); after the Level 1
records, every GLEIF relationship record whose two ends are both LEIs the
census names is read by `record_evidence` under the repo's relationships
contract and applied, in saves of 200; each save prints its size by part
(05b); and the report adds the parent links and why any wait.

Ticket 27's notes follow.

Ticket 27: the Proving Run of the Company policy with both name rules on.

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
(`mdm.run` since platform validation slice 2a).

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

from edgar_warehouse.mdm.clean.run import RunCoordinator
from edgar_warehouse.mdm.clean.cli import execute_manifest
from edgar_warehouse.mdm.clean.company_source import CONTRACT, POLICY, SOURCE_CODE
from edgar_warehouse.mdm.clean.gleif_source import dataset_contract, inspect_archive, record_evidence
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, canonical, digest, register_policy
from tests.integration import test_clean_mdm_postgres as core
from tests.support.rules_authority import register_dataset

postgres = core.postgres
database = core.database

GLEIF = "gleif.level1.v1"
LINKS = "gleif.relationships.v1"
RR_ARCHIVE = Path.home() / ".local/share/edgartools/clean-mdm/research/gleif-20260911-1600/01-20260911-1600-gleif-goldencopy-rr-golden-copy.json.zip"
RR_SHA256 = "089a2513d2b5d78fc6359c87ef4bc25a56ac7f58d6b3cb740b954e3ecd2bd0c3"
RR_METADATA = {"format": "json.zip", "cdf_version": "RR_2.1", "content_date": "2026-09-11T16:00:00+00:00",
               "file_content": "GLEIF_FULL_PUBLISHED", "delta_start": None, "record_count": 487721}
GLEIF_DIR = Path.home() / ".local/share/edgartools/clean-mdm/research/gleif-20260911-1600"
ARCHIVE = GLEIF_DIR / "01-20260911-1600-gleif-goldencopy-lei2-golden-copy.json.zip"
ARCHIVE_SHA256 = "1b6cd9cda3f94269fd406ee481842ea042b699e95eb5b8124b1496d4fda36a6a"
AS_OF = "2026-09-29T15:00:00+00:00"
# A batch request is capped at 16 MiB (`write_batch`); each GLEIF
# assertion carries its native record, so 1,000 of them came to 43 MB.
GLEIF_BATCH = 200
# Links go in saves of 200, as GLEIF records do. Before #772 every review
# copied its whole closure, and 200 links came to 24 MB (2026-10-01).
LINK_BATCH = GLEIF_BATCH
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
        "identities": group("SELECT kind, count(*) FROM mdm.master_entity GROUP BY kind"),
        "companies_open": one("SELECT count(*) FROM mdm.current_entity WHERE kind='company' AND status<>'alias'"),
        "stage_records": group("SELECT source_code||':'||kind, count(*) FROM mdm.stage_record GROUP BY 1"),
        "stage_bound": group("SELECT source_code, count(*) FROM mdm.stage_record WHERE entity_id IS NOT NULL GROUP BY 1"),
        "waiting": group("SELECT source_code||':'||coalesce(reason,'(none)'), count(*) FROM mdm.stage_waiting GROUP BY 1"),
        "open_reviews": group("SELECT coalesce(body->>'reason','(none)'), count(*) FROM mdm.current_record "
                              "WHERE object_type='review' AND body->'open'='true'::jsonb GROUP BY 1"),
        "decisions": group("SELECT operation, count(*) FROM mdm.decision GROUP BY 1"),
        "decisions_by_rule": group("SELECT coalesce(body->>'rule_id', body->'rule'->>'rule_id', '(none)'), count(*) "
                                   "FROM mdm.decision GROUP BY 1"),
    }


def masters(conn) -> dict:
    """Each open Company's CIKs and LEIs, from the records bound to it."""
    out: dict[str, dict] = {}
    for entity, source, cik, lei in conn.execute(text(
        "SELECT entity_id::text, source_code, reading->'identifiers'->>'cik', reading->'identifiers'->>'lei' "
        "FROM mdm.stage_record WHERE entity_id IS NOT NULL"
    )):
        m = out.setdefault(entity, {"ciks": set(), "leis": set()})
        if cik:
            m["ciks"].add(cik)
        if lei:
            m["leis"].add(lei)
    return out


def group(conn, sql) -> dict:
    return {str(k): v for k, v in conn.execute(text(sql)).all()}


def links(conn) -> dict:
    """Each projected link: type, ends (with their CIKs/LEIs) and periods."""
    out = {}
    for (body,) in conn.execute(text("SELECT body FROM mdm.current_record WHERE object_type='relationship'")):
        out[body["relationship_id"]] = {k: body.get(k) for k in ("type", "source_id", "target_id", "scope",
                                                                  "periods", "derived", "last_seen")}
    return out


def test_proving_run(database, tmp_path):
    work = Path(os.environ["PROVING_WORK"]).expanduser()
    out = work / "report-06a2.json"
    with database.admin.begin() as conn:
        register_dataset(conn, SOURCE_CODE, database.registry, CONTRACT)
        register_dataset(conn, GLEIF, database.registry, dataset_contract("level1"))
        register_dataset(conn, LINKS, database.registry, dataset_contract("relationships"))
        policy = register_policy(conn, POLICY)
    store = Store(database.application)
    coordinator = RunCoordinator(store)
    stage = MergeStage(store)
    # What fills a save: bytes per part of each request (05b, 2026-10-01).
    sizes = []
    commit = store.commit

    def measured_commit(conn, request, run_id):
        part = Counter()
        for key in ("assertions", "decisions", "identities"):
            part[key] = len(json.dumps(request.get(key) or []))
        reviews = 0
        for p in request.get("projections") or []:
            name = p["object_type"] + ("_retired" if p["body"].get("retired") else "")
            part[name] += len(json.dumps(p))
            if p["object_type"] == "review" and not p["body"].get("retired"):
                reviews += 1
                part["review_affected_lists"] += len(json.dumps(p["body"].get("affected_subjects", []))) + len(
                    json.dumps(p["body"].get("affected_entities", [])))
        line = {"save": request.get("batch_id"), "mb": round(sum(v for k, v in part.items()
                                                                 if k != "review_affected_lists") / 1e6, 2),
                "reviews": reviews, "parts_mb": {k: round(v / 1e6, 2) for k, v in sorted(part.items())}}
        sizes.append(line)
        print(json.dumps(line), flush=True)
        return commit(conn, request, run_id)

    store.commit = measured_commit

    # Ticket 27's bundles name its policy (75bd2b67); as ticket 05 did, each is
    # copied and pointed at the policy registered here, which adds GLEIF's
    # relationship file to Company's sources and changes nothing else Company reads.
    import shutil

    bundles = []
    for n in range(1, 8):
        target = tmp_path / f"chunk{n}"
        shutil.copytree(work / "bundles" / f"chunk{n}", target)
        body = json.loads((target / "manifest.json").read_text())
        assert body["policy_digest"].startswith("75bd2b67")
        body["policy_digest"] = policy
        (target / "manifest.json").write_text(canonical(body) + "\n")
        bundles.append(target)
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

    # GLEIF's relationship records whose two ends are both census LEIs.
    started = time.monotonic()
    link_rows = []

    def keep_link(row: dict, ordinal: int) -> None:
        rel = (row.get("RelationshipRecord") or {}).get("Relationship") or {}
        ends = [((rel.get(side) or {}).get("NodeID") or {}).get("$") for side in ("StartNode", "EndNode")]
        if all(e in leis for e in ends):
            link_rows.append((ordinal, row))

    rr_info = inspect_archive(RR_ARCHIVE.open("rb"), member="relationships", metadata=RR_METADATA,
                              expected_sha256=RR_SHA256, on_record=keep_link)
    link_publication = {"publication_key": "gleif-golden-copy-rr-20260911-1600", "revision": 1,
                        "artifact_sha256": RR_SHA256, "member": "relationships"}
    link_assertions, link_deferred = [], Counter()
    link_contract = dataset_contract("relationships")
    for ordinal, row in link_rows:
        kind, result = record_evidence(row, member="relationships", contract=link_contract, source_code=LINKS,
                                       eligible_leis=leis, publication=link_publication, ordinal=ordinal)
        if kind == "assertion":
            link_assertions.append(result)
        else:
            link_deferred[result["reason"]] += 1
    timings.append({"gleif_links_read": len(link_rows), "records_in_file": rr_info["record_count"],
                    "seconds": round(time.monotonic() - started, 1)})
    print(json.dumps(timings[-1]), flush=True)

    def apply_links(tag: str, checkpoint: int) -> int:
        for i in range(0, len(link_assertions), LINK_BATCH):
            started = time.monotonic()
            stage.apply(batch_id=f"links-{tag}-{i // LINK_BATCH + 1}", run_id=str(uuid4()), policy_digest=policy,
                        consumer="gleif-proving", expected_checkpoint=checkpoint - 1, checkpoint=checkpoint,
                        as_of=AS_OF, assertions=link_assertions[i:i + LINK_BATCH])
            timings.append({"links": f"{tag}-{i // LINK_BATCH + 1}", "seconds": round(time.monotonic() - started, 1)})
            print(json.dumps(timings[-1]), flush=True)
            checkpoint += 1
        return checkpoint

    next_checkpoint = apply_gleif("first", 1)
    next_checkpoint = apply_links("first", next_checkpoint)
    with database.application.connect() as conn:
        after_first = counts(conn)
        first_masters = masters(conn)
        first_links = links(conn)

    apply_sec()
    next_checkpoint = apply_gleif("second", next_checkpoint)
    apply_links("second", next_checkpoint)
    with database.application.connect() as conn:
        after_second = counts(conn)
        second_masters = masters(conn)
        second_links = links(conn)
        link_reviews = group(conn, "SELECT body->>'reason', count(*) FROM mdm.current_record WHERE object_type='review' "
                                   "AND body->'open'='true'::jsonb AND body ? 'relationship' GROUP BY 1")
        review_sample = [r[0] for r in conn.execute(text(
            "SELECT body FROM mdm.current_record WHERE object_type='review' "
            "AND body->'open'='true'::jsonb LIMIT 5"))]

    both = [m for m in first_masters.values() if m["ciks"] and m["leis"]]
    by_cik = {cik: m for m in first_masters.values() for cik in m["ciks"]}
    report = {
        "ticket": "platform validation 06a2: ticket 27's Proving Run with GLEIF parent links",
        "policy": digest(POLICY),
        "population": json.loads((work / "census.json").read_text())["sec"].get("filers"),
        "cohort_leis_named_by_census": len(leis),
        "gleif_records_read": len(rows),
        "gleif_assertions": len(assertions),
        "gleif_set_aside": dict(deferred),
        "after_first_pass": after_first,
        "after_second_pass": after_second,
        "second_pass_changed_nothing": (after_first == after_second and first_masters == second_masters
                                        and first_links == second_links),
        "gleif_link_records_with_both_ends_named": len(link_rows),
        "gleif_link_assertions": len(link_assertions),
        "gleif_links_set_aside": dict(link_deferred),
        "parent_links": {"by_type": dict(Counter(l["type"] for l in first_links.values())),
                         "examples": list(first_links.values())[:10]},
        "link_reviews_open": link_reviews,
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
