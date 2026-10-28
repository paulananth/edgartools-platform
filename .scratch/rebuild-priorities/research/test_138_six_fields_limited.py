"""Ticket 138: the limited test before N-PORT's six Security facts switch on (operator,
2026-10-28: "Switch on with minimal testing no multi hours testing"). Counts only.

A slice of the real 2026 Q2 quarter (seed 138): every holding of 300 CUSIPs and
50 ISIN-only holdings (identifiers passing their checks), with their ISINs and filings, through N-PORT's configured
chain (source.yaml, reduce.yaml, combine.yaml, record.yaml, the Dataset Contract)
into a disposable MDM, twice. Writes 138_six_fields_limited_test.json beside it.

Run from the repo root:
  CI=true uv run --no-sync pytest -q -p tests.integration.conftest \
    .scratch/rebuild-priorities/research/test_138_six_fields_limited.py
"""
from __future__ import annotations

import collections
import csv
import io
import json
import os
import random
import sys
import time
import zipfile
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean.identifier_types import TYPES
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, register_policy
from edgar_warehouse.rules import files
from tests.integration import test_clean_mdm_postgres as core
from tests.integration import test_nport_link_start as chain
from tests.support.rules_authority import register_dataset

QUARTER = Path(os.path.expanduser(
    "~/.local/share/edgartools/clean-mdm/captures/sec.nport-datasets/2026q2/2026q2_nport.zip"))
OUT = Path(__file__).with_name("138_six_fields_limited_test.json")
FACTS = ("asset_category", "issuer_type", "investment_country", "currency", "restricted", "derivative_category")


def rows(z, member):
    with z.open(member) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, "utf-8", errors="replace"), delimiter="\t")


def tsv(header, items):
    out = io.StringIO()
    w = csv.DictWriter(out, header, delimiter="\t", lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    w.writerows(items)
    return out.getvalue()


def slice_zip(root: Path) -> tuple[bytes, list[list[str]]]:
    with zipfile.ZipFile(QUARTER) as z:
        isin_of = collections.defaultdict(set)
        for r in rows(z, "IDENTIFIERS.tsv"):
            if (r.get("IDENTIFIER_ISIN") or "").strip():
                isin_of[r["HOLDING_ID"]].add(r["IDENTIFIER_ISIN"].strip())
        holdings, header = [], None
        for r in rows(z, "FUND_REPORTED_HOLDING.tsv"):
            header = header or list(r)
            holdings.append(r)
        # Identifiers that pass their checks only: the real run sets the others
        # aside with their reasons, which this helper refuses (the six facts are the test).
        cusips = sorted(c for c in {(r.get("ISSUER_CUSIP") or "").strip().upper() for r in holdings}
                        - {"", "000000000", "999999999"} if TYPES["cusip"].refusal(c)[1] is None)
        rng = random.Random(138)
        chosen = set(rng.sample(cusips, 300))
        isin_only = [r["HOLDING_ID"] for r in holdings
                     if (r.get("ISSUER_CUSIP") or "").strip().upper() in ("", "000000000", "999999999")
                     and len(isin_of.get(r["HOLDING_ID"], ())) == 1
                     and TYPES["isin"].refusal(next(iter(isin_of[r["HOLDING_ID"]])))[1] is None]
        isin_only = set(rng.sample(sorted(isin_only), 50))
        kept = [r for r in holdings if (r.get("ISSUER_CUSIP") or "").strip().upper() in chosen
                or r["HOLDING_ID"] in isin_only]
        ids = {r["HOLDING_ID"] for r in kept}
        accessions = {r["ACCESSION_NUMBER"] for r in kept}
        submissions = [r for r in rows(z, "SUBMISSION.tsv") if r["ACCESSION_NUMBER"] in accessions]
        sub_header = list(submissions[0])
    pairs = [[h, i] for h in sorted(ids) for i in sorted(isin_of.get(h, ())) if TYPES["isin"].refusal(i)[1] is None]
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as z:
        z.writestr("FUND_REPORTED_HOLDING.tsv", tsv(header, kept))
        z.writestr("IDENTIFIERS.tsv", tsv(["HOLDING_ID", "IDENTIFIER_ISIN"],
                                          [{"HOLDING_ID": h, "IDENTIFIER_ISIN": i} for h, i in pairs]))
        z.writestr("SUBMISSION.tsv", tsv(sub_header, submissions))
    return body.getvalue(), pairs, len(kept)


def records(root: Path):
    data, pairs, holdings = slice_zip(root)
    store = Artifacts()
    root.mkdir(parents=True, exist_ok=True)
    raw = store.put_bytes((root / "capture.zip").as_uri(), data)
    read = chain.read(store, root / "holdings", "source.yaml", raw, chain.Q2, lookups={"isin": pairs})
    issuers = chain.issuers(store, root, raw, pairs, chain.Q2)
    return chain.security_records(store, root, read, issuers, batch_id="limited"), holdings


def stated(field) -> bool:
    return isinstance(field, dict) and field.get("op") == "value"


def securities(database) -> dict:
    return {k: b for k, b in core.documents(database, "entity").items() if b.get("kind") == "security"}


def test_the_six_facts_reach_the_securities_and_a_second_pass_changes_nothing(database, tmp_path):
    began = time.monotonic()
    step = lambda what: print(f"{what}: {time.monotonic() - began:.0f} s", file=sys.stderr, flush=True)
    found, holdings = records(tmp_path)
    step(f"records {len(found)}")
    with database.admin.begin() as conn:
        register_dataset(conn, chain.CODE, database.registry, files.mdm_contract(chain.NAME, chain.CODE))
        policy = register_policy(conn, files.policy())
    stage = MergeStage(Store(database.application))
    # Batches of 250, as a run's merge takes them; the second pass repeats them.
    batches = [found[i:i + 250] for i in range(0, len(found), 250)]
    checkpoint = 0
    for name in ("first", "again"):
        for number, batch in enumerate(batches):
            checkpoint += 1
            chain.apply(stage, policy, f"{name}-{number}", batch, checkpoint)
        step(f"pass {name}")
        if name == "first":
            first = securities(database)
    again = securities(database)
    held = collections.defaultdict(set)
    for entity, body in first.items():
        for namespace, values in (body.get("identifiers") or {}).items():
            for value in values if isinstance(values, list) else [values]:
                held[(namespace, json.dumps(value, sort_keys=True))].add(entity)
    reviews = collections.Counter(b["reason"] for b in core.documents(database, "review").values() if b.get("open"))
    report = {
        "kind": "limited test before the switch-on (operator, 2026-10-28: \"Switch on with minimal testing no multi hours testing\")",
        "slice": {"holdings": holdings, "cusips_sampled": 300, "isin_only_holdings_sampled": 50, "seed": 138},
        "records": len(found),
        "records_stating_each_fact": {f: sum(1 for r in found if stated(r["fields"].get(f))) for f in FACTS},
        "securities": len(first),
        "securities_holding_each_fact": {f: sum(1 for b in first.values() if (b.get("fields") or {}).get(f) not in (None, "")) for f in FACTS},
        "identifiers_on_two_or_more_securities": sum(1 for v in held.values() if len(v) > 1),
        "open_reviews": dict(reviews),
        "second_pass_changed": first != again,
    }
    OUT.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    assert report["identifiers_on_two_or_more_securities"] == 0
    assert not report["second_pass_changed"]
    assert all(report["records_stating_each_fact"][f] > 0 for f in FACTS[:5])
