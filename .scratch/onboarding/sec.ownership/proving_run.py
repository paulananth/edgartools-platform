"""SEC ownership, the owner's Dataset Contract: its Proving Run (profiling ticket 07).

Every Form 3, 4 and 5 filing in the local copies (p07, 8,723 filings) is read
through the approved source extracts (`rules/sources/sec.ownership/`), and each
reporting owner row through `sec.ownership.reporting_owner.v1` and the repo's
merge rules. The issuers are the Companies of the cm27 cohort that the filings
name (prepared Company records, `sec.submissions.company.v1`). Both are applied
by the Merge Stage on a disposable PostgreSQL 16 (the MDM test fixtures); the
container is removed afterwards. Zero requests leave the machine.

The ownership rules (`sec-ownership-person`, `sec-ownership-person-cik`) are
switched on here as a **Proving Run activation** only: stamped "proving-run" in
a copy of the policy in the disposable database. Then everything is applied
again; the second pass must change nothing. The report holds counts only.

    PROVING_WORK=~/.local/share/edgartools/clean-mdm/proving/ownership \\
    uv run --no-sync pytest -q -s -p no:randomly .scratch/onboarding/sec.ownership/proving_run.py
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sqlalchemy import text

from edgar_warehouse.mdm.clean.activation import wilson_lower_bound
from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
from edgar_warehouse.mdm.clean.evidence import deferred_record
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, canonical, register_policy
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine
from tests.integration import test_clean_mdm_postgres as core
from tests.support.rules_authority import register_dataset

postgres = core.postgres
database = core.database

LOCAL = Path.home() / ".local/share/edgartools/clean-mdm"
OWNERSHIP = LOCAL / "proving/p07/inputs/warehouse/bronze"
COMPANIES = LOCAL / "proving/cm27/bundles"
OWNER, COMPANY = "sec.ownership.reporting_owner.v1", "sec.submissions.company.v1"
AS_OF = "2026-10-13T00:00:00+00:00"
MAX_RECORDS, MAX_BYTES = 1000, 12 * 1024 * 1024
MEASURED = Path(__file__).with_name("measure.json")

def bound(n: int) -> float:
    """The Wilson lower bound of n correct of n, rounded down as the policy checks it."""
    return math.floor(wilson_lower_bound(n, n, 0.975) * 1e6) / 1e6

def proof(approval: dict) -> dict:
    measured = json.loads(MEASURED.read_text())
    n = measured["person_owners_by_label"]["person"]
    steps = {step: {"n": c["person"], "correct": c["person"], "lower_bound": bound(c["person"])}
             for step, c in measured["person_owners_by_step"].items()}
    sha = hashlib.sha256(MEASURED.read_bytes()).hexdigest()
    return {"method": "wilson_lower_bound", "one_sided_confidence": 0.975, "n": n, "correct": n,
            "lower_bound": bound(n),
            "adversarial": {"fixture_sha256": sha, **measured["adversarial"]},
            "cohort": {"by_step": steps, "files": {"measure.json": sha}}, **approval}

def proving_policy(approval: dict) -> dict:
    """The repo's merge rules with the two ownership rules switched on for this run."""
    body = files.policy()
    person = body["kinds"]["person"]
    # Main carries the approved verification (#964); a policy without one gets a stand-in.
    person["identifiers"]["cik"].setdefault("verification", {"corpus_sha256": "0" * 64, **approval})
    rules = {r["rule_id"]: r for r in person["rules"]}
    measured = rules["sec-ownership-person"]
    # On main the two rules are switched on (#964); the run adds only what is not.
    active = {(r["kind"], r["family"], r["rule_id"]) for r in body["automatic_rules"]}
    body["automatic_rules"] = [*body["automatic_rules"], *(entry for entry in ({
        "kind": "person", "family": "classification", "rule_id": measured["rule_id"],
        "rule_version": measured["version"], "verdict": "person", "activation": "measured",
        # The measured sample (measure.py, measure.json): the owners the proven rule,
        # run on each owner's own submissions document, also calls a person.
        "proof": proof(approval)}, {
        "kind": "person", "family": "binding", "rule_id": "sec-ownership-person-cik",
        "rule_version": rules["sec-ownership-person-cik"]["version"], "verdict": "bind",
        "activation": "deterministic"}) if (entry["kind"], entry["family"], entry["rule_id"]) not in active)]
    return body

def filings() -> list[tuple[str, dict]]:
    """Each local filing's tables, read by the source extract for its shape."""
    folder = files.ROOT / "sources" / "sec.ownership"
    bare = SourceEngine(files.load(folder / "ownership-xml.yaml"))
    sgml = SourceEngine(files.load(folder / "ownership-sgml.yaml"))
    out = []
    for path in sorted(p for p in OWNERSHIP.rglob("*") if p.is_file() and "iapd_adv_bulk" not in p.parts):
        raw = path.read_bytes()
        if b"ownershipDocument" not in raw:
            continue
        if raw.lstrip().startswith(b"<SEC-DOCUMENT>") or b"<XML>" in raw:
            tables = sgml.read(raw).tables
        else:
            found = re.search(r"\d{10}-\d{2}-\d{6}", str(path))
            tables = bare.read(raw, context={"accession": found.group(0) if found else path.name, "filed": None}).tables
        out.append((hashlib.sha256(raw).hexdigest(), tables))
    return out

def companies(issuers: set[int]) -> list[dict]:
    """The cm27 Companies the filings name as issuers."""
    rows, seen = [], set()
    for records in sorted(COMPANIES.glob("chunk*/records.jsonl")):
        for line in records.open():
            row = json.loads(line)
            cik = int(row.get("cik") or 0)
            if cik in issuers and cik not in seen:
                seen.add(cik)
                rows.append(row)
    return rows

def read(row: dict, source_code: str, contract: dict, policy: dict, publication: dict) -> tuple[str, dict]:
    try:
        return "assertions", normalize(row, source_code=source_code, contract=contract,
                                       publication=publication, policy=policy)
    except UnsupportedRecord as exc:
        return "deferred", deferred_record(
            source_code=source_code, publication_key=publication["publication_key"],
            record_locator=publication["member"], schema_version=contract["schema_version"],
            reason=exc.reason, raw_record=row, probable_kind=exc.probable_kind,
            provenance={"artifact_sha256": publication["artifact_sha256"], "member": publication["member"],
                        "adapter_version": contract["adapter"]["version"], **exc.detail})

def counts(conn) -> dict:
    one = lambda sql: conn.execute(text(sql)).scalar()
    group = lambda sql: {str(k): v for k, v in conn.execute(text(sql)).all()}
    return {
        "identities": group("SELECT kind, count(*) FROM mdm.master_entity GROUP BY kind"),
        "stage_records": group("SELECT kind, count(*) FROM mdm.stage_record GROUP BY 1"),
        "waiting": group("SELECT coalesce(reason,'(none)')||' / '||coalesce(probable_kind,'-'), count(*) "
                         "FROM mdm.stage_waiting GROUP BY 1"),
        "open_reviews": group("SELECT coalesce(body->>'reason','(none)'), count(*) FROM mdm.current_record "
                              "WHERE object_type='review' AND body->'open'='true'::jsonb GROUP BY 1"),
        "relationships": group("SELECT body->>'type' || coalesce(' / ' || (body->>'capacity'), ''), count(*) "
                               "FROM mdm.current_record WHERE object_type='relationship' GROUP BY 1"),
        "decisions": group("SELECT operation, count(*) FROM mdm.decision GROUP BY 1"),
        "relationship_bodies": one("SELECT md5(string_agg(body::text, '|' ORDER BY object_id)) "
                                   "FROM mdm.current_record WHERE object_type='relationship'"),
    }

def ciks_by_kind(conn) -> dict[str, Counter]:
    """How many entities of each kind hold each CIK."""
    out: dict[str, Counter] = {}
    for kind, cik, _ in conn.execute(text(
        "SELECT DISTINCT m.kind, s.reading->'identifiers'->>'cik', s.entity_id FROM mdm.stage_record s "
        "JOIN mdm.master_entity m ON m.entity_id = s.entity_id")).all():
        out.setdefault(kind, Counter())[cik] += 1
    return out

def test_proving_run(database):
    work = Path(os.environ["PROVING_WORK"]).expanduser()
    work.mkdir(parents=True, exist_ok=True)
    approval = {"approved_by": "proving-run",
                "approved_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
                "reason": "SEC ownership Proving Run only; not an approval"}
    body = proving_policy(approval)
    owner_contract = files.mdm_contract("sec.ownership", OWNER)
    company_contract = files.mdm_contract("sec.submissions.company", COMPANY)
    with database.admin.begin() as conn:
        for code, contract in ((COMPANY, company_contract), (OWNER, owner_contract)):
            register_dataset(conn, code, database.registry, contract)
        policy = register_policy(conn, copy.deepcopy(body))
    stage = MergeStage(Store(database.application))

    started = time.monotonic()
    read_filings = filings()
    issuers = {int(t["ownership_document"][0]["issuer_cik"]) for _, t in read_filings}
    issuer_rows = companies(issuers)
    read_seconds = round(time.monotonic() - started, 1)
    timings, read_counts = [], Counter()

    def records(tag: str):
        """Companies first, so each owner's links find their issuer."""
        for row in issuer_rows:
            member = f"cm27/cik={row['cik']}"
            sha = hashlib.sha256(canonical(row).encode()).hexdigest()
            yield COMPANY, read(row, COMPANY, company_contract, body,
                                {"publication_key": f"{member}@{sha}", "revision": 1,
                                 "artifact_sha256": sha, "member": member, "record_locator": member})
        for sha, tables in read_filings:
            for row in tables["reporting_owner"]:
                member = f"{row['accession']}#{row['position']}"
                kind, record = read(row, OWNER, owner_contract, body,
                                    {"publication_key": f"{row['accession']}@{sha}", "revision": 1,
                                     "artifact_sha256": sha, "member": member, "record_locator": member})
                if tag == "first":
                    read_counts[kind if kind == "assertions" else f"deferred: {record['reason']}"] += 1
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
            stage.apply(batch_id=f"ownership-{tag}-{n}", run_id=str(uuid4()), policy_digest=policy,
                        consumer="ownership-proving", expected_checkpoint=checkpoint - 1,
                        checkpoint=checkpoint, as_of=AS_OF, **{key: list(batch)})
            timings.append({"batch": f"{tag}-{n}", key: len(batch), "seconds": round(time.monotonic() - begun, 1)})
            checkpoint += 1
            batch.clear()
            size[0] = 0

        # Every reading first, then every set-aside record (person feed 1's finding:
        # interleaved, each batch is slower than the last).
        for wanted in ("assertions", "deferred"):
            source = None
            for code, (kind, record) in records(tag):
                if kind != wanted:
                    continue
                if code != source:
                    flush(wanted)  # one source a batch
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
        after_first, first_ciks = counts(conn), ciks_by_kind(conn)
    begun = time.monotonic()
    apply_all("second", nxt)
    second_seconds = round(time.monotonic() - begun, 1)
    with database.application.connect() as conn:
        after_second, second_ciks = counts(conn), ciks_by_kind(conn)

    person, company = first_ciks.get("person", Counter()), first_ciks.get("company", Counter())
    report = {
        "run": "SEC ownership, Proving Run of sec.ownership.reporting_owner.v1",
        "policy_digest": policy,
        "filings": len(read_filings), "issuers": len(issuers), "issuer_companies_in_cm27": len(issuer_rows),
        "read": dict(read_counts),
        "after_first_pass": after_first,
        "after_second_pass": after_second,
        "second_pass_changed_nothing": after_first == after_second and first_ciks == second_ciks,
        "persons_by_cik": len(person),
        "cik_on_two_persons": sum(1 for n in person.values() if n > 1),
        "cik_both_person_and_company": len(set(person) & set(company)),
        "seconds": {"read": read_seconds, "first_pass": first_seconds, "second_pass": second_seconds},
        "batches": len(timings),
        "slowest_batch_seconds": max((t["seconds"] for t in timings), default=0),
    }
    (work / "report.json").write_text(json.dumps(report, sort_keys=True, indent=1, default=str) + "\n")
    print(json.dumps(report, indent=1, default=str))
    assert report["second_pass_changed_nothing"]
