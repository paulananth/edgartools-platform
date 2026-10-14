"""Person feed 1 with its links: the switch-on proof (rebuild ticket 11).

One disposable PostgreSQL 16 store (the MDM test fixtures) takes, with the
repo's merge rules as they are on main (Person feed 1's rules on since
2026-10-01, the ownership rules since #964, ticket 10's checks since #967):

1. the cm27 Companies the local Forms 3, 4, 5 filings name as issuers;
2. every SEC submissions document (76,230), read as Person feed 1;
3. every reporting owner of the local filings (p07), with its insider links.

Then everything again: the second pass must change nothing. Zero requests leave
the machine; the report holds counts only (names and CIKs stay local).

    PROVING_WORK=~/.local/share/edgartools/clean-mdm/proving/person-switch-on \\
    DOCKER_HOST=unix://$HOME/.colima/default/docker.sock \\
    uv run --no-sync pytest -q -s -p no:randomly .scratch/onboarding/sec.submissions.person/switch_on_proof.py
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

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2]))
sys.path.insert(0, str(HERE.parent / "sec.ownership"))
sys.path.insert(0, str(HERE))

from sqlalchemy import text  # noqa: E402

import proving_run as person_feed  # noqa: E402  (this folder's Person feed 1 run)

del sys.modules["proving_run"]
sys.path.remove(str(HERE))
import proving_run as ownership  # noqa: E402  (the ownership feed's run)

from edgar_warehouse.mdm.clean.merge import MergeStage  # noqa: E402
from edgar_warehouse.mdm.clean.store import Store, canonical, register_policy  # noqa: E402
from edgar_warehouse.rules import files  # noqa: E402
from tests.integration import test_clean_mdm_postgres as core  # noqa: E402
from tests.support.rules_authority import register_dataset  # noqa: E402

postgres = core.postgres
database = core.database

COMPANY, OWNER, PERSON = ownership.COMPANY, ownership.OWNER, person_feed.SOURCE_CODE
AS_OF = "2026-10-14T00:00:00+00:00"
MAX_RECORDS, MAX_BYTES = 1000, 12 * 1024 * 1024


def people_by_source(conn) -> dict:
    """How many Persons each combination of feeds states."""
    rows = conn.execute(text(
        "SELECT string_agg(DISTINCT s.source_code, ' + ' ORDER BY s.source_code) "
        "FROM mdm.stage_record s JOIN mdm.master_entity m ON m.entity_id = s.entity_id "
        "WHERE m.kind = 'person' GROUP BY s.entity_id")).all()
    return dict(sorted(Counter(r[0] for r in rows).items()))


def test_switch_on_proof(database):
    work = Path(os.environ["PROVING_WORK"]).expanduser()
    work.mkdir(parents=True, exist_ok=True)
    body = files.policy()
    contracts = {COMPANY: files.mdm_contract("sec.submissions.company", COMPANY),
                 PERSON: files.mdm_contract("sec.submissions.person", PERSON),
                 OWNER: files.mdm_contract("sec.ownership", OWNER)}
    with database.admin.begin() as conn:
        for code, contract in contracts.items():
            register_dataset(conn, code, database.registry, contract)
        policy = register_policy(conn, copy.deepcopy(body))
    stage = MergeStage(Store(database.application))

    started = time.monotonic()
    read_filings = ownership.filings()
    issuers = {int(t["ownership_document"][0]["issuer_cik"]) for _, t in read_filings}
    issuer_rows = ownership.companies(issuers)
    documents = person_feed.documents()
    read_seconds = round(time.monotonic() - started, 1)
    timings, read_counts = [], Counter()

    def records(tag: str, count: bool):
        """Companies first, then Persons, then owners, so each link finds its ends.
        `count`: tally what is read (once a run: the records are read once per kind of record)."""
        for row in issuer_rows:
            member = f"cm27/cik={row['cik']}"
            sha = hashlib.sha256(canonical(row).encode()).hexdigest()
            yield COMPANY, ownership.read(row, COMPANY, contracts[COMPANY], body,
                                          {"publication_key": f"{member}@{sha}", "revision": 1,
                                           "artifact_sha256": sha, "member": member, "record_locator": member})
        for receipt in documents:
            kind, record = person_feed.read(receipt, contracts[PERSON], body)
            kind = "assertions" if kind == "assertion" else kind
            if count:
                read_counts[f"{PERSON} " + (kind if kind == "assertions" else record["reason"])] += 1
            yield PERSON, (kind, record)
        for sha, tables in read_filings:
            for row in tables["reporting_owner"]:
                member = f"{row['accession']}#{row['position']}"
                kind, record = ownership.read(row, OWNER, contracts[OWNER], body,
                                              {"publication_key": f"{row['accession']}@{sha}", "revision": 1,
                                               "artifact_sha256": sha, "member": member, "record_locator": member})
                if count:
                    read_counts[f"{OWNER} " + (kind if kind == "assertions" else record["reason"])] += 1
                yield OWNER, (kind, record)

    def apply_all(tag: str, checkpoint: int) -> int:
        pending = {"assertions": ([], [0]), "deferred": ([], [0])}
        n = 0

        def flush(key: str) -> None:
            nonlocal n, checkpoint
            batch, size = pending[key]
            if not batch:
                return
            n += 1
            begun = time.monotonic()
            stage.apply(batch_id=f"switch-on-{tag}-{n}", run_id=str(uuid4()), policy_digest=policy,
                        consumer="person-switch-on-proof", expected_checkpoint=checkpoint - 1,
                        checkpoint=checkpoint, as_of=AS_OF, **{key: list(batch)})
            timings.append({"batch": f"{tag}-{n}", key: len(batch), "seconds": round(time.monotonic() - begun, 1)})
            checkpoint += 1
            batch.clear()
            size[0] = 0

        # Every reading first, then every set-aside record; one source a batch.
        for wanted in ("assertions", "deferred"):
            source = None
            for code, (kind, record) in records(tag, count=tag == "first" and wanted == "assertions"):
                if kind != wanted:
                    continue
                if code != source:
                    flush(wanted)
                    source = code
                batch, size = pending[wanted]
                weight = len(canonical(record))
                if len(batch) >= MAX_RECORDS or size[0] + weight > MAX_BYTES:
                    flush(wanted)
                batch.append(record)
                size[0] += weight
            flush(wanted)
        return checkpoint

    begun = time.monotonic()
    nxt = apply_all("first", 1)
    first_seconds = round(time.monotonic() - begun, 1)
    with database.application.connect() as conn:
        after_first, first_ciks, first_sources = ownership.counts(conn), ownership.ciks_by_kind(conn), people_by_source(conn)
    begun = time.monotonic()
    apply_all("second", nxt)
    second_seconds = round(time.monotonic() - begun, 1)
    with database.application.connect() as conn:
        after_second, second_ciks, second_sources = ownership.counts(conn), ownership.ciks_by_kind(conn), people_by_source(conn)

    person, company = first_ciks.get("person", Counter()), first_ciks.get("company", Counter())
    report = {
        "run": "Person feed 1 with its links: the switch-on proof (rebuild ticket 11)",
        "policy_digest": policy,
        "documents": len(documents), "filings": len(read_filings), "issuers": len(issuers),
        "issuer_companies_in_cm27": len(issuer_rows),
        "read": dict(sorted(read_counts.items())),
        "after_first_pass": after_first,
        "after_second_pass": after_second,
        "people_by_source": first_sources,
        "second_pass_changed_nothing": (after_first == after_second and first_ciks == second_ciks
                                        and first_sources == second_sources),
        "persons_by_cik": len(person),
        "cik_on_two_persons": sum(1 for n in person.values() if n > 1),
        "cik_both_person_and_company": len(set(person) & set(company)),
        "seconds": {"read": read_seconds, "first_pass": first_seconds, "second_pass": second_seconds},
        "batches": len(timings),
        "slowest_batch_seconds": max((t["seconds"] for t in timings), default=0),
    }
    (work / "report.json").write_text(json.dumps(report, sort_keys=True, indent=1, default=str) + "\n")
    (work / "batches.jsonl").write_text("".join(json.dumps(t) + "\n" for t in timings))
    print(json.dumps(report, indent=1, default=str))
    assert report["second_pass_changed_nothing"]
