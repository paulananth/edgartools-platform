"""Ticket 19: prove the direct-XML ownership parser reproduces the edgartools-
backed parser it replaces on every pre-existing column, over the research 18
bronze corpus (5,356 Form 3/4/5 artifacts, 5,743 owner rows), with zero
network.

The old parser (PARSER_VERSION 2, saved from git as ownership_v2.py) called
edgartools' Entity(cik).data.is_company live. Here that lookup is fed the
same bronze submissions.json the new parser reads -- but through edgartools'
OWN parse_entity_submissions/EntityData path, so the comparison checks the
new parser's _is_company reimplementation against edgartools' real one, not
against itself.

Usage:
  uv run --extra s3 python 19-equivalence.py --old ownership_v2.py \
      --artifacts r18/filing_artifact --submissions r18/submissions --out 19-equivalence.json
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


def load_old(path: str):
    spec = importlib.util.spec_from_file_location("ownership_v2", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--artifacts", required=True)
    ap.add_argument("--submissions", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    from edgar.entity.data import create_default_entity_data, parse_entity_submissions
    from edgar.ownership import ownershipforms
    from edgar_warehouse.parsers import ownership as new

    sub_cache: dict[int, dict | None] = {}

    def submissions(cik: int) -> dict | None:
        if cik not in sub_cache:
            p = os.path.join(args.submissions, f"{cik}.json")
            sub_cache[cik] = json.load(open(p)) if os.path.exists(p) else None
        return sub_cache[cik]

    class BronzeEntity:
        """Stands in for edgar.entity.Entity: same .data, no HTTP."""

        def __init__(self, cik):
            self.cik = int(cik)

        @property
        def data(self):
            payload = submissions(self.cik)
            if payload is None:
                d = create_default_entity_data(self.cik)
                d._not_found = True
                return d
            return parse_entity_submissions(payload)

    ownershipforms.Entity = BronzeEntity  # the old parser's only network path
    old = load_old(args.old)

    files = sorted(os.listdir(args.artifacts))
    if args.limit:
        files = files[: args.limit]

    tables = ("sec_ownership_reporting_owner", "sec_ownership_non_derivative_txn", "sec_ownership_derivative_txn")
    stats = {t: Counter() for t in tables}
    diff_examples: dict[str, list] = {}
    old_errors = new_errors = 0
    row_counts = {t: [0, 0] for t in tables}
    new_only_cols: dict[str, set] = {t: set() for t in tables}
    numeric_recovered = Counter()
    lookup_calls = Counter()

    def counting_lookup(cik: int):
        lookup_calls["calls"] += 1
        return submissions(cik)

    for n, f in enumerate(files, 1):
        content = open(os.path.join(args.artifacts, f), "rb").read().decode("utf-8", errors="replace")
        acc = f
        try:
            o = old.parse_ownership(acc, content, "4")
        except Exception as exc:  # noqa: BLE001
            old_errors += 1
            o = None
        try:
            w = new.parse_ownership(acc, content, "4", submissions_lookup=counting_lookup)
        except Exception as exc:  # noqa: BLE001
            new_errors += 1
            print("NEW ERROR", f, repr(exc)[:200], file=sys.stderr)
            w = None
        if o is None or w is None:
            continue
        for t in tables:
            orows, wrows = o[t], w[t]
            row_counts[t][0] += len(orows)
            row_counts[t][1] += len(wrows)
            if len(orows) != len(wrows):
                stats[t]["ROWCOUNT_DIFF"] += 1
                diff_examples.setdefault(f"{t}.ROWCOUNT", []).append((f, len(orows), len(wrows)))
                continue
            for orow, wrow in zip(orows, wrows):
                new_only_cols[t] |= set(wrow) - set(orow)
                for col in orow:
                    if col == "parser_version":
                        continue
                    ov, wv = orow.get(col), wrow.get(col)
                    if ov == wv:
                        stats[t]["same"] += 1
                        continue
                    # numeric field where the old parser lost the value to a footnote marker
                    if ov is None and wv is not None and col in (
                        "conversion_or_exercise_price", "underlying_security_shares",
                    ):
                        numeric_recovered[col] += 1
                        continue
                    stats[t][col] += 1
                    ex = diff_examples.setdefault(f"{t}.{col}", [])
                    if len(ex) < 8:
                        ex.append((f, ov, wv))
        if n % 500 == 0:
            print(f"{n}/{len(files)}", file=sys.stderr)

    out = {
        "artifacts": len(files),
        "old_parse_errors": old_errors,
        "new_parse_errors": new_errors,
        "row_counts_old_new": row_counts,
        "column_diffs": {t: dict(c) for t, c in stats.items()},
        "numeric_values_recovered_from_footnoted_fields": dict(numeric_recovered),
        "new_only_columns": {t: sorted(c) for t, c in new_only_cols.items()},
        "submissions_lookup_calls": lookup_calls["calls"],
        "examples": diff_examples,
    }
    json.dump(out, open(args.out, "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in out.items() if k != "examples"}, indent=1, default=str))


if __name__ == "__main__":
    main()
