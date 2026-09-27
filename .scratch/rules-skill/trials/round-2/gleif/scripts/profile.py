"""Stream a GLEIF Golden Copy JSON zip and profile its first N records.

Usage: profile.py <zip> <wrapper key> <limit> <out.json>
Never loads a whole file: zipfile streams the member, ijson yields one record
at a time. Paths are dotted; a list step is written `[]`.
"""

import json
import re
import sys
import time
import zipfile
from collections import Counter, defaultdict

import ijson

LEI_RE = re.compile(r"[A-Z0-9]{18}[0-9]{2}")
DISTINCT_CAP = 5000


def lei_ok(v: str) -> bool:
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in v)
    return int(digits) % 97 == 1


def walk(node, path, out):
    """Yield (path, value) for every leaf; lists become `[]`."""
    if isinstance(node, dict):
        if not node:
            out.append((path, {}))
        for k, v in node.items():
            walk(v, f"{path}.{k}" if path else k, out)
    elif isinstance(node, list):
        out.append((path + "#len", len(node)))
        for item in node:
            walk(item, path + "[]", out)
    else:
        out.append((path, node))


def main(zip_path, wrapper, limit, out_path):
    limit = int(limit)
    filled = Counter()  # records in which the path has a non-empty value
    types = defaultdict(Counter)
    distinct = defaultdict(set)
    overflow = set()
    samples = defaultdict(list)
    lei_like = defaultdict(lambda: [0, 0])  # path -> [lei-shaped, passes mod 97]
    list_lens = defaultdict(Counter)
    n = 0
    started = time.time()
    with zipfile.ZipFile(zip_path) as z:
        member = z.infolist()[0]
        with z.open(member) as stream:
            for record in ijson.items(stream, f"{wrapper}.item", use_float=True):
                n += 1
                leaves = []
                walk(record, "", leaves)
                seen = set()
                for path, v in leaves:
                    if path.endswith("#len"):
                        list_lens[path[:-4]][v] += 1
                        continue
                    types[path][type(v).__name__] += 1
                    if v is None or v == "" or v == {}:
                        continue
                    if path not in seen:
                        filled[path] += 1
                        seen.add(path)
                    if path not in overflow:
                        distinct[path].add(v if not isinstance(v, float) else repr(v))
                        if len(distinct[path]) > DISTINCT_CAP:
                            overflow.add(path)
                            distinct[path] = set()
                    if len(samples[path]) < 5 and v not in samples[path]:
                        samples[path].append(v)
                    if isinstance(v, str) and LEI_RE.fullmatch(v):
                        lei_like[path][0] += 1
                        lei_like[path][1] += lei_ok(v)
                if n >= limit:
                    break
    elapsed = time.time() - started
    report = {
        "file": zip_path.rsplit("/", 1)[-1],
        "member": member.filename,
        "expanded_bytes": member.file_size,
        "records_profiled": n,
        "seconds": round(elapsed, 2),
        "paths": {
            p: {
                "filled": filled[p],
                "filled_pct": round(100 * filled[p] / n, 2),
                "types": dict(types[p]),
                "distinct": (f">{DISTINCT_CAP}" if p in overflow else len(distinct[p])),
                "samples": samples[p],
                **(
                    {"lei_shaped": lei_like[p][0], "lei_mod97_ok": lei_like[p][1]}
                    if p in lei_like
                    else {}
                ),
            }
            for p in sorted(types)
        },
        "list_lengths": {p: dict(sorted(c.items())) for p, c in sorted(list_lens.items())},
    }
    with open(out_path, "w") as f:
        json.dump(report, f, indent=1, default=str)
    print(f"{report['file']}: {n} records in {elapsed:.1f}s, {len(types)} paths")


if __name__ == "__main__":
    main(*sys.argv[1:])
