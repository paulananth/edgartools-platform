"""Bounded-sample profile of one GLEIF Golden Copy JSON zip.

Streams the single ZIP member line by line (the files are pretty-printed, one
record opening with a line that is exactly "{" and closing with "}," / "}" /
"}]}" at column 0). Keeps N records from the start, N from the byte middle and
N from the end (ring buffer), parses each with json, and profiles paths.
Writes a JSON report next to this script. No full JSON parse of the file.
"""

from __future__ import annotations

import collections
import io
import json
import re
import sys
import time
import zipfile

LEI_RE = re.compile(r"[A-Z0-9]{18}[0-9]{2}")
DIGITS_RE = re.compile(r"[0-9]{1,10}")


def lei_ok(v: str) -> bool:
    if not LEI_RE.fullmatch(v):
        return False
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in v)
    return int(digits) % 97 == 1


def records(path: str, n: int):
    with zipfile.ZipFile(path) as z:
        info = z.infolist()[0]
        size = info.file_size
        raw = z.open(info)
        f = io.BufferedReader(raw, buffer_size=4 << 20)
        first = f.readline()
        offset = len(first)
        start, middle = [], []
        end = collections.deque(maxlen=n)
        cur = None
        idx = 0
        mid_start = None
        for line in f:
            pos = offset
            offset += len(line)
            if cur is None:
                if line.rstrip(b"\r\n") == b"{":
                    cur = [line]
                    cur_pos = pos
                    continue
                if line.strip() in (b"", b"]}"):
                    continue
                raise SystemExit(f"unexpected line outside record at {pos}: {line[:80]!r}")
            cur.append(line)
            s = line.rstrip(b"\r\n")
            if s in (b"}", b"},", b"}]}"):
                text = b"".join(cur)
                if s.endswith(b",") or s == b"}]}":
                    text = text.rstrip(b"\r\n")
                    text = text[: -1] if s == b"}," else text[: -2] if s == b"}]}" else text
                if idx < n:
                    start.append((idx, cur_pos, text))
                elif cur_pos >= size // 2 and len(middle) < n:
                    if mid_start is None:
                        mid_start = idx
                    middle.append((idx, cur_pos, text))
                end.append((idx, cur_pos, text))
                idx += 1
                cur = None
        return size, idx, start, middle, list(end)


def walk(node, path, out):
    if isinstance(node, dict):
        out.append((path or "<root>", "object", None))
        for k, v in node.items():
            walk(v, f"{path}.{k}" if path else k, out)
    elif isinstance(node, list):
        out.append((path, "array", len(node)))
        for v in node:
            walk(v, path + "[]", out)
    else:
        t = "null" if node is None else type(node).__name__
        out.append((path, t, node))


def profile(rows):
    stats = {}
    for _, _, rec in rows:
        seen = {}
        items = []
        walk(rec, "", items)
        for path, t, val in items:
            st = stats.setdefault(
                path,
                {"records": 0, "occurrences": 0, "types": collections.Counter(),
                 "distinct": set(), "samples": [], "lei_like": 0, "lei_ok": 0,
                 "digits": 0, "blank": 0, "array_len": collections.Counter()},
            )
            st["occurrences"] += 1
            st["types"][t] += 1
            if path not in seen:
                seen[path] = True
                st["records"] += 1
            if t == "array":
                st["array_len"][val] += 1
            if t in ("str", "int", "float", "bool"):
                sv = str(val)
                if isinstance(val, str) and not val.strip():
                    st["blank"] += 1
                if len(st["distinct"]) < 20000:
                    st["distinct"].add(sv)
                if len(st["samples"]) < 6 and sv not in st["samples"]:
                    st["samples"].append(sv)
                if isinstance(val, str) and LEI_RE.fullmatch(val):
                    st["lei_like"] += 1
                    st["lei_ok"] += lei_ok(val)
                if isinstance(val, str) and DIGITS_RE.fullmatch(val):
                    st["digits"] += 1
    out = {}
    for path, st in sorted(stats.items()):
        d = st["distinct"]
        out[path] = {
            "records": st["records"],
            "occurrences": st["occurrences"],
            "types": dict(st["types"]),
            "distinct": len(d) if len(d) < 20000 else ">=20000",
            "samples": st["samples"],
            "lei_like": st["lei_like"],
            "lei_ok": st["lei_ok"],
            "all_digits": st["digits"],
            "blank": st["blank"],
            "array_len": dict(sorted(st["array_len"].items())[:12]),
        }
        if len(d) <= 40:
            out[path]["values"] = sorted(d)
    return out


def main():
    path, n, out_path = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    t = time.time()
    size, total, start, middle, end = records(path, n)
    t_split = time.time() - t
    report = {"file": path.rsplit("/", 1)[-1], "expanded_bytes": size,
              "records_line_split": total, "seconds_line_split": round(t_split, 1)}
    t = time.time()
    parsed = {}
    for name, part in (("start", start), ("middle", middle), ("end", end)):
        rows = [(i, pos, json.loads(txt)) for i, pos, txt in part]
        parsed[name] = rows
        report[f"{name}_ordinals"] = [part[0][0], part[-1][0]] if part else None
    report["seconds_json_sample"] = round(time.time() - t, 2)
    allrows = parsed["start"] + parsed["middle"] + parsed["end"]
    report["sample_records"] = len(allrows)
    report["paths"] = profile(allrows)
    report["by_segment_paths"] = {
        name: {p: v["records"] for p, v in profile(rows).items()}
        for name, rows in parsed.items()
    }
    # keep a few raw records for reading
    report["examples"] = {
        name: [r[2] for r in rows[:2]] for name, rows in parsed.items()
    }
    with open(out_path, "w") as fh:
        json.dump(report, fh, indent=1, default=str)
    print(json.dumps({k: report[k] for k in ("file", "expanded_bytes", "records_line_split",
          "seconds_line_split", "seconds_json_sample", "sample_records",
          "start_ordinals", "middle_ordinals", "end_ordinals")}))


if __name__ == "__main__":
    main()
