"""Ticket 07: the Proving Run of the Form ADV rules (iapd.adv) on a cohort.

A disposable PostgreSQL 16 (pgserver), migrated as the Clean MDM tests do; the
repo's Company policy from a rules folder, with the three Form ADV binding
rules switched on in a **copy** only, each Identifier Contract stamped
`approved_by: proving-run` ("Proving Run only; not an approval"); the two
Form ADV Dataset Contracts registered with the test Rules authority.

The cohort: advisers (CRD) with custody rows in at least two filings, chosen
by the sha256 of their CRD, so the list is fixed; every filing of theirs in
the 13 months and every custody row of those filings. Each month's records are
applied in month order, dated by the file's month end (what mdm.prepare's
`effective_column` gives them), filings first. Then everything again: the
second pass must change nothing.

The change test: for each adviser and custodian (by LEI, else BD number), the
expected first and last filing month that names it, from the source rows,
against MDM's CUSTODIAN links (first stated, last_seen).

    cd <a worktree with the code>   # needs declared Identifier Contract namespaces
    uv run --no-sync --with pgserver python <this file> <rules root> <readings folder> <out folder> [advisers]

<readings folder> is read_all.py's output.
"""
from __future__ import annotations

import copy
import os
import hashlib
import json
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text

from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, digest, register_policy
from edgar_warehouse.rules import files
from tests.integration import test_clean_mdm_postgres as core
from tests.support.rules_authority import register_dataset

FILINGS, CUSTODY = "iapd.adv.filings.v1", "iapd.adv.custody.v1"
RULES = ["iapd-adv-crd", "iapd-adv-custodian-lei", "iapd-adv-custodian-bd"]
AS_OF = "2026-10-09T15:00:00+00:00"
BATCH = int(os.environ.get("BATCH", "500"))


def cohort(readings: Path, size: int) -> tuple[dict, dict]:
    """{month: filings rows}, {month: custody rows} for the chosen advisers."""
    filings = {m.name: json.loads((m / "filings.json").read_text()) for m in sorted(readings.iterdir())}
    custody = {m.name: json.loads((m / "custody.json").read_text()) for m in sorted(readings.iterdir())}
    with_custody = {r["filing_id"] for rows in custody.values() for r in rows}
    per_crd = Counter(r["crd"] for rows in filings.values() for r in rows if r["filing_id"] in with_custody)
    eligible = sorted((c for c, n in per_crd.items() if n >= 2), key=lambda c: hashlib.sha256(c.encode()).hexdigest())
    chosen = set(eligible[:size])
    keep = {r["filing_id"] for rows in filings.values() for r in rows if r["crd"] in chosen}
    return ({m: [r for r in rows if r["filing_id"] in keep] for m, rows in filings.items()},
            {m: [r for r in rows if r["filing_id"] in keep] for m, rows in custody.items()})


def proving_policy(root: Path, corpus: str) -> dict:
    body = copy.deepcopy(files.policy(root=root))
    company = body["kinds"]["company"]
    for namespace in ("crd", "lei", "bd_number"):
        company["identifiers"][namespace]["verification"] = {
            "corpus_sha256": corpus, "approved_by": "proving-run", "approved_at": "2026-10-09T15:00:00Z",
            "reason": "Proving Run only; not an approval"}
    versions = {r["rule_id"]: r["version"] for r in company["rules"]}
    body["automatic_rules"] = [*body["automatic_rules"], *[
        {"kind": "company", "family": "binding", "rule_id": r, "rule_version": versions[r],
         "verdict": "bind", "activation": "deterministic"} for r in RULES]]
    return body


def assertions(code: str, contract: dict, rows: list[dict], month: str) -> tuple[list[dict], Counter]:
    publication = {"publication_key": f"{code}:{month}", "revision": 1, "effective_at": rows[0]["published"],
                   "artifact_sha256": hashlib.sha256(month.encode()).hexdigest(), "member": month}
    found, deferred = [], Counter()
    for row in rows:
        try:
            found.append(normalize(row, source_code=code, contract=contract, publication=publication))
        except UnsupportedRecord as exc:
            deferred[exc.reason] += 1
    return found, deferred


def counts(conn) -> dict:
    one = lambda sql: conn.execute(text(sql)).scalar()
    group = lambda sql: {str(k): v for k, v in conn.execute(text(sql)).all()}
    return {
        "companies_open": one("SELECT count(*) FROM mdm.current_entity WHERE kind='company' AND status<>'alias'"),
        "stage_records": group("SELECT source_code, count(*) FROM mdm.stage_record GROUP BY 1"),
        "stage_bound": group("SELECT source_code, count(*) FROM mdm.stage_record WHERE entity_id IS NOT NULL GROUP BY 1"),
        "open_reviews": group("SELECT coalesce(body->>'reason','(none)'), count(*) FROM mdm.current_record "
                              "WHERE object_type='review' AND body->'open'='true'::jsonb GROUP BY 1"),
        "decisions_by_rule": group("SELECT coalesce(body->>'rule_id', body->'rule'->>'rule_id', '(none)'), count(*) "
                                   "FROM mdm.decision GROUP BY 1"),
        "custodian_links": one("SELECT count(*) FROM mdm.current_record WHERE object_type='relationship' "
                               "AND body->>'type'='CUSTODIAN'"),
    }


def expected_links(filings: dict, custody: dict) -> dict:
    """(crd, custodian id) -> (first month, last month) naming it, for identified custodians."""
    crd = {r["filing_id"]: r["crd"] for rows in filings.values() for r in rows}
    seen = defaultdict(list)
    for month, rows in custody.items():
        for r in rows:
            ident = (f"lei:{r['lei']}" if r["lei"] else None) or (f"bd:{r['bd_number']}" if r["bd_number"] else None)
            if ident:
                seen[(crd[r["filing_id"]], ident)].append(month)
    return {k: (min(v), max(v)) for k, v in seen.items()}


def month(instant: str | None) -> str:
    """The New York month of a stored instant (MDM keeps them in UTC)."""
    return datetime.fromisoformat(instant).astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m") if instant else ""


def mdm_links(conn) -> dict:
    """(crd, custodian id) -> (first stated, last stated) months, from MDM."""
    ids = defaultdict(set)
    for entity, source, crd, lei, bd in conn.execute(text(
            "SELECT entity_id::text, source_code, reading->'identifiers'->>'crd', reading->'identifiers'->>'lei', "
            "reading->'identifiers'->>'bd_number' FROM mdm.stage_record WHERE entity_id IS NOT NULL")):
        if source == FILINGS and crd:
            ids[entity].add(("crd", crd))
        if source == CUSTODY:
            ids[entity].add(("custodian", f"lei:{lei}" if lei else f"bd:{bd}"))
    found = {}
    for body, in conn.execute(text("SELECT body FROM mdm.current_record WHERE object_type='relationship' "
                                   "AND body->>'type'='CUSTODIAN'")):
        crds = {v for k, v in ids[body["source_id"]] if k == "crd"}
        custodians = {v for k, v in ids[body["target_id"]] if k == "custodian"}
        starts = [p["valid_from"] for p in body["periods"]]
        for c in crds:
            for t in custodians:
                found[(c, t)] = (month(min(starts)), month(body.get("last_seen")), len(body["periods"]))
    return found


def main(root: Path, readings: Path, out: Path, size: int) -> None:
    out.mkdir(parents=True, exist_ok=True)
    filings, custody = cohort(readings, size)
    corpus = digest({"filings": filings, "custody": custody})
    print(json.dumps({"advisers": size, "filings": sum(map(len, filings.values())),
                      "custody_rows": sum(map(len, custody.values())), "corpus_sha256": corpus}), flush=True)
    import pgserver
    server = pgserver.get_server(tempfile.mkdtemp(prefix="adv-proving-"), cleanup_mode="stop")
    admin = create_engine(server.get_uri().replace("postgresql://", "postgresql+psycopg2://"))
    with admin.begin() as conn:
        conn.execute(text("CREATE ROLE clean_application LOGIN PASSWORD 'test' NOSUPERUSER NOCREATEDB NOCREATEROLE"))
    app = create_engine(admin.url.set(username="clean_application", password="test"))
    built = core.initialize_database(admin, app)
    policy_body = proving_policy(root, corpus)
    contracts = {code: files.mdm_contract("iapd.adv", code, root=root) for code in (FILINGS, CUSTODY)}
    # Blocker checks (ticket 07): NO_LINKS drops the custody links, FILINGS_ONLY
    # loads adviser filings alone; CLOSURE_LIMIT lowers the Merge Stage's bound.
    if os.environ.get("NO_LINKS"):
        contracts[CUSTODY]["adapter"].pop("relationships")
    if os.environ.get("FILINGS_ONLY"):
        custody = {m: [] for m in custody}
    with admin.begin() as conn:
        for code, contract in contracts.items():
            register_dataset(conn, code, built.registry, contract)
        policy = register_policy(conn, policy_body)
    stage = MergeStage(Store(app), closure_limit=int(os.environ.get("CLOSURE_LIMIT", "10000")))
    checkpoint, timings, deferred = 0, [], Counter()

    def apply_all(tag: str) -> None:
        nonlocal checkpoint
        for month in sorted(filings):
            for code, rows in ((FILINGS, filings[month]), (CUSTODY, custody[month])):
                if not rows:
                    continue
                found, skipped = assertions(code, contracts[code], rows, month)
                deferred.update({f"{tag}:{code}:{k}": v for k, v in skipped.items()})
                for i in range(0, len(found), BATCH):
                    started = time.monotonic()
                    stage.apply(batch_id=f"{tag}-{code}-{month}-{i}", run_id=str(uuid4()), policy_digest=policy,
                                consumer="adv-proving", expected_checkpoint=checkpoint, checkpoint=checkpoint + 1,
                                as_of=AS_OF, assertions=found[i:i + BATCH])
                    checkpoint += 1
                    timings.append({"batch": f"{tag} {code} {month} {i}", "records": len(found[i:i + BATCH]),
                                    "seconds": round(time.monotonic() - started, 1)})
                    print(json.dumps(timings[-1]), flush=True)

    apply_all("first")
    with app.connect() as conn:
        first, first_links = counts(conn), mdm_links(conn)
    apply_all("second")
    with app.connect() as conn:
        second, second_links = counts(conn), mdm_links(conn)
        sample = [r[0] for r in conn.execute(text(
            "SELECT body FROM mdm.current_record WHERE object_type='relationship' AND body->>'type'='CUSTODIAN' LIMIT 3"))]
    expected = expected_links(filings, custody)
    got = {k: v[:2] for k, v in first_links.items()}
    report = {
        "policy_digest": policy, "corpus_sha256": corpus, "deferred": dict(deferred),
        "after_first": first, "after_second": second, "second_pass_changed_nothing": first == second and first_links == second_links,
        "links_expected": len(expected), "links_in_mdm": len(got),
        "links_matching": sum(got.get(k) == v for k, v in expected.items()),
        "links_missing": sorted(map(list, set(expected) - set(got)))[:10],
        # A custodian known by an LEI in some rows and a BD number in others is
        # one Company holding both: its links show under both ids.
        "links_extra": sorted(map(list, set(got) - set(expected)))[:10],
        "links_differing": [[*k, expected[k], got[k]] for k in expected if k in got and got[k] != expected[k]][:10],
        "links_with_more_than_one_period": sum(v[2] > 1 for v in first_links.values()),
        "custodian_dropped_by_adviser": len({k[0] for k, v in expected.items()
                                             if v[1] < max(m for m, rows in filings.items()
                                                           for r in rows if r["crd"] == k[0])}),
        "sample_links": sample, "seconds": round(sum(t["seconds"] for t in timings), 1),
    }
    (out / "report.json").write_text(json.dumps(report, indent=1, default=str) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "sample_links"}, indent=1, default=str))
    server.cleanup()


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 300)
