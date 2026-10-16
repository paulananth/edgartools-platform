"""ISSUED_BY by the issuer's LEI (tickets 22 and 97): Proving Run 2.

Run 1 found no issuer became a Company. With ticket 97 a GLEIF record an
N-PORT holding names as issuer creates or joins its Company by LEI. This run
masters, on a disposable PostgreSQL 16 (removed afterwards; zero requests):

1. the cm27 SEC Companies (6,726 records, the cohort the Company proof used),
   so the SEC-GLEIF name rules can bind and duplicates can be counted;
2. GLEIF Level 1: the cm27 cohort's GLEIF records and the 28,397 issuer
   records, through the real Level 1 reading (`rules/sources/gleif/
   level1-json.yaml`, with `approved_scope` and `nport_issuers` filled) and the
   `mdm.prepare` worker with `record_extras: [nport_issuer]`: nothing is
   flagged by hand;
3. the N-PORT CUSIP Securities with their ISSUED_BY links.

The issuer rule, N-PORT's three Security rules and the two Identifier
Contracts' verifications are switched on here only, in a copy of the policy
(a Proving Run activation). Then everything is applied again; the second pass
must change nothing. Counts only.

    PG16_SERVER=pgserver GLEIF_ISSUERS=~/edgar-local-tmp/nissuer/gleif-issuers.jsonl \\
    CM27=~/.local/share/edgartools/clean-mdm/proving/cm27 \\
    PREPARED_NPORT=~/edgar-local-tmp/nissuer/mdm-security \\
    PROVING_WORK=~/.local/share/edgartools/clean-mdm/proving/nport-issuer-2 \\
    python -m pytest -q -s -p no:randomly -p no:cacheprovider .scratch/onboarding/sec.nport/issuer_proving_run_2.py
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import shutil
import sys
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sqlalchemy import text

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
from edgar_warehouse.mdm.clean.evidence import deferred_record
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, canonical, register_policy
from edgar_warehouse.rules import files
from edgar_warehouse.workers import mdm_prepare, source_read
from tests.integration import test_clean_mdm_postgres as core
from tests.support.rules_authority import register_dataset

postgres = core.postgres
database = core.database

AS_OF = "2026-10-16T00:00:00+00:00"
MAX_RECORDS, MAX_BYTES = 1000, 12 * 1024 * 1024
SEC, GLEIF, NPORT = "sec.submissions.company.v1", "gleif.level1.v1", "sec.nport.security.v1"
NPORT_RULES = ("nport-security-cusip", "nport-security-isin", "nport-isin-security-isin")
ISSUER_RULE = "gleif-issuer-lei"
STAMP = {"corpus_sha256": "0" * 64, "approved_by": "proving run", "approved_at": AS_OF,
         "reason": "Proving Run activation only"}


def proving_policy() -> dict:
    body = files.policy()
    active = {r["rule_id"] for r in body["automatic_rules"]}
    for kind, namespace, rules in (("security", "isin", NPORT_RULES), ("company", "lei", (ISSUER_RULE,))):
        block = body["kinds"][kind]
        block["identifiers"][namespace].setdefault("verification", dict(STAMP))
        for rule in block["rules"]:
            if rule["rule_id"] in rules and rule["rule_id"] not in active:
                body["automatic_rules"].append({"kind": kind, "family": "binding", "rule_id": rule["rule_id"],
                                                "rule_version": rule["version"], "verdict": "bind",
                                                "activation": "deterministic"})
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


def sec_rows(cm27: Path):
    for records in sorted((cm27 / "bundles").glob("chunk*/records.jsonl")):
        for n, line in enumerate(records.open(), 1):
            row = json.loads(line)
            member = f"cm27/{records.parent.name}/line={n}"
            sha = hashlib.sha256(canonical(row).encode()).hexdigest()
            yield row, {"publication_key": f"{member}@{sha}", "revision": 1, "semantics": "patch",
                        "artifact_sha256": sha, "member": member, "record_locator": member}


def gleif_prepared(work: Path, cm27: Path, issuers_file: Path) -> tuple[Path, int, int]:
    """The GLEIF Level 1 records through the real reading and mdm.prepare (record_extras)."""
    by_lei, issuer_leis = {}, set()
    for line in issuers_file.open():
        _, row = json.loads(line)
        by_lei[row["LEI"]["$"]] = row
        issuer_leis.add(row["LEI"]["$"])
    for line in next(cm27.glob("gleif-rows-*.jsonl")).open():
        _, row = json.loads(line)
        by_lei.setdefault(row["LEI"]["$"], row)
    rows = [by_lei[lei] for lei in sorted(by_lei)]
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr("golden-copy.json", json.dumps({"records": rows}))
    rules = files.load(files.ROOT / "sources/gleif/level1-json.yaml")
    # The archive holds only the wanted records, so the run's selection is
    # dropped here: 32,000 LEIs in `approved_scope` exceed the 1 MiB a contract
    # is read within (the issuer set travels as a lookup receipt, ticket 97).
    rules["read"]["tables"]["level1"].pop("select")
    store, root = Artifacts(), work / "gleif"
    shutil.rmtree(root, ignore_errors=True)  # the zip's timestamps make each run's bytes new
    root.mkdir(parents=True)
    capture = store.put_bytes((root / "golden-copy.zip").as_uri(), raw.getvalue())
    contract = store.put(root.as_uri(), rules)
    context = store.put(root.as_uri(), {"version": 1, "input": capture, "values": {"publication_count": len(rows)}})
    lookups = store.put(root.as_uri(), {"version": 1, "input": capture, "sets": {"nport_issuers": sorted(issuer_leis)}})
    manifest = store.put(root.as_uri(), {"version": 3, "contract": contract,
                                         "artifacts": [{"input": capture, "context": context, "lookups": lookups}]})
    envelope = {"input": manifest, "output": (root / "reading.json").as_uri(), "checks": ["source.output"]}
    reading = source_read.execute(envelope, store)
    assert source_read.verify({**envelope, "candidate": reading}, store) == ({"source.output": True}, [])
    prepare = {"input": reading, "output": (root / "mdm/manifest.json").as_uri(), "checks": ["mdm.prepared"],
               "keys": {"table": "level1", "record_column": "record", "record_extras": ["nport_issuer"],
                        "dataset": GLEIF, "policy": "0" * 64, "consumer": "proving", "batch_id": "gleif",
                        "as_of": AS_OF}}
    prepared = mdm_prepare.execute(prepare, store)
    assert mdm_prepare.verify({**prepare, "candidate": prepared}, store) == ({"mdm.prepared": True}, [])
    return root / "mdm", len(rows), len(issuer_leis)


def prepared_rows(folder: Path):
    manifest = json.loads((folder / "manifest.json").read_bytes())
    for batch in manifest["batches"]:
        data = batch["input"]
        for n, line in enumerate((folder / data["path"]).read_bytes().splitlines(), 1):
            yield json.loads(line), {**data["publication"], "semantics": "patch", "artifact_sha256": data["sha256"],
                                     "member": data["path"], "record_locator": f"{data['sha256']}:line:{n}"}


def counts(conn) -> dict:
    group = lambda sql: {str(k): v for k, v in conn.execute(text(sql)).all()}
    return {
        "identities": group("SELECT kind, count(*) FROM mdm.master_entity GROUP BY kind"),
        "stage_records": group("SELECT source_code, count(*) FROM mdm.stage_record GROUP BY 1"),
        "bound": group("SELECT source_code, count(*) FROM mdm.stage_record WHERE entity_id IS NOT NULL GROUP BY 1"),
        "waiting": group("SELECT coalesce(reason,'(none)'), count(*) FROM mdm.stage_waiting GROUP BY 1"),
        "open_reviews": group("SELECT coalesce(body->>'reason','(none)'), count(*) FROM mdm.current_record "
                              "WHERE object_type='review' AND body->'open'='true'::jsonb GROUP BY 1"),
        "decisions": group("SELECT operation, count(*) FROM mdm.decision GROUP BY 1"),
        "relationships": group("SELECT type || ' ' || coalesce(from_kind,'?') || ' -> ' || coalesce(to_kind,'?'), "
                               "count(DISTINCT relationship_id) FROM mdm.relationship_context GROUP BY 1"),
    }


def companies_by_feeds(conn) -> dict:
    return {str(k): v for k, v in conn.execute(text(
        "SELECT feeds, count(*) FROM (SELECT s.entity_id, string_agg(DISTINCT s.source_code, ' + ' "
        "ORDER BY s.source_code) AS feeds FROM mdm.stage_record s JOIN mdm.master_entity m "
        "ON m.entity_id = s.entity_id WHERE m.kind = 'company' GROUP BY 1) t GROUP BY 1")).all()}


def lei_holders(conn) -> Counter:
    return Counter(value for value, _ in conn.execute(text(
        "SELECT DISTINCT s.reading->'identifiers'->>'lei', s.entity_id FROM mdm.stage_record s "
        "WHERE s.entity_id IS NOT NULL AND s.reading->'identifiers' ? 'lei'")).all())


def duplicates(conn, sec_leis: dict[str, set[str]]) -> dict:
    """Issuer GLEIF records whose LEI an SEC Company's census also names, and
    whether both ended on one Company."""
    gleif_entity = dict(conn.execute(text(
        "SELECT reading->'identifiers'->>'lei', entity_id::text FROM mdm.stage_record "
        "WHERE source_code = :g AND entity_id IS NOT NULL "
        "AND reading->'provenance'->'matching'->>'nport_issuer' = 'true'"), {"g": GLEIF}).all())
    sec_entity = dict(conn.execute(text(
        "SELECT record_key, entity_id::text FROM mdm.stage_record WHERE source_code = :s AND entity_id IS NOT NULL"),
        {"s": SEC}).all())
    found = Counter()
    for lei, entity in gleif_entity.items():
        ciks = sec_leis.get(lei, set())
        if not ciks:
            found["issuer, no SEC filer names its LEI"] += 1
        elif any(sec_entity.get(cik) == entity for cik in ciks):
            found["issuer, on the same Company as its SEC filer"] += 1
        else:
            found["issuer, on another Company than its SEC filer (duplicate)"] += 1
    return dict(found)


def test_proving_run(database):
    work = Path(os.environ["PROVING_WORK"]).expanduser()
    work.mkdir(parents=True, exist_ok=True)
    cm27 = Path(os.environ["CM27"]).expanduser()
    begun = time.monotonic()
    gleif_folder, gleif_records, issuers = gleif_prepared(work, cm27, Path(os.environ["GLEIF_ISSUERS"]).expanduser())
    prepare_seconds = round(time.monotonic() - begun, 1)
    body = proving_policy()
    contracts = {SEC: files.mdm_contract("sec.submissions.company", SEC), GLEIF: files.mdm_contract("gleif", GLEIF),
                 NPORT: files.mdm_contract("sec.nport.security", NPORT)}
    with database.admin.begin() as conn:
        for code, contract in contracts.items():
            register_dataset(conn, code, database.registry, contract)
        policy = register_policy(conn, copy.deepcopy(body))
    stage = MergeStage(Store(database.application))
    nport = Path(os.environ["PREPARED_NPORT"]).expanduser()
    feeds = ((SEC, lambda: sec_rows(cm27)), (GLEIF, lambda: prepared_rows(gleif_folder)),
             (NPORT, lambda: prepared_rows(nport)))
    timings, read_counts, flagged = [], Counter(), Counter()
    sec_leis: dict[str, set[str]] = defaultdict(set)

    def apply_all(tag, checkpoint):
        n = 0
        for code, rows in feeds:
            read_rows = [read(row, code, contracts[code], body, pub) for row, pub in rows()]
            if tag == "first":
                for kind, record in read_rows:
                    read_counts[f"{code} {kind if kind == 'assertions' else 'deferred: ' + record['reason']}"] += 1
                    if code == GLEIF and kind == "assertions":
                        flagged[str(((record.get("provenance") or {}).get("matching") or {}).get("nport_issuer"))] += 1
                    if code == SEC and kind == "assertions":
                        census = ((record.get("provenance") or {}).get("matching") or {}).get("name_census") or {}
                        for lei in [*(pair[0] for pair in census.get("leis") or []),
                                    (census.get("cascade") or {}).get("lei")]:
                            if lei:
                                sec_leis[lei].add(record["record_key"])
            for wanted in ("assertions", "deferred"):
                batch, size = [], 0
                chosen = [record for kind, record in read_rows if kind == wanted]
                for i, record in enumerate(chosen):
                    batch.append(record)
                    size += len(canonical(record))
                    if len(batch) >= MAX_RECORDS or size > MAX_BYTES or i == len(chosen) - 1:
                        n += 1
                        began = time.monotonic()
                        stage.apply(batch_id=f"nissuer2-{tag}-{n}", run_id=str(uuid4()), policy_digest=policy,
                                    consumer="nport-issuer-proving-2", expected_checkpoint=checkpoint - 1,
                                    checkpoint=checkpoint, as_of=AS_OF, **{wanted: batch})
                        timings.append(round(time.monotonic() - began, 1))
                        checkpoint += 1
                        batch, size = [], 0
                        if n % 50 == 0:
                            print(f"{tag} {code}: {n} batches", flush=True)
            print(f"{tag} {code}: applied, {n} batches so far", flush=True)
        return checkpoint

    def snapshot():
        with database.application.connect() as conn:
            return counts(conn), lei_holders(conn), companies_by_feeds(conn), duplicates(conn, sec_leis)

    begun = time.monotonic()
    nxt = apply_all("first", 1)
    first_seconds = round(time.monotonic() - begun, 1)
    first = snapshot()
    begun = time.monotonic()
    apply_all("second", nxt)
    second_seconds = round(time.monotonic() - begun, 1)
    second = snapshot()

    issued = first[0]["relationships"]
    report = {
        "run": "ISSUED_BY by issuer LEI, Proving Run 2 (issuer rule, real Level 1 reading and record_extras)",
        "policy_digest": policy,
        "gleif_records_read": gleif_records, "issuer_leis_listed": issuers,
        "read": dict(read_counts), "gleif_flag_on_assertions": dict(flagged),
        "after_first_pass": first[0], "after_second_pass": second[0],
        "companies_by_feeds": first[2], "issuers_and_sec_filers": first[3],
        "issued_by_resolved": {k: v for k, v in issued.items() if k.startswith("ISSUED_BY")},
        "second_pass_changed_nothing": first == second,
        "lei_on_two_entities": sum(1 for c in first[1].values() if c > 1),
        "seconds": {"gleif_prepare": prepare_seconds, "first_pass": first_seconds, "second_pass": second_seconds},
        "batches": len(timings), "slowest_batch_seconds": max(timings, default=0),
    }
    (work / "report.json").write_text(json.dumps(report, sort_keys=True, indent=1, default=str) + "\n")
    print(json.dumps(report, indent=1, default=str))
    assert report["second_pass_changed_nothing"]
