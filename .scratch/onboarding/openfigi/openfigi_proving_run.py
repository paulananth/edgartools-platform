"""OpenFIGI's two matching rules: the Proving Run on a pinned cohort (ticket 80).

The cohort is every identifier asked in the first 20 answer files of each kind
of the 2026-10-15 capture (id_cusip/00000-00019, id_isin/00000-00019). On a
disposable PostgreSQL 16 (removed afterwards; zero requests), it masters:

1. the N-PORT Securities that hold one of those CUSIPs or ISINs (ticket 79's
   prepared records: CUSIP records, with the ISIN OpenFIGI agrees on, and
   ISIN-only records), through N-PORT's three Security rules;
2. the cohort's OpenFIGI records, prepared by the full configured run
   (`openfigi_run.py`), through `openfigi-security-cusip` and
   `openfigi-security-isin`.

The five rules and the ISIN Identifier Contract's verification are switched on
here only, in a copy of the policy (a Proving Run activation). Then everything
is applied again; the second pass must change nothing. Counts only.

    NPORT_PREPARED=~/edgar-local-tmp/figi-attach OPENFIGI_PREPARED=~/edgar-local-tmp/t80/full \\
    OPENFIGI_CAPTURE=~/.local/share/edgartools/clean-mdm/captures/openfigi/2026q2-nport \\
    PROVING_REPORT=~/edgar-local-tmp/t80/proving.json \\
    .venv/bin/python -m pytest -q -s -p no:randomly .scratch/onboarding/openfigi/openfigi_proving_run.py
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
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, register_policy
from edgar_warehouse.rules import files
from tests.integration.conftest import database, postgres  # noqa: F401
from tests.support.rules_authority import register_dataset

AS_OF = "2026-10-17T00:00:00+00:00"
FILES = 20
NPORT, NPORT_ISIN = "sec.nport.security.v1", "sec.nport.security_isin.v1"
FIGI, FIGI_ISIN = "openfigi.security.v1", "openfigi.security_isin.v1"
RULES = ("nport-security-cusip", "nport-security-isin", "nport-isin-security-isin",
         "openfigi-security-cusip", "openfigi-security-isin")
BATCH = 1000


def proving_policy() -> dict:
    body = copy.deepcopy(files.policy())
    security = body["kinds"]["security"]
    security["identifiers"]["isin"].setdefault("verification", {
        "corpus_sha256": "0" * 64, "approved_by": "proving-run", "approved_at": AS_OF,
        "reason": "Proving Run only; not an approval"})
    for rule_id in RULES:
        rule = next(r for r in security["rules"] if r["rule_id"] == rule_id)
        body["automatic_rules"].append({"kind": "security", "family": "binding", "rule_id": rule_id,
                                        "rule_version": rule["version"], "verdict": "bind",
                                        "activation": "deterministic"})
    return body


def prepared(folder: Path):
    manifest = json.loads((folder / "manifest.json").read_bytes())
    for batch in manifest["batches"]:
        data = batch["input"]
        for n, line in enumerate((folder / data["path"]).read_bytes().splitlines(), 1):
            yield json.loads(line), {**data["publication"], "semantics": "patch", "artifact_sha256": data["sha256"],
                                     "member": data["path"], "record_locator": f"{data['sha256']}:line:{n}"}


def cohort(capture: Path) -> tuple[set[str], set[str], dict]:
    asked, pins = {"id_cusip": set(), "id_isin": set()}, {}
    for kind in asked:
        for number in range(FILES):
            path = capture / kind / f"{number:05d}.request.json"
            pins[f"{kind}/{path.name}"] = hashlib.sha256(path.read_bytes()).hexdigest()
            asked[kind] |= {job["idValue"].upper() for job in json.loads(path.read_bytes())}
    return asked["id_cusip"], asked["id_isin"], pins


def records(code: str, contract: dict, rows, read: Counter) -> list[dict]:
    out = []
    for row, publication in rows:
        try:
            out.append(normalize(row, source_code=code, contract=contract, publication=publication))
            read[f"{code} accepted"] += 1
        except UnsupportedRecord as refused:
            read[f"{code} set aside: {refused.reason}"] += 1
    return out


def counts(conn) -> dict:
    def grouped(sql):
        return {str(k): v for k, v in conn.execute(text(sql)).all()}
    return {
        "securities": conn.scalar(text("SELECT count(*) FROM mdm.current_record WHERE object_type = 'entity' "
                                       "AND body->>'kind' = 'security' AND coalesce(body->>'status', '') <> 'alias'")),
        "bound": grouped("SELECT source_code, count(*) FROM mdm.stage_record WHERE entity_id IS NOT NULL GROUP BY 1"),
        "waiting": grouped("SELECT source_code, count(*) FROM mdm.stage_record WHERE entity_id IS NULL GROUP BY 1"),
        "decisions": grouped("SELECT operation, count(*) FROM mdm.decision GROUP BY 1"),
    }


def held_twice(conn, namespace: str) -> int:
    """Values of an identifier that two Securities hold."""
    return conn.scalar(text(
        "SELECT count(*) FROM (SELECT v FROM mdm.current_record e, "
        "jsonb_array_elements_text(e.body->'identifiers'->:n) v WHERE e.object_type = 'entity' "
        "AND e.body->>'kind' = 'security' AND coalesce(e.body->>'status', '') <> 'alias' "
        "GROUP BY v HAVING count(DISTINCT e.object_id) > 1) t"), {"n": namespace})


def test_proving_run(database):  # noqa: F811
    begun = time.monotonic()
    cusips, isins, pins = cohort(Path(os.environ["OPENFIGI_CAPTURE"]).expanduser())
    nport, figi = Path(os.environ["NPORT_PREPARED"]).expanduser(), Path(os.environ["OPENFIGI_PREPARED"]).expanduser()
    body = proving_policy()
    contracts = {NPORT: files.mdm_contract("sec.nport.security", NPORT),
                 NPORT_ISIN: files.mdm_contract("sec.nport.security", NPORT_ISIN),
                 FIGI: files.mdm_contract("openfigi", FIGI), FIGI_ISIN: files.mdm_contract("openfigi", FIGI_ISIN)}
    read = Counter()
    feeds = [
        (NPORT, records(NPORT, contracts[NPORT]["contract"] if "contract" in contracts[NPORT] else contracts[NPORT],
                        ((r, p) for r, p in prepared(nport / "mdm-security")
                         if r.get("cusip", "").upper() in cusips or (r.get("isin") or "").upper() in isins), read)),
        (NPORT_ISIN, records(NPORT_ISIN, contracts[NPORT_ISIN].get("contract", contracts[NPORT_ISIN]),
                             ((r, p) for r, p in prepared(nport / "mdm-security_isin")
                              if r.get("isin", "").upper() in isins), read)),
        (FIGI, records(FIGI, contracts[FIGI].get("contract", contracts[FIGI]),
                       ((r, p) for r, p in prepared(figi / "cusip" / "mdm") if r["id"] in cusips), read)),
        (FIGI_ISIN, records(FIGI_ISIN, contracts[FIGI_ISIN].get("contract", contracts[FIGI_ISIN]),
                            ((r, p) for r, p in prepared(figi / "isin" / "mdm") if r["id"] in isins), read)),
    ]
    with database.admin.begin() as conn:
        for code, contract in contracts.items():
            register_dataset(conn, code, database.registry, contract)
        policy = register_policy(conn, copy.deepcopy(body))
    stage = MergeStage(Store(database.application))
    prepare_seconds = round(time.monotonic() - begun, 1)

    def apply_all(tag, checkpoint, after=None):
        seconds = []
        for code, assertions in feeds:
            for start in range(0, len(assertions), BATCH):
                began = time.monotonic()
                stage.apply(batch_id=f"openfigi-{tag}-{code}-{start}", run_id=str(uuid4()), policy_digest=policy,
                            consumer="openfigi-proving", expected_checkpoint=checkpoint - 1, checkpoint=checkpoint,
                            as_of=AS_OF, assertions=assertions[start:start + BATCH])
                seconds.append(time.monotonic() - began)
                checkpoint += 1
            if after and code == NPORT_ISIN:
                after()
        return checkpoint, seconds

    def snapshot():
        with database.application.connect() as conn:
            return {**counts(conn), "cusips_on_two_securities": held_twice(conn, "cusip"),
                    "isins_on_two_securities": held_twice(conn, "isin")}

    before_openfigi = {}
    begun = time.monotonic()
    nxt, first_batches = apply_all("first", 1, after=lambda: before_openfigi.update(snapshot()))
    first = {**snapshot(), "seconds": round(time.monotonic() - begun, 1)}
    begun = time.monotonic()
    _, second_batches = apply_all("second", nxt)
    second = {**snapshot(), "seconds": round(time.monotonic() - begun, 1)}
    report = {
        "run": "OpenFIGI's matching rules beside the N-PORT Securities (ticket 80)",
        "cohort": {"files_per_kind": FILES, "cusips_asked": len(cusips), "isins_asked": len(isins),
                   "request_files_sha256": pins},
        "read": dict(sorted(read.items())), "prepare_seconds": prepare_seconds,
        "securities_before_openfigi": before_openfigi["securities"],
        "first": first, "second": second,
        "slowest_batch_seconds": round(max(first_batches + second_batches), 1),
        "second_pass_changed_nothing": {k: v for k, v in first.items() if k != "seconds"}
                                       == {k: v for k, v in second.items() if k != "seconds"},
    }
    out = json.dumps(report, indent=1, sort_keys=True)
    Path(os.environ["PROVING_REPORT"]).expanduser().write_text(out)
    print(out)
    assert report["second_pass_changed_nothing"]
    assert first["securities"] == before_openfigi["securities"]  # OpenFIGI creates no Security
