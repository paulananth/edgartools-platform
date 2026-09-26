"""Compare parse_thirteenf with the 13F Source Contract on a pinned local cache.

The cache is keyed by ETag. This script does not open S3 or the SEC.
period_of_report is unknown from the information table alone, so the Python
parser is called with an empty period and does not apply the thousands
multiplier. security_class is not in the contract: it depends on edgartools'
ticker lookup.
"""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent / "engine"))

from source_engine import Engine  # noqa: E402

from edgar_warehouse.parsers.thirteenf import parse_thirteenf  # noqa: E402

PIN = ROOT / "docs/research/heavy-parse-s3-pin-13f-2026-09-25.json"
CACHE = Path.home() / ".local/share/edgartools/heavy-parse-13f"
FIELDS = (
    "cusip",
    "issuer_name",
    "security_title",
    "shares_held",
    "market_value",
    "put_call",
    "discretion_type",
    "voting_auth_sole",
    "voting_auth_shared",
    "voting_auth_none",
)


def same(left, right) -> bool:
    if left is None and right is None:
        return True
    if isinstance(left, float) or isinstance(right, float):
        if left is None or right is None:
            return False
        return abs(float(left) - float(right)) < 1e-6
    return left == right


def cik_and_accession(key: str) -> tuple[int, str]:
    parts = key.split("/")
    cik = int(parts[4].split("=", 1)[1])
    accession = parts[5].split("=", 1)[1]
    return cik, accession


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("limit", type=int, nargs="?", default=10)
    parser.add_argument("--pin", type=Path, default=PIN)
    parser.add_argument("--cache", type=Path, default=CACHE)
    args = parser.parse_args()
    available = json.loads(args.pin.read_text())["sample_1000"]
    if not 1 <= args.limit <= len(available):
        parser.error(f"limit must be between 1 and {len(available)}")
    rows = available[:args.limit]
    engine = Engine(Path(__file__).resolve().parent / "sources" / "thirteenf", {})
    stats = {
        "files": 0,
        "match": 0,
        "both_empty": 0,
        "row_mismatch": 0,
        "field_mismatch": 0,
        "rules_rows": 0,
        "python_rows": 0,
        "rules_seconds": 0.0,
        "python_seconds": 0.0,
        "examples": [],
        "rejects": 0,
        "type_errors": 0,
    }
    for item in rows:
        path = args.cache / item["etag"]
        raw = path.read_bytes()
        if len(raw) != item["size"]:
            raise ValueError(f"Cached size differs from pin: {item['key']}")
        cik, accession = cik_and_accession(item["key"])
        engine.rejects.clear()
        engine.type_errors.clear()
        t0 = time.perf_counter()
        rules = engine.parse(raw)["sec_thirteenf_holding"]
        stats["rules_seconds"] += time.perf_counter() - t0
        t1 = time.perf_counter()
        python_rows = parse_thirteenf(
            raw.decode("utf-8", errors="replace"),
            cik=cik,
            accession_number=accession,
            period_of_report="",
        )["sec_thirteenf_holding"]
        stats["python_seconds"] += time.perf_counter() - t1
        stats["files"] += 1
        stats["rules_rows"] += len(rules)
        stats["python_rows"] += len(python_rows)
        stats["rejects"] += len(engine.rejects)
        stats["type_errors"] += len(engine.type_errors)
        if not rules and not python_rows:
            stats["both_empty"] += 1
            continue
        if len(rules) != len(python_rows):
            stats["row_mismatch"] += 1
            if len(stats["examples"]) < 5:
                stats["examples"].append(
                    {
                        "key": item["key"],
                        "rules": len(rules),
                        "python": len(python_rows),
                        "rejects": engine.rejects[:2],
                        "type_errors": engine.type_errors[:2],
                    }
                )
            continue
        bad = None
        for rule_row, py_row in zip(rules, python_rows, strict=True):
            for field in FIELDS:
                if not same(rule_row.get(field), py_row.get(field)):
                    bad = (field, rule_row.get(field), py_row.get(field), rule_row["holding_index"])
                    break
            if bad:
                break
        if bad:
            stats["field_mismatch"] += 1
            if len(stats["examples"]) < 5:
                stats["examples"].append({"key": item["key"], "field": bad[0], "rules": bad[1], "python": bad[2], "index": bad[3]})
        else:
            stats["match"] += 1
        if stats["files"] % 25 == 0:
            print(f"{stats['files']} match={stats['match']}", flush=True)
    stats["rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
    print(json.dumps(stats, indent=2))
    if stats["row_mismatch"] or stats["field_mismatch"] or stats["rejects"] or stats["type_errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
