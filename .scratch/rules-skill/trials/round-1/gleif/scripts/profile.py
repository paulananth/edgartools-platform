"""Stream-profile one GLEIF Golden Copy JSON zip (the skill's step 2 stand-in).

Never extracts to disk and never holds the whole file: ijson (yajl2_c) walks the
single zip member record by record.

usage: profile.py <zip> <wrapper> <out.json> [--write-leis FILE] [--leis FILE]
                  [--key path[,path...]] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import zipfile
from collections import Counter, defaultdict

import ijson

LEI_RE = re.compile(r"[A-Z0-9]{18}[0-9]{2}")
CIK_RE = re.compile(r"[0-9]{1,10}")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?)?")
DISTINCT_CAP = 200_000
TOP_CAP = 2_000  # keep a full value counter only while distinct values stay below this
ORG_TOKENS = re.compile(
    r"\b(INC|LLC|LTD|LIMITED|CORP|CORPORATION|COMPANY|CO|PLC|GMBH|AG|SA|S\.A\.|SAS|SARL|BV|B\.V\.|NV|N\.V\.|LP|L\.P\.|LLP|FUND|TRUST|BANK|HOLDINGS?|GROUP|S\.P\.A\.|SPA|AB|OY|AS|A/S|KG|SE|PTE|PTY|BHD|KK|FOUNDATION|ASSOCIATION|PARTNERS|CAPITAL|SICAV|ETF|PORTFOLIO|SERIES)\b",
    re.I,
)


def lei_ok(value: str) -> bool:
    if not LEI_RE.fullmatch(value):
        return False
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in value)
    return int(digits) % 97 == 1


class PathStats:
    __slots__ = (
        "records", "values", "types", "distinct", "capped", "top", "samples",
        "lei_shaped", "lei_valid", "cik_shaped", "date_shaped", "max_len", "multi",
        "org_like", "blank",
    )

    def __init__(self):
        self.records = 0  # records where this path holds a non-empty value
        self.values = 0
        self.types = Counter()
        self.distinct: set | None = set()
        self.capped = False
        self.top: Counter | None = Counter()
        self.samples: list = []
        self.lei_shaped = self.lei_valid = self.cik_shaped = self.date_shaped = 0
        self.max_len = 0  # for list paths: longest list
        self.multi = 0  # for list paths: records with more than one element
        self.org_like = 0
        self.blank = 0


def flatten(value, path, out):
    if isinstance(value, dict):
        out.append((path, "object", None))
        for key, item in value.items():
            flatten(item, f"{path}.{key}" if path else key, out)
    elif isinstance(value, list):
        out.append((path, "array", len(value)))
        for item in value:
            flatten(item, path + "[]", out)
    else:
        kind = (
            "null" if value is None else "bool" if isinstance(value, bool)
            else "number" if isinstance(value, (int, float)) else "string"
            if isinstance(value, str) else type(value).__name__
        )
        out.append((path, kind, value))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zip")
    ap.add_argument("wrapper")
    ap.add_argument("out")
    ap.add_argument("--write-leis")
    ap.add_argument("--leis")
    ap.add_argument("--key", action="append", default=[])
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    known = None
    if args.leis:
        with open(args.leis) as fh:
            known = {line.strip() for line in fh if line.strip()}

    stats: dict[str, PathStats] = defaultdict(PathStats)
    keys = {k: set() for k in args.key}
    key_dupes = Counter()
    key_dupe_samples = defaultdict(list)
    key_missing = Counter()
    refs = defaultdict(Counter)  # path -> {in_level1, not_in_level1}
    ref_samples = defaultdict(list)
    lei_out = open(args.write_leis, "w") if args.write_leis else None
    first_records = []
    count = 0
    started = time.time()
    with zipfile.ZipFile(args.zip) as archive:
        (member,) = archive.infolist()
        with archive.open(member) as stream:
            for record in ijson.items(stream, f"{args.wrapper}.item", use_float=True):
                count += 1
                if len(first_records) < 3:
                    first_records.append(record)
                flat: list = []
                flatten(record, "", flat)
                seen_paths = set()
                for path, kind, val in flat:
                    if not path:
                        continue
                    st = stats[path]
                    st.types[kind] += 1
                    if kind == "array":
                        st.max_len = max(st.max_len, val)
                        if val > 1:
                            st.multi += 1
                        if val and path not in seen_paths:
                            seen_paths.add(path)
                            st.records += 1
                        continue
                    if kind == "object":
                        if path not in seen_paths:
                            seen_paths.add(path)
                            st.records += 1
                        continue
                    if kind == "string" and not val.strip():
                        st.blank += 1
                        continue
                    if val is None:
                        continue
                    st.values += 1
                    if path not in seen_paths:
                        seen_paths.add(path)
                        st.records += 1
                    if st.distinct is not None:
                        st.distinct.add(val)
                        if len(st.distinct) > DISTINCT_CAP:
                            st.distinct = None
                            st.capped = True
                    if st.top is not None:
                        st.top[val] += 1
                        if len(st.top) > TOP_CAP:
                            st.top = None
                    if len(st.samples) < 8 and val not in st.samples:
                        st.samples.append(val)
                    if kind == "string":
                        if LEI_RE.fullmatch(val):
                            st.lei_shaped += 1
                            if lei_ok(val):
                                st.lei_valid += 1
                            if known is not None:
                                hit = "in_level1" if val in known else "not_in_level1"
                                refs[path][hit] += 1
                                if hit == "not_in_level1" and len(ref_samples[path]) < 5:
                                    ref_samples[path].append(val)
                        if CIK_RE.fullmatch(val):
                            st.cik_shaped += 1
                        if DATE_RE.fullmatch(val):
                            st.date_shaped += 1
                        if path.endswith("Name.$") and ORG_TOKENS.search(val):
                            st.org_like += 1
                if lei_out is not None:
                    lei = (record.get("LEI") or {}).get("$")
                    if lei:
                        lei_out.write(lei + "\n")
                for key in args.key:
                    parts = []
                    for p in key.split(","):
                        cur = record
                        for part in p.split("."):
                            cur = cur.get(part) if isinstance(cur, dict) else None
                        parts.append(cur)
                    if any(x is None or x == "" for x in parts):
                        key_missing[key] += 1
                        continue
                    h = hash(tuple(parts))
                    if h in keys[key]:
                        key_dupes[key] += 1
                        if len(key_dupe_samples[key]) < 5:
                            key_dupe_samples[key].append(parts)
                    else:
                        keys[key].add(h)
                if count % 250_000 == 0:
                    print(f"{count} records, {time.time() - started:.0f}s", file=sys.stderr, flush=True)
                if args.limit and count >= args.limit:
                    break
    if lei_out is not None:
        lei_out.close()

    report = {
        "file": args.zip,
        "records": count,
        "seconds": round(time.time() - started),
        "first_records": first_records,
        "keys": {
            k: {
                "distinct": len(keys[k]),
                "duplicates": key_dupes[k],
                "missing": key_missing[k],
                "duplicate_samples": key_dupe_samples[k],
            }
            for k in args.key
        },
        "references_to_level1": {p: dict(c) for p, c in refs.items()},
        "reference_samples_not_in_level1": dict(ref_samples),
        "paths": {},
    }
    for path in sorted(stats):
        st = stats[path]
        entry = {
            "types": dict(st.types),
            "records_filled": st.records,
            "fill_rate": round(st.records / count, 4) if count else None,
            "values": st.values,
            "blank_strings": st.blank,
            "distinct": (">" + str(DISTINCT_CAP)) if st.capped else len(st.distinct or ()),
            "samples": st.samples,
        }
        if st.top is not None and st.top:
            entry["top"] = st.top.most_common(40)
        if st.max_len:
            entry["max_list_len"] = st.max_len
            entry["records_with_multi"] = st.multi
        for name in ("lei_shaped", "lei_valid", "cik_shaped", "date_shaped", "org_like"):
            if getattr(st, name):
                entry[name] = getattr(st, name)
        report["paths"][path] = entry
    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=1, default=str, ensure_ascii=False)
    print(f"done: {count} records in {time.time() - started:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
