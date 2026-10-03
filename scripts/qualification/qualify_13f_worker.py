"""Execute and verify source.read against a pinned offline 13F corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import source_read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_bytes())
    expected = {item["key"]: item for item in json.loads(args.expected.read_bytes())}
    started = time.perf_counter()
    store, checked = Artifacts(), []
    contract_path = ROOT / "crates/source-contract/contracts/thirteenf/contract.yaml"
    contract = {"uri": contract_path.as_uri(), "sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest()}
    with tempfile.TemporaryDirectory(prefix="13f-worker-proof-") as folder:
        root = Path(folder)
        for offset in range(0, len(manifest["files"]), 2):
            batch = manifest["files"][offset:offset+2]
            inputs = [{"uri": Path(item["cache_path"]).as_uri(), "sha256": item["sha256"]} for item in batch]
            input_ref = store.put(root.as_uri(), {"version": 1, "contract": contract, "artifacts": inputs})
            destination = root / f"{offset}.json"
            envelope = {"input": input_ref, "output": destination.as_uri(), "checks": ["source.output"]}
            candidate = source_read.execute(envelope, store)
            assert source_read.verify({**envelope, "candidate": candidate}, store) == ({"source.output": True}, [])
            results = json.loads(store.verified(candidate))["artifacts"]
            for item, result in zip(batch, results, strict=True):
                assert result["deferred"] == []
                tables = result["tables"]
                sha = hashlib.sha256(json.dumps(tables, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
                assert sha == expected[item["key"]]["output_sha256"], item["key"]
                checked.append({"key": item["key"], "input_sha256": item["sha256"], "output_sha256": sha,
                                "rows": sum(len(rows) for rows in tables.values())})
            destination.unlink()  # verified temporary output; hashes retained
            if len(checked) % 20 == 0:
                print(f"Executed and verified: {len(checked)}/{len(manifest['files'])}", flush=True)
    report = {"contract_sha256": contract["sha256"], "files": len(checked), "rows": sum(item["rows"] for item in checked),
              "full_output_parity": True, "verification_passed": True,
              "elapsed_seconds": time.perf_counter()-started, "artifacts": checked}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k != "artifacts"}), flush=True)


if __name__ == "__main__":
    main()
