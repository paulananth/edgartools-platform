"""Tickets 75 and 76: Form ADV through the Merge Stage beside the GLEIF and SEC Companies.

On a disposable PostgreSQL 16 (removed afterwards; zero provider requests),
with the Form ADV matching rules (`iapd-adv-crd`, `iapd-adv-custodian-lei`,
`iapd-adv-custodian-bd`), the issuer rule and their Identifier Contracts
switched on in a copy of the policy only (a Proving Run activation), this
masters:

1. the cm27 SEC Companies (6,726 records), so the SEC-GLEIF name rules bind;
2. GLEIF Level 1: the cm27 cohort's records and the N-PORT issuer records
   (ticket 22's set), through the real reading and `mdm.prepare`; since ticket
   97 GLEIF is an LEI source, so a custodian LEI a GLEIF-bound Company holds
   joins it, and an LEI on two Companies goes to review;
3. all 13 local Form ADV months through the real chain (both source extracts,
   combine.yaml, `mdm.prepare` dated by `published`), each month's custodians
   before its filings, so each CUSTODIAN link names a record already loaded.

Then everything is applied again until a pass changes nothing (at most three). The
database is tuned for a throwaway run (no fsync, no synchronous commit), which
changes no result. Counts only.

    ADV_ZIPS=~/.local/share/edgartools/clean-mdm/proving/p07/inputs/warehouse/bronze/reference/iapd_adv_bulk \\
    GLEIF_ISSUERS=~/edgar-local-tmp/nissuer/gleif-issuers.jsonl \\
    CM27=~/.local/share/edgartools/clean-mdm/proving/cm27 \\
    PROVING_WORK=~/edgar-local-tmp/t76 \\
    ADV_MONTHS=13 \\
    uv run --extra mdm --extra s3 pytest -q -s -p no:randomly .scratch/rebuild-priorities/research/76_adv_merge_run.py
"""

from __future__ import annotations

import calendar
import copy
import importlib.util
import json
import os
import time
from collections import Counter
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, canonical, register_policy
from edgar_warehouse.rules import files
from edgar_warehouse.workers import mdm_prepare, source_combine, source_read
from tests.integration.conftest import database, postgres  # noqa: F401
from tests.support.rules_authority import register_dataset

ROOT = Path(__file__).resolve().parents[3]
# The helper file was written before #1027 moved the fixtures to conftest.py.
from tests.integration import test_clean_mdm_postgres as _core  # noqa: E402
_core.postgres, _core.database = postgres, database
_spec = importlib.util.spec_from_file_location("issuer_run", ROOT / ".scratch/onboarding/sec.nport/issuer_proving_run_2.py")
issuer_run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(issuer_run)

AS_OF = "2026-10-17T00:00:00+00:00"
SEC, GLEIF = issuer_run.SEC, issuer_run.GLEIF
FILINGS, CUSTODIANS = "iapd.adv.filings.v1", "iapd.adv.custodians.v1"
ADV = "iapd.adv"
ADV_RULES = ("iapd-adv-crd", "iapd-adv-custodian-lei", "iapd-adv-custodian-bd")
MAX_RECORDS, MAX_BYTES = issuer_run.MAX_RECORDS, issuer_run.MAX_BYTES


def proving_policy() -> dict:
    body = issuer_run.proving_policy()
    company = body["kinds"]["company"]
    for namespace in ("crd", "lei", "bd_number"):
        company["identifiers"][namespace].setdefault("verification", dict(issuer_run.STAMP))
    active = {r["rule_id"] for r in body["automatic_rules"]}
    for rule in company["rules"]:
        if rule["rule_id"] in ADV_RULES and rule["rule_id"] not in active:
            body["automatic_rules"].append({"kind": "company", "family": "binding", "rule_id": rule["rule_id"],
                                            "rule_version": rule["version"], "verdict": "bind",
                                            "activation": "deterministic"})
    return body


def adv_prepared(work: Path, zips: Path) -> list[tuple[str, Path]]:
    """Each month's custodians, then its filings, through the real chain: (code, prepared folder)."""
    store, out = Artifacts(), []
    folder = files.ROOT / "sources" / ADV
    months = sorted(zips.glob("*/*.zip"))
    for z in months[:int(os.environ.get("ADV_MONTHS", len(months)))]:
        y, m = map(int, z.parent.name.split("-"))
        published = f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}T00:00:00+00:00"
        root = work / "adv" / z.parent.name
        raw = store.put_bytes((root / "capture.zip").as_uri(), z.read_bytes())

        def read(name, contract_file):
            path = root / name
            path.mkdir(parents=True, exist_ok=True)
            body = {"source": ADV, "execution": {"profile": "source.read", "workers": 1, "max_artifacts": 1},
                    **files.load(folder / contract_file)}
            context = store.put(path.as_uri(), {"version": 1, "input": raw, "values": {"published": published}})
            manifest = store.put(path.as_uri(), {"version": 2, "contract": store.put(path.as_uri(), body),
                                                 "artifacts": [{"input": raw, "context": context}]})
            task = {"input": manifest, "output": (path / "reading.json").as_uri(), "checks": ["source.output"]}
            reading = source_read.execute(task, store)
            assert source_read.verify({**task, "candidate": reading}, store) == ({"source.output": True}, [])
            return reading

        filings, custody = read("filings", "adviser-filings-csv.yaml"), read("custody", "custody-csv.yaml")
        m_ = store.put(root.as_uri(), {"version": 1, "contract": store.put(root.as_uri(), files.load(folder / "combine.yaml")),
                                       "readings": {"filings": filings, "custody": custody}})
        task = {"input": m_, "output": (root / "combine/out.json").as_uri(), "checks": [source_combine.CHECK], "keys": {}}
        combined = source_combine.execute(task, store)
        assert source_combine.verify({**task, "candidate": combined}, store) == ({source_combine.CHECK: True}, [])
        for code, reading, table, extra in ((CUSTODIANS, custody, "custody", {"distinct_on": ["custodian_id"]}),
                                            (FILINGS, combined, "filings", {})):
            target = root / f"mdm-{code.split('.')[2]}"
            task = {"input": reading, "output": (target / "manifest.json").as_uri(), "checks": ["mdm.prepared"],
                    "keys": {"table": table, "dataset": code, "policy": "0" * 64, "consumer": "proving",
                             "batch_id": f"adv-{z.parent.name}-{code}", "as_of": AS_OF,
                             "effective_column": "published", **extra}}
            prepared = mdm_prepare.execute(task, store)
            assert mdm_prepare.verify({**task, "candidate": prepared}, store) == ({"mdm.prepared": True}, [])
            out.append((code, target))
    return out


def test_adv_merge_run(database):
    work = Path(os.environ["PROVING_WORK"]).expanduser()
    work.mkdir(parents=True, exist_ok=True)
    cm27 = Path(os.environ["CM27"]).expanduser()
    admin, _ = database.admin, database.application
    with admin.execution_options(isolation_level="AUTOCOMMIT").connect() as conn:
        for setting in ("fsync = off", "synchronous_commit = off", "full_page_writes = off",
                        "max_wal_size = '4GB'", "checkpoint_timeout = '30min'"):
            conn.execute(text(f"ALTER SYSTEM SET {setting}"))
        conn.execute(text("SELECT pg_reload_conf()"))
    begun = time.monotonic()
    gleif_folder, gleif_records, issuers = issuer_run.gleif_prepared(work, cm27, Path(os.environ["GLEIF_ISSUERS"]).expanduser())
    adv = adv_prepared(work, Path(os.environ["ADV_ZIPS"]).expanduser())
    prepare_seconds = round(time.monotonic() - begun, 1)
    print(f"prepared: GLEIF {gleif_records} records, ADV {len(adv)} folders, {prepare_seconds} s", flush=True)
    body = proving_policy()
    contracts = {SEC: files.mdm_contract("sec.submissions.company", SEC), GLEIF: files.mdm_contract("gleif", GLEIF),
                 FILINGS: files.mdm_contract(ADV, FILINGS), CUSTODIANS: files.mdm_contract(ADV, CUSTODIANS)}
    with database.admin.begin() as conn:
        for code, contract in contracts.items():
            register_dataset(conn, code, database.registry, contract)
        policy = register_policy(conn, copy.deepcopy(body))
    stage = MergeStage(Store(database.application))
    feeds = [(SEC, lambda: issuer_run.sec_rows(cm27)), (GLEIF, lambda: issuer_run.prepared_rows(gleif_folder)),
             *((code, (lambda f=folder: issuer_run.prepared_rows(f))) for code, folder in adv)]
    timings, read_counts = [], Counter()

    def apply_all(tag, checkpoint):
        n = 0
        for code, rows in feeds:
            read_rows = [issuer_run.read(row, code, contracts[code], body, pub) for row, pub in rows()]
            if tag == "first":
                for kind, record in read_rows:
                    read_counts[f"{code} {kind if kind == 'assertions' else 'deferred: ' + record['reason']}"] += 1
            for wanted in ("assertions", "deferred"):
                batch, size = [], 0
                chosen = [record for kind, record in read_rows if kind == wanted]
                for i, record in enumerate(chosen):
                    batch.append(record)
                    size += len(canonical(record))
                    if len(batch) >= MAX_RECORDS or size > MAX_BYTES or i == len(chosen) - 1:
                        n += 1
                        began = time.monotonic()
                        stage.apply(batch_id=f"adv76-{tag}-{n}", run_id=str(uuid4()), policy_digest=policy,
                                    consumer="adv-merge-run", expected_checkpoint=checkpoint - 1,
                                    checkpoint=checkpoint, as_of=AS_OF, **{wanted: batch})
                        timings.append((tag, code, round(time.monotonic() - began, 1)))
                        checkpoint += 1
                        batch, size = [], 0
            print(f"{tag} {code}: applied, {n} batches, {round(time.monotonic() - started)} s", flush=True)
        return checkpoint

    def snapshot():
        with database.application.connect() as conn:
            found = issuer_run.counts(conn)
            holders = issuer_run.lei_holders(conn)
            feeds_ = issuer_run.companies_by_feeds(conn)
            crd_holders = Counter(v for v, _ in conn.execute(text(
                "SELECT DISTINCT s.reading->'identifiers'->>'crd', s.entity_id FROM mdm.stage_record s "
                "WHERE s.entity_id IS NOT NULL AND s.reading->'identifiers' ? 'crd'")).all())
            bd_holders = Counter(v for v, _ in conn.execute(text(
                "SELECT DISTINCT s.reading->'identifiers'->>'bd_number', s.entity_id FROM mdm.stage_record s "
                "WHERE s.entity_id IS NOT NULL AND s.reading->'identifiers' ? 'bd_number'")).all())
            most_in = conn.execute(text(
                "SELECT max(n) FROM (SELECT body->>'target_id' t, count(*) n FROM mdm.current_record "
                "WHERE object_type = 'relationship' AND body->>'type' = 'CUSTODIAN' GROUP BY 1) x")).scalar()
            moved = conn.execute(text(
                "SELECT count(*) FROM mdm.current_record WHERE object_type = 'relationship' "
                "AND body->>'type' = 'CUSTODIAN' AND body->>'last_seen' > (body->'periods'->0->>'valid_from')")).scalar()
        return {"counts": found, "companies_by_feeds": feeds_,
                "leis_on_two_or_more_entities": sum(1 for v in holders.values() if v > 1),
                "crds_on_two_or_more_entities": sum(1 for v in crd_holders.values() if v > 1),
                "bd_numbers_on_two_or_more_entities": sum(1 for v in bd_holders.values() if v > 1),
                "most_custodian_links_on_one_custodian": most_in,
                "custodian_links_seen_after_their_first_month": moved}

    # Passes until one changes nothing (at most three): a record waiting for an
    # entity a later feed creates is looked at again only when applied again.
    passes, nxt = [], 1
    for tag in ("first", "second", "third"):
        started = time.monotonic()
        nxt = apply_all(tag, nxt)
        passes.append({"pass": tag, "seconds": round(time.monotonic() - started, 1), "after": snapshot()})
        print(f"{tag} pass:", json.dumps(passes[-1])[:1500], flush=True)
        if len(passes) > 1 and passes[-1]["after"] == passes[-2]["after"]:
            break
    by_feed = {}
    for tag, code, seconds in timings:
        entry = by_feed.setdefault(f"{tag} {code}", {"batches": 0, "seconds": 0.0, "slowest": 0.0})
        entry["batches"] += 1
        entry["seconds"] = round(entry["seconds"] + seconds, 1)
        entry["slowest"] = max(entry["slowest"], seconds)
    report = {"run": "Form ADV through the Merge Stage beside GLEIF and SEC (tickets 75, 76)",
              "policy_digest": policy, "gleif_records_read": gleif_records, "issuer_leis_listed": issuers,
              "read": dict(read_counts), "passes": passes,
              "last_pass_changed_nothing": len(passes) > 1 and passes[-1]["after"] == passes[-2]["after"],
              "seconds": {"prepare": prepare_seconds},
              "batches": {k: v for k, v in by_feed.items() if not k.startswith("second") or v["batches"]}}
    (work / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True))
    print(json.dumps(report, indent=1, sort_keys=True), flush=True)
    assert report["last_pass_changed_nothing"]
