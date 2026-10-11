"""Offline reduction worker comparison; immutable baseline loaded from git.

Run: uv run --no-sync python .planning/workstreams/rust-configured-reduction/benchmark.py
Measures execute + independent verify, authenticated local artifact reads,
native conversion, output encoding/writes and idempotent repeat writes.
Does not measure source acquisition, parsing, MDM, AWS or production workloads.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import platform
from pathlib import Path
import resource
import statistics
import subprocess
import sys
import tempfile
import time
import types

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
BASELINE = "45525cd8bc1df550bfba10022bd5eead1f41359d"


def child(mode, workers, manifest):
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.workers import source_combine
    baseline = subprocess.check_output(
        ["git", "show", f"{BASELINE}:edgar_warehouse/workers/source_reduction.py"], cwd=ROOT)
    if mode == "python":
        module = types.ModuleType("edgar_warehouse.workers._pinned_reduction")
        module.__package__ = "edgar_warehouse.workers"
        exec(compile(baseline, "pinned_reduction.py", "exec"), module.__dict__)
        source_combine.source_reduction = module
    tasks = json.loads(Path(manifest).read_text())[:workers]
    store = Artifacts()

    def work(task):
        receipt = source_combine.execute(task, store)
        assert source_combine.verify({**task, "candidate": receipt}, store) == (
            {source_combine.CHECK: True}, [])
        return receipt["sha256"]

    times, hashes = [], []
    for _ in range(5):
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            result = list(pool.map(work, tasks))
        times.append(time.perf_counter() - start)
        hashes.append(result)
    assert all(result == hashes[0] for result in hashes)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(json.dumps({"mode": mode, "workers": workers, "seconds": times,
                      "median_seconds": statistics.median(times),
                      "worker_runs_per_second": workers / statistics.median(times),
                      "peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024,
                      "output_sha256": hashes[0],
                      "baseline_source_sha256": hashlib.sha256(baseline).hexdigest()}))


def main(sizes, output):
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from tests.engine.test_source_combine import envelope
    from tests.engine.test_source_reduction import member, partitioned, plan
    from edgar_warehouse.rules.source_engine import runtime_files
    native = runtime_files()[-1]
    evidence = {"baseline_commit": BASELINE, "trials": 5,
                "scope": "offline source.combine reduce execute + verify; local artifact I/O",
                "production_qualified": False, "python_version": sys.version,
                "machine": platform.machine(), "native_binary_sha256": hashlib.sha256(native.read_bytes()).hexdigest(),
                "workloads": []}
    with tempfile.TemporaryDirectory(prefix="codex-native-reduction-") as temp:
        root = Path(temp)
        store = Artifacts()
        for size in sizes:
            folder = root / str(size)
            folder.mkdir()
            chunks = []
            for start in range(0, size, 5000):
                chunks.append({
                    "legal": [{"key": f"k{i % 257}", "holder": f"M{(i // 257) % 149}",
                               "time": str(i), "ignored": "é𐀀\n\\"} for i in range(start, min(size, start + 5000))],
                    "other": [{"key": f"k{i % 257}", "holder": f"M{(i // 257) % 200}"}
                              for i in range(start, min(size, start + 5000))]})
            groups = {"legal": member("legal", last="time", limit=10),
                      "other": member("other", exclude="legal", limit=10),
                      "counts": {"source": "main", "table": "legal", "keys": ["key"],
                                 "mode": "count", "count": "frequency", "sample": None, "sample_limit": 0}}
            body = plan(groups, max_rows=2 * size, max_input_bytes=64 * 1024**2,
                        max_keys=10000, max_members=500000, max_state_bytes=64 * 1024**2,
                        max_output_rows=10000, max_output_bytes=8 * 1024**2)
            ref = partitioned(store, folder, chunks)
            tasks = [envelope(store, folder / f"worker-{i}", body, {"main": ref}) for i in range(4)]
            manifest = folder / "tasks.json"
            manifest.write_text(json.dumps(tasks))
            workload = {"selected_rows_per_table": size, "input_rows_per_worker": size * 2,
                        "groups": 3, "partition_count": len(chunks), "runs": []}
            for workers in (1, 2, 4):
                results = []
                for mode in ("python", "rust"):
                    completed = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                        "--child", mode, "--workers", str(workers), "--manifest", str(manifest)],
                        cwd=ROOT, check=True, text=True, capture_output=True)
                    result = json.loads(completed.stdout)
                    results.append(result)
                    print(f"rows={size} workers={workers} {mode}: {result['median_seconds']:.3f}s", flush=True)
                assert results[0]["output_sha256"] == results[1]["output_sha256"]
                workload["runs"].append({"workers": workers, "python": results[0], "rust": results[1],
                    "exact_output_parity": True,
                    "speedup": results[0]["median_seconds"] / results[1]["median_seconds"],
                    "rss_ratio": results[1]["peak_rss_bytes"] / results[0]["peak_rss_bytes"]})
            evidence["workloads"].append(workload)
    destination = Path(__file__).with_name(output)
    destination.write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"Evidence: {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", choices=["python", "rust"])
    parser.add_argument("--workers", type=int)
    parser.add_argument("--manifest")
    parser.add_argument("--rows", type=int, nargs="+", choices=[20000, 100000], default=[20000, 100000])
    parser.add_argument("--output", default="benchmark.json")
    args = parser.parse_args()
    if args.child:
        child(args.child, args.workers, args.manifest)
    else:
        main(args.rows, args.output)
