"""Compare two configured filing fields on pinned captured submissions, offline.

Every selected byte hash must match its existing receipt. This is partial
projection evidence only: not Company/Person classification or MDM equivalence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from edgar_warehouse.loaders.bronze_submission_extractors import stage_recent_filing_loader
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error("--limit must be 1..1000")
    root = args.capture.resolve()
    receipt_bytes = (root / "receipts.jsonl").read_bytes()
    receipts = [json.loads(line) for line in receipt_bytes.splitlines() if line.strip()]
    receipts = [r for r in receipts if "/submissions/" in r["key"] and "/main/" in r["key"]]
    receipts.sort(key=lambda r: hashlib.sha256(r["key"].encode()).hexdigest())
    selected = receipts[:args.limit]
    if len(selected) != args.limit or len({r["key"] for r in selected}) != args.limit:
        raise ValueError("Need the requested number of distinct captured submissions")
    engine = SourceEngine(files.load(args.contract))
    rows, evidence = 0, []
    for ref in selected:
        path = (root / "bronze" / ref["key"].removeprefix("warehouse/bronze/")).resolve()
        if not path.is_relative_to(root / "bronze"):
            raise ValueError("Capture key escapes its root")
        with path.open("rb") as stream:
            raw = stream.read(32 * 1024**2 + 1)
        if len(raw) > 32 * 1024**2 or hashlib.sha256(raw).hexdigest() != ref["sha256"]:
            raise ValueError("Capture bytes differ from their bounded receipt")
        payload = json.loads(raw)
        old = stage_recent_filing_loader(payload, int(payload["cik"]), "qualification", "captured", "default")
        expected = [{key: row[key] for key in ("accession_number", "form")} for row in old]
        reading = engine.read(raw)
        actual = reading.tables["filings"]
        if actual != expected or reading.deferred:
            raise ValueError(f"Configured filing projection differs for {ref['key']}")
        canonical = json.dumps(actual, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        rows += len(actual)
        evidence.append({"key": ref["key"], "input_sha256": ref["sha256"], "rows": len(actual),
                         "projection_sha256": hashlib.sha256(canonical).hexdigest()})
    result = {"scope": ["accession_number", "form"], "filings": len(selected), "rows": rows,
              "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest(),
              "receipts_sha256": hashlib.sha256(receipt_bytes).hexdigest(), "evidence": evidence}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"filings": len(selected), "rows": rows, "scope": result["scope"]}))


if __name__ == "__main__":
    main()
