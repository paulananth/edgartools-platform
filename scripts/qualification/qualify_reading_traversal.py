"""Measure authenticated traversal cost on synthetic repeated-row partitions."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time

from edgar_warehouse import control_contract
from edgar_warehouse.bookkeeping.clean import artifacts as artifact_store
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import source_readings


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--partitions", type=int, nargs="+", default=[128, 512, 2048, 4096])
    args = parser.parse_args()
    if not 1 <= len(args.partitions) <= 8 or any(not 1 <= n <= 4096 for n in args.partitions):
        parser.error("supply 1..8 sizes, each 1..4096 partitions")
    files = [__file__, source_readings.__file__, artifact_store.__file__, control_contract.__file__,
             str(Path(artifact_store.__file__).with_name("config.py"))]
    pins = {str(Path(path).resolve()): sha(path) for path in files}
    results = []
    with tempfile.TemporaryDirectory(prefix="reading-traversal-") as location:
        root = Path(location)
        store = Artifacts()
        input_ref = store.put(root.as_uri(), {"captured": "synthetic repeated row"})
        contract_ref = store.put(root.as_uri(), {"fixture": "traversal cost only"})
        part = store.put(root.as_uri(), {"version": 1, "tables": {"rows": [{"key": "a", "value": 1}]}, "deferred": []})
        part_bytes = len(store.verified(part))
        for count in args.partitions:
            body = {"version": 2, "contract": contract_ref, "artifacts": [{
                "input": input_ref, "record_count": count, "expanded_bytes": count * 64,
                "table_names": ["rows"], "partitions": [{
                    "receipt": part, "first_ordinal": i + 1, "record_count": 1,
                    "bytes": part_bytes} for i in range(count)]}]}
            ref = store.put(root.as_uri(), body)
            index_bytes = len(store.verified(ref))
            maximum = index_bytes + count * part_bytes
            started = time.perf_counter()
            materialized, consumed = source_readings.load(ref, store, max_bytes=maximum, max_rows=count)
            load_seconds = time.perf_counter() - started
            if len(materialized["artifacts"][0]["tables"]["rows"]) != count or consumed != maximum:
                raise ValueError("Materialized traversal differs from synthetic accounting")
            del materialized
            seen = 0
            started = time.perf_counter()
            for header, index, chunk, consumed in source_readings.iter_load(
                    ref, store, max_bytes=maximum, max_rows=count):
                if index != 0 or header["reading"] != ref or header["contract"] != contract_ref or chunk["input"] != input_ref:
                    raise ValueError("Incremental traversal differs from synthetic identity")
                seen += len(chunk["tables"]["rows"])
            seconds = time.perf_counter() - started
            if seen != count or consumed != maximum:
                raise ValueError("Incremental traversal differs from synthetic accounting")
            result = {"partitions": count, "index_bytes": index_bytes, "aggregate_bytes": consumed,
                      "materialized_seconds": load_seconds, "incremental_seconds": seconds, "rows": seen}
            results.append(result)
            print(json.dumps(result), flush=True)
    if pins != {str(Path(path).resolve()): sha(path) for path in files}:
        raise ValueError("Traversal runtime changed during measurement")
    report = {"scope": "synthetic repeated one-row partitions; metadata traversal cost only",
              "trials_per_size": 1, "results": results, "runtime_sha256": pins,
              "full_source_qualified": False}
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
