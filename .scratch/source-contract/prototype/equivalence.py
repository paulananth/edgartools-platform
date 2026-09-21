"""PROTOTYPE — the Form 3/4/5 Source Contract vs edgar_warehouse/parsers/ownership.py.

Every artifact in the local bronze copy is parsed both ways, with the same
bronze submissions lookup. Differences are classified against
expected-differences.md (written before this ran). Output: equivalence.json.
"""

from __future__ import annotations

import collections
import glob
import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

PROTO = Path(__file__).resolve().parent
sys.path.insert(0, str(PROTO / "engine"))
R18 = os.environ["R18"]
IGNORED = {"parser_version"}                                       # expected difference 1
VALUE_TEXT = {"transaction_shares", "transaction_price", "shares_owned_after", "acquired_disposed_code",
              "ownership_direct_indirect", "ownership_nature"}      # expected difference 2

_engine = None


def _lookup(cik):
    p = f"{R18}/submissions/{cik}.json"
    if not os.path.exists(p):
        return None
    raw = open(p, "rb").read()
    d = json.loads(raw)
    d["_bronze_sha256"] = hashlib.sha256(raw).hexdigest()
    return d


def work(paths):
    global _engine
    import source_engine as se
    from edgar_warehouse.parsers import ownership as oracle
    if _engine is None:
        _engine = se.Engine(PROTO / "sources" / "form345", se.load_families())
        _engine.validate()
    out = []
    for p in paths:
        raw = open(p, "rb").read()
        text = raw.decode("utf-8", errors="replace")
        rec = {"artifact": os.path.basename(p), "diffs": [], "error": None}
        try:
            mine = _engine.parse(raw)
        except se.PathError as e:
            rec["error"] = f"PathError: {e}"
            out.append(rec)
            continue
        acc = next((r["accession_number"] for t in mine.values() for r in t), None) or se._sgml_header(text).get("ACCESSION NUMBER")
        theirs = oracle.parse_ownership(acc, text, "4", submissions_lookup=_lookup)
        for t, rows in theirs.items():
            if len(rows) != len(mine[t]):
                rec["diffs"].append({"table": t, "kind": "row_count", "oracle": len(rows), "contract": len(mine[t])})
                continue
            for i, (a, b) in enumerate(zip(rows, mine[t])):
                for col, av in a.items():
                    if col in IGNORED:
                        continue
                    bv = b.get(col, "<absent>")
                    if av != bv:
                        rec["diffs"].append({"table": t, "row": i, "column": col, "oracle": av, "contract": bv,
                                             "expected": col in VALUE_TEXT})
        out.append(rec)
    return out


def main():
    files = sorted(glob.glob(f"{R18}/filing_artifact/*"))
    chunks = [files[i::8] for i in range(8)]
    results = []
    with ProcessPoolExecutor(8) as ex:
        for part in ex.map(work, chunks):
            results.extend(part)
    errors = [r for r in results if r["error"]]
    diffs = [d | {"artifact": r["artifact"]} for r in results for d in r["diffs"]]
    unexpected = [d for d in diffs if not d.get("expected")]
    by_col = collections.Counter((d["table"], d.get("column", d["kind"]), d.get("expected", False)) for d in diffs)
    summary = {
        "artifacts": len(results),
        "artifacts_identical": sum(1 for r in results if not r["diffs"] and not r["error"]),
        "path_errors": len(errors),
        "path_error_samples": errors[:10],
        "differences": len(diffs),
        "unexpected_differences": len(unexpected),
        "by_column": [{"table": t, "column": c, "expected": e, "count": n} for (t, c, e), n in by_col.most_common()],
        "unexpected_samples": unexpected[:25],
        "expected_samples": [d for d in diffs if d.get("expected")][:10],
    }
    (PROTO / "equivalence.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps({k: v for k, v in summary.items() if not k.endswith("samples")}, indent=1, default=str))


if __name__ == "__main__":
    main()
