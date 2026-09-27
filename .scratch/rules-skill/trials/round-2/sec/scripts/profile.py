"""Bounded profile of the captured SEC files (trial, Phase A). Streams nothing
large: the files are small (<1 MB each), so each is read whole."""
import json, re, sys, collections
from pathlib import Path

IN = Path(sys.argv[1])
MAXSAMP = 5

def lei_ok(v):
    v = str(v)
    if not re.fullmatch(r"[A-Z0-9]{18}[0-9]{2}", v):
        return False
    return int("".join(str(ord(c) - 55) if c.isalpha() else c for c in v)) % 97 == 1

class Prof:
    def __init__(self, name):
        self.name = name; self.n = 0
        self.paths = collections.defaultdict(lambda: {"types": collections.Counter(), "filled": 0,
                                                       "distinct": set(), "samples": []})
    def add(self, rec, prefix=""):
        if prefix == "":
            self.n += 1
        for k, v in rec.items():
            p = f"{prefix}{k}"
            if isinstance(v, dict) and v and prefix.count(".") < 3:
                self.add(v, p + ".")
                continue
            s = self.paths[p]
            s["types"][type(v).__name__] += 1
            filled = v not in (None, "", [], {})
            if filled:
                s["filled"] += 1
                key = json.dumps(v, sort_keys=True)[:200]
                s["distinct"].add(key)
                if len(s["samples"]) < MAXSAMP and key not in s["samples"]:
                    s["samples"].append(key)
    def report(self):
        print(f"\n=== {self.name}: {self.n} records ===")
        for p, s in sorted(self.paths.items()):
            key = " KEY?" if s["filled"] == self.n and len(s["distinct"]) == self.n else ""
            print(f"  {p:45s} types={dict(s['types'])} filled={s['filled']}/{self.n} "
                  f"distinct={len(s['distinct'])}{key}")
            print(f"      samples={s['samples'][:MAXSAMP]}")

# --- submissions
top, addr, former, recent, files = (Prof("submissions: filer (top level, arrays excluded)"),
    Prof("submissions: addresses (mailing+business)"), Prof("submissions: formerNames[]"),
    Prof("submissions: filings.recent (zipped parallel arrays)"), Prof("submissions: filings.files[]"))
mismatch = []; lens_bad = []; subs = {}
for f in sorted((IN / "submissions").glob("*.json")):
    d = json.loads(f.read_bytes())
    subs[d["cik"]] = d
    if f.stem != f"CIK{d['cik']}":
        mismatch.append((f.name, d["cik"]))
    flat = {k: v for k, v in d.items() if k not in ("addresses", "formerNames", "filings")}
    for k in ("tickers", "exchanges"):
        flat[k] = d.get(k)
    top.add(flat)
    for t, a in (d.get("addresses") or {}).items():
        addr.add({"address_type": t, "cik": d["cik"], **a})
    for i, fn in enumerate(d.get("formerNames") or [], 1):
        former.add({"cik": d["cik"], "ordinal": i, **fn})
    r = (d.get("filings") or {}).get("recent") or {}
    lens = {k: len(v) for k, v in r.items()}
    if len(set(lens.values())) > 1:
        lens_bad.append((d["cik"], lens))
    for i in range(max(lens.values(), default=0)):
        recent.add({"cik": d["cik"], **{k: (v[i] if i < len(v) else None) for k, v in r.items()}})
    for x in (d.get("filings") or {}).get("files") or []:
        files.add({"cik": d["cik"], **x})
for p in (top, addr, former, recent, files):
    p.report()
print("\nfilename/cik mismatches:", mismatch)
print("recent arrays of unequal length:", lens_bad)
print("top-level key sets:", collections.Counter(tuple(sorted(d)) for d in subs.values()))
print("filings key sets:", collections.Counter(tuple(sorted(d.get("filings") or {})) for d in subs.values()))

# identifiers
print("\n--- identifier checks")
ciks = [d["cik"] for d in subs.values()]
print("cik all 10-digit zero-padded strings:", all(isinstance(c, str) and re.fullmatch(r"\d{10}", c) for c in ciks))
leis = [(d["cik"], d.get("lei")) for d in subs.values() if d.get("lei")]
print("non-null lei:", leis, "mod97 ok:", [lei_ok(l) for _, l in leis])
eins = [d.get("ein") for d in subs.values() if d.get("ein")]
print("ein filled:", len(eins), "all 9 digits:", all(re.fullmatch(r"\d{9}", e) for e in eins),
      "distinct values:", collections.Counter(eins).most_common(5))
print("entityType:", collections.Counter(d.get("entityType") for d in subs.values()))
print("category:", collections.Counter(d.get("category") for d in subs.values()))
print("sic:", collections.Counter(d.get("sic") for d in subs.values()).most_common(15))
print("stateOfIncorporation:", collections.Counter(d.get("stateOfIncorporation") for d in subs.values()))
print("flags:", collections.Counter(d.get("flags") for d in subs.values()))
print("tickers per filer:", collections.Counter(len(d.get("tickers") or []) for d in subs.values()))
print("insider flags:", collections.Counter((d.get("insiderTransactionForOwnerExists"), d.get("insiderTransactionForIssuerExists")) for d in subs.values()))

# --- tickers
ct = json.loads((IN / "tickers/company_tickers.json").read_bytes())
cte = json.loads((IN / "tickers/company_tickers_exchange.json").read_bytes())
ct_rows = [{"key": k, **v} for k, v in ct.items()]
cte_rows = [dict(zip(cte["fields"], r)) for r in cte["data"]]
p1, p2 = Prof("company_tickers.json rows"), Prof("company_tickers_exchange.json rows (zipped)")
for r in ct_rows: p1.add(r)
for r in cte_rows: p2.add(r)
p1.report(); p2.report()
print("\ncompany_tickers keys sequential 0..N-1:", [int(k) for k in ct] == list(range(len(ct))))
print("cte fields:", cte["fields"], "row lengths:", collections.Counter(len(r) for r in cte["data"]))
for name, rows, ck in (("ct", ct_rows, "cik_str"), ("cte", cte_rows, "cik")):
    tick = collections.Counter(r["ticker"] for r in rows)
    pairs = collections.Counter((r[ck], r["ticker"]) for r in rows)
    print(f"{name}: rows={len(rows)} distinct ciks={len({r[ck] for r in rows})} "
          f"dup tickers={[t for t, c in tick.items() if c > 1][:10]} dup (cik,ticker)={sum(c > 1 for c in pairs.values())} "
          f"cik types={collections.Counter(type(r[ck]).__name__ for r in rows)} "
          f"null/empty ticker={sum(1 for r in rows if not r['ticker'])} null cik={sum(1 for r in rows if r[ck] is None)}")
    print(f"   tickers per cik: {collections.Counter(collections.Counter(r[ck] for r in rows).values()).most_common(8)}")
print("cte exchange values:", collections.Counter(r["exchange"] for r in cte_rows))
ct_pairs = {(r["cik_str"], r["ticker"]) for r in ct_rows}
cte_pairs = {(r["cik"], r["ticker"]) for r in cte_rows}
print("pairs only in ct:", len(ct_pairs - cte_pairs), sorted(ct_pairs - cte_pairs)[:8])
print("pairs only in cte:", len(cte_pairs - ct_pairs), sorted(cte_pairs - ct_pairs)[:8])
ct_title = {(r["cik_str"], r["ticker"]): r["title"] for r in ct_rows}
diff_names = [(k, ct_title[k], r["name"]) for r in cte_rows for k in [(r["cik"], r["ticker"])] if k in ct_title and ct_title[k] != r["name"]]
print("title != name for same pair:", len(diff_names), diff_names[:5])
order_same = [(r["cik_str"], r["ticker"]) for r in ct_rows] == [(r["cik"], r["ticker"]) for r in cte_rows]
print("same row order in both catalogs:", order_same)

# --- relationships: catalog -> submissions
sub_ciks = {int(c) for c in subs}
cat_ciks = {r["cik_str"] for r in ct_rows}
print("\n--- cross-file")
print("submission CIKs in ticker catalog:", len(sub_ciks & cat_ciks), "of", len(sub_ciks),
      "; not in catalog:", sorted(f"{c:010d}" for c in sub_ciks - cat_ciks))
cat_by_cik = collections.defaultdict(list)
for r in ct_rows: cat_by_cik[r["cik_str"]].append(r["ticker"])
dis = [(c, d.get("tickers"), cat_by_cik.get(int(c))) for c, d in subs.items()
       if sorted(d.get("tickers") or []) != sorted(cat_by_cik.get(int(c), []))]
print("submissions.tickers != catalog tickers for:", len(dis), dis[:8])
name_dis = [(c, d["name"], {r["title"] for r in ct_rows if r["cik_str"] == int(c)}) for c, d in subs.items()
            if int(c) in cat_ciks and d["name"] not in {r["title"] for r in ct_rows if r["cik_str"] == int(c)}]
print("submissions.name != catalog title:", len(name_dis), name_dis[:6])
