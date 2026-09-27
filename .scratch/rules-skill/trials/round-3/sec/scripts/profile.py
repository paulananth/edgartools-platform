"""Scratch profiler for the captured SEC submissions + ticker catalog files.

Stands in for `edgar-warehouse rules profile <files>` (not built).
Usage: profile.py <inputs dir> [--sample]
  --sample: only the first, middle and last submissions files, and the first,
  middle and last 50 rows of each catalog.
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(sys.argv[1])
SAMPLE = "--sample" in sys.argv


def lei_ok(v: str) -> bool:
    if not re.fullmatch(r"[A-Z0-9]{18}[0-9]{2}", v):
        return False
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in v)
    return int(digits) % 97 == 1


class Paths:
    """Per path: types, filled count, distinct values, samples."""

    def __init__(self):
        self.n = 0
        self.types = defaultdict(Counter)
        self.filled = Counter()
        self.values = defaultdict(Counter)

    def walk(self, obj, prefix=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                self.walk(v, f"{prefix}.{k}" if prefix else k)
            return
        t = type(obj).__name__
        self.types[prefix][t] += 1
        if isinstance(obj, list):
            if obj:
                self.filled[prefix] += 1
            self.values[prefix][f"<list len={len(obj)}>"] += 1
            for item in obj:
                if isinstance(item, (dict, list)):
                    self.walk(item, prefix + "[]")
                else:
                    self.types[prefix + "[]"][type(item).__name__] += 1
                    self.filled[prefix + "[]"] += item not in (None, "")
                    self.values[prefix + "[]"][repr(item)[:60]] += 1
            return
        if obj not in (None, ""):
            self.filled[prefix] += 1
        self.values[prefix][repr(obj)[:60]] += 1

    def report(self, title, n):
        print(f"\n=== {title}: {n} records ===")
        for p in sorted(self.types):
            vals = self.values[p]
            samples = [v for v, _ in vals.most_common(4)]
            print(
                f"{p:48} types={dict(self.types[p])} filled={self.filled[p]} "
                f"distinct={len(vals)} e.g. {samples}"
            )


def submissions(files):
    top = Paths()
    recent_rows = Paths()
    per_file = []
    for f in files:
        doc = json.loads(f.read_text())
        # zip the parallel arrays in filings.recent into rows
        recent = (doc.get("filings") or {}).get("recent") or {}
        lengths = {k: len(v) for k, v in recent.items() if isinstance(v, list)}
        n = max(lengths.values()) if lengths else 0
        rows = [{k: recent[k][i] if i < len(recent[k]) else None for k in recent} for i in range(n)]
        for r in rows:
            recent_rows.walk(r)
        shallow = dict(doc)
        shallow["filings"] = {
            "recent": f"<{n} rows; column lengths equal={len(set(lengths.values())) <= 1}>",
            "files": doc.get("filings", {}).get("files"),
        }
        top.walk(shallow)
        per_file.append((f, doc, rows))
    return top, recent_rows, per_file


def main():
    t0 = time.time()
    sub_files = sorted((ROOT / "submissions").glob("*.json"))
    if SAMPLE:
        sub_files = [sub_files[0], sub_files[len(sub_files) // 2], sub_files[-1]]
    top, recent, per_file = submissions(sub_files)
    top.report("submissions: one filer per file", len(per_file))
    recent.report("submissions: filings.recent zipped into rows", sum(len(r) for _, _, r in per_file))

    print("\n=== submissions: identifier and key checks ===")
    for f, doc, rows in per_file:
        cik = doc.get("cik")
        name_cik = f.stem.removeprefix("CIK")
        checks = {
            "cik_is_10_digit_text": isinstance(cik, str) and bool(re.fullmatch(r"\d{10}", cik)),
            "cik_equals_filename": cik == name_cik,
            "ein": doc.get("ein"),
            "ein_9_digits": bool(re.fullmatch(r"\d{9}", doc.get("ein") or "")),
            "lei": doc.get("lei"),
            "lei_valid_mod97": lei_ok(doc["lei"]) if isinstance(doc.get("lei"), str) else None,
        }
        acc = [r.get("accessionNumber") for r in rows]
        acc_ok = all(re.fullmatch(r"\d{10}-\d{2}-\d{6}", a or "") for a in acc)
        prefixes = Counter((a or "")[:10] for a in acc)
        own_prefix = prefixes.get(cik, 0)
        checks["accessions_unique"] = len(acc) == len(set(acc))
        checks["accession_format_ok"] = acc_ok
        checks["accession_prefix_own_cik"] = f"{own_prefix}/{len(acc)}"
        checks["accession_prefix_distinct"] = len(prefixes)
        forms = Counter(r.get("form") for r in rows)
        print(
            f"{f.name} type={doc.get('entityType')!r} sic={doc.get('sic')!r} "
            f"name={doc.get('name')!r} tickers={doc.get('tickers')} exch={doc.get('exchanges')} "
            f"cat={doc.get('category')!r} soi={doc.get('stateOfIncorporation')!r} "
            f"fye={doc.get('fiscalYearEnd')!r} flags={doc.get('flags')!r} ownerOrg={doc.get('ownerOrg')!r} "
            f"former={len(doc.get('formerNames') or [])} files={len(doc['filings'].get('files') or [])} "
            f"top_forms={forms.most_common(4)} {checks}"
        )

    print(f"\nelapsed submissions {time.time() - t0:.3f}s")

    # Ticker catalogs
    t1 = time.time()
    ct = json.loads((ROOT / "tickers" / "company_tickers.json").read_text())
    cte = json.loads((ROOT / "tickers" / "company_tickers_exchange.json").read_text())
    ct_rows = [dict(v, _key=k) for k, v in ct.items()]
    cte_rows = [dict(zip(cte["fields"], row)) for row in cte["data"]]
    if SAMPLE:
        def pick(rows):
            m = len(rows) // 2
            return rows[:50] + rows[m - 25 : m + 25] + rows[-50:]
        ct_rows, cte_rows = pick(ct_rows), pick(cte_rows)
    for title, rows in (("company_tickers.json", ct_rows), ("company_tickers_exchange.json", cte_rows)):
        p = Paths()
        for r in rows:
            p.walk(r)
        p.report(title, len(rows))
    print("\n=== catalog checks ===")
    print("company_tickers keys are 0..N-1 in order:",
          [r["_key"] for r in ct_rows] == [str(i) for i in range(len(ct_rows))] if not SAMPLE else "n/a (sample)")
    print("cte fields:", cte.get("fields"), "top-level keys:", list(cte))
    for title, rows, cik_key, name_key in (
        ("company_tickers", ct_rows, "cik_str", "title"),
        ("company_tickers_exchange", cte_rows, "cik", "name"),
    ):
        tick = Counter(r["ticker"] for r in rows)
        ciks = Counter(r[cik_key] for r in rows)
        pair = Counter((r[cik_key], r["ticker"]) for r in rows)
        print(
            f"{title}: rows={len(rows)} distinct tickers={len(tick)} dup tickers={[t for t, c in tick.items() if c > 1][:10]} "
            f"distinct ciks={len(ciks)} ciks with >1 ticker={sum(1 for c in ciks.values() if c > 1)} "
            f"max tickers per cik={max(ciks.values())} dup (cik,ticker)={sum(1 for c in pair.values() if c > 1)} "
            f"cik types={Counter(type(r[cik_key]).__name__ for r in rows)} "
            f"cik max digits={max(len(str(r[cik_key])) for r in rows)} empty ticker={sum(1 for r in rows if not r['ticker'])}"
        )
        names_per_cik = defaultdict(set)
        for r in rows:
            names_per_cik[r[cik_key]].add(r[name_key])
        print(f"  ciks with >1 name in one catalog: {sum(1 for s in names_per_cik.values() if len(s) > 1)}")
    if not SAMPLE:
        print("exchange values:", Counter(r["exchange"] for r in cte_rows).most_common())
        a = {(r["cik_str"], r["ticker"]) for r in ct_rows}
        b = {(r["cik"], r["ticker"]) for r in cte_rows}
        print(f"(cik,ticker) pairs: only company_tickers={len(a - b)} only exchange={len(b - a)} both={len(a & b)}")
        print("  e.g. only company_tickers:", sorted(a - b)[:8])
        print("  e.g. only exchange:", sorted(b - a)[:8])
        ta = {r["ticker"]: r["cik_str"] for r in ct_rows}
        tb = {r["ticker"]: r["cik"] for r in cte_rows}
        print("  same ticker, different cik across catalogs:", [(t, ta[t], tb[t]) for t in ta.keys() & tb.keys() if ta[t] != tb[t]][:8])
        name_a = {r["cik_str"]: r["title"] for r in ct_rows}
        name_b = {r["cik"]: r["name"] for r in cte_rows}
        diff = [(c, name_a[c], name_b[c]) for c in name_a.keys() & name_b.keys() if name_a[c] != name_b[c]]
        print(f"  cik whose name differs across catalogs: {len(diff)} e.g. {diff[:5]}")
        # order: sorted? rank?
        print("  exchange catalog order equals company_tickers order on shared pairs:",
              [p for p in [(r['cik'], r['ticker']) for r in cte_rows] if p in a][:5],
              [p for p in [(r['cik_str'], r['ticker']) for r in ct_rows] if p in b][:5])
        # compare with submissions
        subs = {int(doc["cik"]): doc for _, doc, _ in per_file}
        for cik, doc in subs.items():
            cat_t = [r["ticker"] for r in cte_rows if r["cik"] == cik]
            cat_t2 = [r["ticker"] for r in ct_rows if r["cik_str"] == cik]
            cat_n = name_b.get(cik) or name_a.get(cik)
            if cat_t or cat_t2 or doc.get("tickers"):
                print(f"  CIK {cik}: submissions tickers={doc.get('tickers')} exch={doc.get('exchanges')} "
                      f"exchange-catalog={cat_t} tickers-catalog={cat_t2} catalog name={cat_n!r} submissions name={doc.get('name')!r}")
            else:
                print(f"  CIK {cik}: in neither catalog, no tickers in submissions")
    print(f"\nelapsed catalogs {time.time() - t1:.3f}s")


if __name__ == "__main__":
    main()
