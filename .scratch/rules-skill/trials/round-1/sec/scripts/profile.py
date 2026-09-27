"""Profile the captured files in inputs/ (the skill's step 2, done by hand).

Reads each file once, one at a time. No network. For each record type:
paths, types, fill rate, distinct count, samples; candidate keys;
identifier checks (CIK, LEI mod 97, EIN, accession); repeated groups and
cross-record keys; name shapes, dates and addresses.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

INPUTS = Path(sys.argv[1])


class Profile:
    def __init__(self, name):
        self.name = name
        self.n = 0
        self.types = defaultdict(Counter)
        self.filled = Counter()
        self.values = defaultdict(Counter)

    def add(self, record: dict):
        self.n += 1
        for path, item in flatten(record):
            self.types[path][type(item).__name__] += 1
            if not (item is None or item == "" or item == [] or item == {}):
                self.filled[path] += 1
            self.values[path][json.dumps(item, sort_keys=True)[:80]] += 1

    def report(self, keys_hint=()):
        print(f"\n## {self.name}: {self.n} records")
        print(f"{'path':45} {'types':22} {'filled':>9} {'distinct':>8}  samples")
        for path in sorted(self.types):
            types = ",".join(f"{t}:{c}" for t, c in self.types[path].most_common())
            filled = f"{self.filled[path]}/{self.n}"
            distinct = len(self.values[path])
            samples = " | ".join(v for v, _ in self.values[path].most_common(3))
            print(f"{path:45} {types:22} {filled:>9} {distinct:>8}  {samples[:110]}")
        keys = [
            p for p in self.types
            if self.filled[p] == self.n and len(self.values[p]) == self.n
        ]
        print(f"candidate record keys (always filled, unique): {sorted(keys)}")


def flatten(obj, prefix=""):
    if isinstance(obj, dict) and obj:
        for k, v in obj.items():
            yield from flatten(v, f"{prefix}.{k}" if prefix else k)
    else:
        yield prefix, obj


def is_cik(v) -> bool:
    s = str(v).strip()
    return s.isascii() and s.isdigit() and len(s) <= 10 and int(s) != 0


def lei_ok(v) -> bool:
    s = str(v).strip()
    if not re.fullmatch(r"[A-Z0-9]{18}[0-9]{2}", s):
        return False
    return int("".join(str(ord(c) - 55) if c.isalpha() else c for c in s)) % 97 == 1


LEGAL = re.compile(
    r"\b(INC|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|LLC|LP|L\.P|PLC|N\.?V|S\.?A|"
    r"AG|SE|GROUP|HOLDINGS?|TRUST|FUND|BANK|PARTNERS|CAPITAL|ETF)\b\.?",
    re.I,
)


def name_shape(name: str) -> str:
    if not name:
        return "empty"
    if LEGAL.search(name):
        return "organisation"
    words = name.replace(",", " ").split()
    if 2 <= len(words) <= 4 and all(w.isalpha() or len(w) <= 2 for w in words):
        return "person-like"
    return "unclear"


def main():
    # ---------------------------------------------------------- submissions
    header = Profile("submissions header (one per file, filings.* excluded)")
    address = Profile("submissions addresses.<type> (repeated group, keyed by type)")
    former = Profile("submissions formerNames[] (repeated group)")
    recent = Profile("submissions filings.recent (column arrays, one row per filing)")
    pages = Profile("submissions filings.files[] (older pages, not captured)")
    file_checks = []
    accession_seen = Counter()
    lens = {}
    headers = {}
    for path in sorted((INPUTS / "submissions").glob("*.json")):
        with path.open() as stream:
            doc = json.load(stream)
        cik_file = path.stem.removeprefix("CIK")
        head = {k: v for k, v in doc.items() if k not in ("filings", "addresses", "formerNames")}
        header.add(head)
        headers[doc["cik"]] = doc
        for kind, addr in (doc.get("addresses") or {}).items():
            address.add({"address_type": kind, **addr})
        for i, entry in enumerate(doc.get("formerNames") or [], 1):
            former.add({"ordinal": i, **entry})
        cols = (doc.get("filings") or {}).get("recent") or {}
        lengths = {k: len(v) for k, v in cols.items()}
        lens[cik_file] = lengths
        count = max(lengths.values()) if lengths else 0
        for i in range(count):
            row = {k: (v[i] if i < len(v) else "<missing>") for k, v in cols.items()}
            recent.add(row)
            accession_seen[row.get("accessionNumber")] += 1
        for entry in (doc.get("filings") or {}).get("files") or []:
            pages.add(entry)
        file_checks.append((path.name, cik_file, doc.get("cik"), len(set(lengths.values())) <= 1))

    for p in (header, address, former, recent, pages):
        p.report()

    print("\n## submissions: file-level checks")
    bad = [f for f in file_checks if f[1] != f[2] or not f[3]]
    print(f"files: {len(file_checks)}; file name CIK == cik field and all recent columns equal length: "
          f"{len(file_checks) - len(bad)} ok, {len(bad)} not: {bad}")
    print(f"cik field: all 10-digit zero-padded text: "
          f"{all(isinstance(h['cik'], str) and len(h['cik']) == 10 and is_cik(h['cik']) for h in headers.values())}")
    leis = {c: h.get("lei") for c, h in headers.items() if h.get("lei")}
    print(f"lei filled: {len(leis)}/{len(headers)}; passing mod 97: {sum(lei_ok(v) for v in leis.values())}; values: {leis}")
    eins = [h.get("ein") for h in headers.values()]
    print(f"ein: filled {sum(bool(e) for e in eins)}/{len(eins)}; 9 digits {sum(bool(e) and bool(re.fullmatch(r'[0-9]{9}', e)) for e in eins)}; "
          f"all-zero or placeholder {sum(e in ('000000000', '999999999') for e in eins if e)}; samples {eins[:6]}")
    acc_re = re.compile(r"\d{10}-\d{2}-\d{6}")
    print(f"accessionNumber: {sum(accession_seen.values())} rows, {len(accession_seen)} distinct, "
          f"format NNNNNNNNNN-YY-NNNNNN: {sum(bool(acc_re.fullmatch(a or '')) for a in accession_seen)}; "
          f"repeated across files: {sum(1 for c in accession_seen.values() if c > 1)}")
    et = Counter(h.get("entityType") for h in headers.values())
    print(f"entityType: {dict(et)}")
    print(f"category: {dict(Counter(h.get('category') for h in headers.values()))}")
    print(f"sic filled: {sum(bool(h.get('sic')) for h in headers.values())}/{len(headers)}")
    print(f"tickers non-empty: {sum(bool(h.get('tickers')) for h in headers.values())}/{len(headers)}; "
          f"tickers/exchanges same length: {all(len(h.get('tickers') or []) == len(h.get('exchanges') or []) for h in headers.values())}")
    print("name shapes (submissions name):")
    for c, h in sorted(headers.items()):
        forms = Counter(((h.get("filings") or {}).get("recent") or {}).get("form") or [])
        print(f"  {c} {h.get('entityType'):10} sic={h.get('sic') or '-':5} {name_shape(h.get('name')):12} "
              f"{h.get('name')!r:45} tickers={h.get('tickers')} cat={h.get('category')!r} "
              f"inc={h.get('stateOfIncorporation')!r} top_forms={[f for f, _ in forms.most_common(4)]}")
    print("addresses: business stateOrCountry / countryCode / isForeignLocation (by filer):")
    for c, h in sorted(headers.items()):
        b = (h.get("addresses") or {}).get("business") or {}
        m = (h.get("addresses") or {}).get("mailing") or {}
        print(f"  {c} business: soc={b.get('stateOrCountry')!r} cc={b.get('countryCode')!r} "
              f"country={b.get('country')!r} zip={b.get('zipCode')!r} foreign={b.get('isForeignLocation')!r} | "
              f"mailing soc={m.get('stateOrCountry')!r} cc={m.get('countryCode')!r}")
    fn_dates = [e.get("from") for h in headers.values() for e in h.get("formerNames") or []]
    print(f"formerNames date format samples: {fn_dates[:3]}")

    # ---------------------------------------------------------- tickers
    t1 = Profile("company_tickers.json rows")
    with (INPUTS / "tickers" / "company_tickers.json").open() as stream:
        raw = json.load(stream)
    keys = list(raw)
    rows1 = [raw[k] for k in keys]
    for r in rows1:
        t1.add(r)
    t1.report()
    print(f"object keys are '0'..'{len(keys) - 1}' in order: {keys == [str(i) for i in range(len(keys))]}")

    t2 = Profile("company_tickers_exchange.json rows")
    with (INPUTS / "tickers" / "company_tickers_exchange.json").open() as stream:
        raw2 = json.load(stream)
    print(f"\ncompany_tickers_exchange fields: {raw2['fields']}")
    rows2 = [dict(zip(raw2["fields"], r)) for r in raw2["data"]]
    for r in rows2:
        t2.add(r)
    t2.report()

    for label, rows, cik_key in (("company_tickers", rows1, "cik_str"), ("exchange", rows2, "cik")):
        per_cik = Counter(r[cik_key] for r in rows)
        tick = Counter(r["ticker"] for r in rows)
        print(f"\n{label}: {len(rows)} rows, {len(per_cik)} distinct CIKs, "
              f"CIKs with >1 ticker: {sum(1 for c in per_cik.values() if c > 1)} (max {max(per_cik.values())}), "
              f"tickers repeated: {sum(1 for c in tick.values() if c > 1)}; "
              f"(cik,ticker) unique: {len({(r[cik_key], r['ticker']) for r in rows}) == len(rows)}; "
              f"all CIKs valid: {all(is_cik(r[cik_key]) for r in rows)}")
    same = [
        (a["cik_str"], a["ticker"]) == (b["cik"], b["ticker"]) for a, b in zip(rows1, rows2)
    ]
    print(f"row-by-row same (cik,ticker) order in both files: {sum(same)}/{min(len(rows1), len(rows2))}; "
          f"sets equal: {set((r['cik_str'], r['ticker']) for r in rows1) == set((r['cik'], r['ticker']) for r in rows2)}")
    only1 = set((r['cik_str'], r['ticker']) for r in rows1) - set((r['cik'], r['ticker']) for r in rows2)
    only2 = set((r['cik'], r['ticker']) for r in rows2) - set((r['cik_str'], r['ticker']) for r in rows1)
    print(f"only in company_tickers: {len(only1)} {sorted(only1)[:5]}; only in exchange: {len(only2)} {sorted(only2)[:5]}")
    print(f"exchange values: {dict(Counter(r['exchange'] for r in rows2))}")

    # ---------------------------------------------------------- cross-file
    sub_ciks = {int(c) for c in headers}
    cat_ciks = {r["cik"] for r in rows2}
    print(f"\nsubmissions CIKs in the exchange catalog: {len(sub_ciks & cat_ciks)}/{len(sub_ciks)}; "
          f"not listed: {sorted(sub_ciks - cat_ciks)}")
    mism = []
    for c, h in headers.items():
        cat = [r["ticker"] for r in rows2 if r["cik"] == int(c)]
        if sorted(cat) != sorted(h.get("tickers") or []):
            mism.append((c, h.get("tickers"), cat))
    print(f"submissions tickers vs catalog tickers differ for {len(mism)} filers: {mism[:8]}")
    names = [(c, h["name"], next((r["name"] for r in rows2 if r["cik"] == int(c)), None)) for c, h in headers.items()]
    print(f"submissions name == catalog name: {sum(1 for _, a, b in names if b and a == b)}/{sum(1 for _, _, b in names if b)}; "
          f"differ: {[(c, a, b) for c, a, b in names if b and a != b][:6]}")
    shapes = Counter(name_shape(r["name"]) for r in rows2)
    print(f"catalog name shapes: {dict(shapes)}; person-like samples: "
          f"{[r['name'] for r in rows2 if name_shape(r['name']) == 'person-like'][:8]}")


if __name__ == "__main__":
    main()
