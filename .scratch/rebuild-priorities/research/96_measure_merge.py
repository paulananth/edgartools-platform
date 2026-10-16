"""Ticket 96: where a Merge Stage batch's time goes as the store grows (measurement only).

The 13F Securities, then the first N-PORT CUSIP Securities (the N-PORT
Proving Run's prepared records), go through their Dataset Contracts and are
applied batch by batch on a disposable PostgreSQL 16, as in that Proving Run.
Every batch is timed; every tenth is profiled (cumulative time per function,
and time inside SQL statements by statement shape). After the first
`NPORT_BATCHES` it stops. Migration 021 turns the identifier index's pending
list off; `PENDING=on` puts it back first, so two runs tell ticket 96's share
from the rest. Counts and timings only.

    PG16_SERVER=pgserver NPORT_BATCHES=40 PENDING=on \\
    PREPARED_13F=~/edgar-local-tmp/t13f/mdm PREPARED_NPORT=~/edgar-local-tmp/figi-attach \\
    OUT=.scratch/rebuild-priorities/research/96-measure.json \\
    python -m pytest -q -s -p no:randomly -p no:cacheprovider .scratch/rebuild-priorities/research/96_measure_merge.py
"""

from __future__ import annotations

import copy
import cProfile
import json
import os
import pstats
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sqlalchemy import event, text

from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, canonical, register_policy
from edgar_warehouse.rules import files
from tests.integration import test_clean_mdm_postgres as core
from tests.support.rules_authority import register_dataset

postgres = core.postgres
database = core.database

AS_OF = "2026-10-16T00:00:00+00:00"
MAX_RECORDS = 1000
RULES = ("nport-security-cusip", "nport-security-isin", "nport-isin-security-isin")
FEEDS = (("sec.thirteenf.information_table", "sec.thirteenf.information_table.security.v1", "PREPARED_13F", "."),
         ("sec.nport.security", "sec.nport.security.v1", "PREPARED_NPORT", "mdm-security"))


def policy_body() -> dict:
    body = files.policy()
    security = body["kinds"]["security"]
    security["identifiers"]["isin"].setdefault("verification", {
        "corpus_sha256": "0" * 64, "approved_by": "measurement", "approved_at": AS_OF, "reason": "measurement only"})
    active = {r["rule_id"] for r in body["automatic_rules"]}
    for rule in security["rules"]:
        if rule["rule_id"] in RULES and rule["rule_id"] not in active:
            body["automatic_rules"].append({"kind": "security", "family": "binding", "rule_id": rule["rule_id"],
                                            "rule_version": rule["version"], "verdict": "bind",
                                            "activation": "deterministic"})
    return body


def accepted(code, contract, body, prepared: Path):
    manifest = json.loads((prepared / "manifest.json").read_bytes())
    for batch in manifest["batches"]:
        data = batch["input"]
        for n, line in enumerate((prepared / data["path"]).read_bytes().splitlines(), 1):
            pub = {**data["publication"], "artifact_sha256": data["sha256"], "member": data["path"],
                   "record_locator": f"{data['sha256']}:line:{n}"}
            try:
                yield normalize(json.loads(line), source_code=code, contract=contract, publication=pub, policy=body)
            except UnsupportedRecord:
                continue


def shape(sql: str) -> str:
    """A statement's shape: its first words, with literals and numbers removed."""
    s = re.sub(r"'[^']*'", "?", sql)
    s = re.sub(r"\b\d+\b", "?", s)
    return " ".join(s.split())[:120]


def test_measure(database):
    nport_batches = int(os.environ.get("NPORT_BATCHES", "120"))
    body = policy_body()
    contracts = {code: files.mdm_contract(src, code) for src, code, _, _ in FEEDS}
    with database.admin.begin() as conn:
        for code, contract in contracts.items():
            register_dataset(conn, code, database.registry, contract)
        policy = register_policy(conn, copy.deepcopy(body))
    stage = MergeStage(Store(database.application))

    sql_time = defaultdict(float)
    sql_calls = Counter()
    clock = {}

    @event.listens_for(database.application, "before_cursor_execute")
    def _before(conn, cursor, statement, params, context, many):
        clock[id(cursor)] = time.perf_counter()

    @event.listens_for(database.application, "after_cursor_execute")
    def _after(conn, cursor, statement, params, context, many):
        begun = clock.pop(id(cursor), None)
        if begun is not None and measuring["on"]:
            sql_time[shape(statement)] += time.perf_counter() - begun
            sql_calls[shape(statement)] += 1

    measuring = {"on": False}
    batches, profiles = [], []
    checkpoint = [1]

    def pending() -> int | None:
        try:
            with database.admin.connect() as conn:
                return conn.execute(text(
                    "SELECT pending_tuples FROM pgstatginindex('mdm.stage_record_identifiers'::regclass)")).scalar()
        except Exception:
            return None

    def apply(tag, records, profile):
        sql_time.clear()
        sql_calls.clear()
        measuring["on"] = profile
        prof = cProfile.Profile() if profile else None
        begun = time.monotonic()
        if prof:
            prof.enable()
        stage.apply(batch_id=f"m-{tag}-{checkpoint[0]}", run_id=str(uuid4()), policy_digest=policy,
                    consumer="measure-96", expected_checkpoint=checkpoint[0] - 1, checkpoint=checkpoint[0],
                    as_of=AS_OF, assertions=records)
        if prof:
            prof.disable()
        seconds = round(time.monotonic() - begun, 2)
        measuring["on"] = False
        checkpoint[0] += 1
        with database.admin.connect() as conn:
            stored = conn.execute(text("SELECT count(*) FROM mdm.stage_record")).scalar()
        row = {"tag": tag, "batch": checkpoint[0] - 1, "records": len(records), "store_before": stored - len(records),
               "seconds": seconds}
        batches.append(row)
        print(json.dumps(row), flush=True)
        if prof:
            stats = pstats.Stats(prof)
            top = sorted(((v[3], f"{Path(k[0]).name}:{k[1]}:{k[2]}") for k, v in stats.stats.items()),
                         reverse=True)[:25]
            sql = sorted(((round(t, 3), sql_calls[s], s) for s, t in sql_time.items()), reverse=True)[:12]
            profiles.append({**row, "pending_entries": pending(), "sql_seconds": round(sum(sql_time.values()), 2),
                             "top_cumulative": [[round(t, 3), name] for t, name in top],
                             "top_sql": [list(x) for x in sql]})

    try:
        with database.admin.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgstattuple"))
    except Exception as exc:
        print("pgstattuple not available:", type(exc).__name__, flush=True)

    # PENDING=on puts the pending list back (as before migration 021), to compare.
    if os.environ.get("PENDING") == "on":
        with database.admin.begin() as conn:
            conn.execute(text("ALTER INDEX mdm.stage_record_identifiers RESET (fastupdate)"))
    n_nport = 0
    for _, code, env, folder in FEEDS:
        prepared = Path(os.environ[env]).expanduser() / folder
        batch = []
        for record in accepted(code, contracts[code], body, prepared):
            batch.append(record)
            if len(batch) == MAX_RECORDS:
                if code.startswith("sec.nport"):
                    n_nport += 1
                    if n_nport > nport_batches:
                        break
                    apply("nport", batch, profile=(n_nport % 10 == 0))
                else:
                    apply("13f", batch, profile=False)
                batch = []
        if batch and not code.startswith("sec.nport"):
            apply("13f", batch, profile=False)

    out = {"batches": batches, "profiles": profiles}
    Path(os.environ["OUT"]).write_text(json.dumps(out, indent=1) + "\n")
