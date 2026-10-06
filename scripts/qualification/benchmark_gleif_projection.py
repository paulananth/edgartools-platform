"""Measure identical configured projection paths on an authenticated GLEIF sample.

Sampling deliberately stops before EOF; it is performance evidence only. Full
archive/member/metadata qualification is a separate gate. No domain loader runs.
"""
from __future__ import annotations

import argparse
import io
import json
import statistics
import time
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected, stream_json_array


def benchmark(archive, sha256, *, sample_records=1000, rounds=5):
    rows = []
    limits = dict(max_bytes=16 * 1024**3, max_record=1024**2,
                  max_records=10_000_000, max_depth=64,
                  min_integer=-(2**63) + 1, record_encoding="python")
    def sample(row, ordinal):
        rows.append(row)
        if len(rows) == sample_records:
            raise RuntimeError("benchmark_sample_complete")
    ref = {"uri": Path(archive).resolve().as_uri(), "sha256": sha256}
    import zipfile
    with Artifacts().verified_stream(ref, max_bytes=1024**3) as snapshot:
        with zipfile.ZipFile(snapshot) as zipped:
            members = zipped.infolist()
            if len(members) != 1 or members[0].is_dir() or members[0].flag_bits & 1:
                raise ValueError("Benchmark needs one unencrypted captured member")
            with zipped.open(members[0]) as source:
                try:
                    stream_json_array(source, wrapper="records", on_record=sample, **limits)
                except SourceRejected as error:
                    if error.code != "stream_consumer" or "benchmark_sample_complete" not in error.detail:
                        raise
    if len(rows) != sample_records:
        raise ValueError("Captured member has fewer records than requested sample")
    scope = {row["LEI"]["$"]: {"selected": True} for row in rows[::100]}
    contract = {"read": {"format": "json", "limits": {"max_bytes": 1024**2, "max_records": 100},
        "context": {"source_index": {"type": "integer"}}, "references": {"approved_scope": scope},
        "tables": {"rows": {"each": ".", "select": {"lookup": {"reference": "approved_scope",
            "column": "selected", "key": {"text": {"path": "LEI.$"}}, "on_missing": "null"}},
            "columns": {"record": {"value": {"path": "."}},
                        "source_index": {"context": {"name": "source_index"}}}}}}}
    engine = SourceEngine(contract)
    data = json.dumps({"records": rows}, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    limits.update(max_bytes=len(data), max_records=len(rows))
    def run(fused):
        observed = []
        started = time.perf_counter()
        if fused:
            receipt = engine.stream_json_array(io.BytesIO(data), wrapper="records",
                on_reading=lambda reading, index: observed.append((index, reading)),
                ordinal_context="source_index", **limits)
        else:
            def project(row, index):
                body = json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
                observed.append((index, engine.read(body, context={"source_index": index + 1})))
            receipt = stream_json_array(io.BytesIO(data), wrapper="records", on_record=project, **limits)
        return time.perf_counter() - started, receipt, observed
    old, fused = [], []
    for n in range(rounds):
        first, second = run(n % 2 == 1), run(n % 2 == 0)
        assert first[1:] == second[1:], "Projection or EOF receipts differ"
        if n % 2: first, second = second, first
        old.append(first[0]); fused.append(second[0])
    selected = sum(len(reading.tables["rows"]) for _, reading in first[2])
    return {"archive": ref, "sample_records": len(rows), "sample_bytes": len(data),
        "rounds": rounds, "selected_records": selected, "projection_differences": 0,
        "python_roundtrip_seconds": old, "native_projection_seconds": fused,
        "median_speedup": statistics.median(old) / statistics.median(fused),
        "scope": "authenticated captured prefix, framing plus configured projection; not full archive or mastering qualification"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--sample-records", type=int, default=1000)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.sample_records <= 10000 or not 5 <= args.rounds <= 20:
        parser.error("sample-records must be 1..10000 and rounds 5..20")
    result = benchmark(args.archive, args.sha256, sample_records=args.sample_records, rounds=args.rounds)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
