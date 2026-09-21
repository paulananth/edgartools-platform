"""Ticket 19 resolution criterion: rule C-J can be evaluated from the parser's
own output with zero SEC requests, and reproduces research 18's labelled
corpus (841/841 person, 353/353 entity on the primary corpus).

Runs the production parser (submissions_lookup fed from the bronze
snapshots research 18 synced) over the 5,356 artifacts, maps ONLY the
emitted owner-row columns onto research 18's evidence-row shape, and scores
`rule_combo_j` from 18-classify.py against 18-sample.jsonl by owner_key.
Network is blocked at import.

Usage:
  uv run --extra s3 python 19-classify-from-parser.py --artifacts r18/filing_artifact \
      --submissions r18/submissions --sample 18-sample.jsonl --out 19-classify-from-parser.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import sys
from collections import Counter


def _no_network(*_a, **_k):
    raise AssertionError("network is blocked in this harness")


socket.socket.connect = _no_network  # type: ignore[method-assign]

HERE = os.path.dirname(os.path.abspath(__file__))


def load_r18():
    spec = importlib.util.spec_from_file_location("r18", os.path.join(HERE, "18-classify.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def evidence_row_from_parser(owner: dict, accession: str) -> dict:
    """Research 18's rule inputs, built from parser columns only."""
    name = owner["owner_name_raw"]
    return {
        "accession": accession,
        "owner_index": owner["owner_index"],
        "owner_cik": owner["owner_cik"],
        "owner_name": name,
        "sub_present": owner["owner_submissions_present"],
        "entity_type": owner["owner_entity_type"],
        "sic": owner["owner_sic"],
        "state_of_incorporation": owner["owner_state_of_incorporation"],
        "ein": owner["owner_ein"],
        "n_tickers": owner["owner_ticker_count"],
        "owner_org": owner["owner_org"],
        "fiscal_year_end": owner["owner_fiscal_year_end"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifacts", required=True)
    ap.add_argument("--submissions", required=True)
    ap.add_argument("--sample", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    r18 = load_r18()
    from edgar_warehouse.parsers import ownership as parser

    sub_cache: dict[int, dict | None] = {}
    lookups = Counter()

    def submissions(cik: int) -> dict | None:
        lookups["calls"] += 1
        if cik not in sub_cache:
            p = os.path.join(args.submissions, f"{cik}.json")
            sub_cache[cik] = json.load(open(p)) if os.path.exists(p) else None
        return sub_cache[cik]

    rows: list[dict] = []
    multi_owner = []
    for f in sorted(os.listdir(args.artifacts)):
        content = open(os.path.join(args.artifacts, f), "rb").read().decode("utf-8", errors="replace")
        parsed = parser.parse_ownership(f, content, "4", submissions_lookup=submissions)
        owners = parsed["sec_ownership_reporting_owner"]
        for o in owners:
            r = evidence_row_from_parser(o, f)
            r["entity_tokens"] = r18.entity_tokens(r["owner_name"])
            r["has_entity_token"] = bool(r["entity_tokens"])
            r["has_unambiguous_token"] = bool(set(r["entity_tokens"]) - r18.AMBIGUOUS_TOKENS)
            r["person_name_shape"] = r18.person_name_shape(r["owner_name"])
            rows.append(r)
        if len(owners) > 1:
            txns = parsed["sec_ownership_non_derivative_txn"] + parsed["sec_ownership_derivative_txn"]
            multi_owner.append({
                "artifact": f, "owners": len(owners),
                "txn_rows": len(txns),
                "all_owner_index_1": all(t["owner_index"] == 1 for t in txns),
                "all_count_marked": all(t["reporting_owner_count"] == len(owners) for t in txns),
                "nature_texts": sorted({t["ownership_nature"] for t in txns if t["ownership_nature"]})[:3],
            })

    rep_rows: dict[str, dict] = {}
    for r in rows:
        k = r18.owner_key(r)
        cur = rep_rows.get(k)
        if cur is None or (r["accession"], r["owner_index"]) < (cur["accession"], cur["owner_index"]):
            rep_rows[k] = r

    sample = [json.loads(line) for line in open(args.sample)]
    labeled = [s for s in sample if s.get("label") in ("person", "entity")]
    rec = {"decided_person": 0, "person_correct": 0, "decided_entity": 0, "entity_correct": 0,
           "deferred": 0, "missing_owner": 0, "errors": []}
    for s in labeled:
        r = rep_rows.get(s["owner_key"])
        if r is None:
            rec["missing_owner"] += 1
            continue
        v = r18.rule_combo_j(r)
        if v == "person":
            rec["decided_person"] += 1
            if s["label"] == "person":
                rec["person_correct"] += 1
            else:
                rec["errors"].append({"key": s["owner_key"], "name": s["owner_name"], "decided": v, "label": s["label"]})
        elif v == "entity":
            rec["decided_entity"] += 1
            if s["label"] == "entity":
                rec["entity_correct"] += 1
            else:
                rec["errors"].append({"key": s["owner_key"], "name": s["owner_name"], "decided": v, "label": s["label"]})
        else:
            rec["deferred"] += 1
    p, lo, _ = r18.wilson(rec["person_correct"], rec["decided_person"]) if rec["decided_person"] else (None, None, None)
    rec["person_precision"], rec["person_wilson_lcb95"] = p, lo
    p, lo, _ = r18.wilson(rec["entity_correct"], rec["decided_entity"]) if rec["decided_entity"] else (None, None, None)
    rec["entity_precision"], rec["entity_wilson_lcb95"] = p, lo

    population = Counter(r18.rule_combo_j(r) for r in rep_rows.values())
    out = {
        "owner_rows": len(rows),
        "distinct_owners": len(rep_rows),
        "submissions_lookup_calls": lookups["calls"],
        "sec_requests": 0,
        "labeled_owners": len(labeled),
        "rule_c_j_on_parser_output": rec,
        "population_verdicts_owners": dict(population),
        "multi_owner_filings": len(multi_owner),
        "multi_owner_all_txn_owner_index_1": all(m["all_owner_index_1"] for m in multi_owner),
        "multi_owner_all_txn_count_marked": all(m["all_count_marked"] for m in multi_owner),
        "multi_owner_examples": multi_owner[:5],
    }
    json.dump(out, open(args.out, "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in out.items() if k != "multi_owner_examples"}, indent=1, default=str))


if __name__ == "__main__":
    main()
