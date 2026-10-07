"""Authenticate a complete cached ZIP and compare every framed typed record.

The independent decoder is ijson, with no retired platform parser imports.
Observed counts without --expected-records are structural proof only, not
publisher metadata evidence. Neither path publishes or writes master data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import time
import zipfile
from pathlib import Path

import ijson

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules.source_engine import stream_json_array


def implementation_evidence():
    from edgar_warehouse.rules import source_engine
    paths = [Path(__file__), *source_engine.runtime_files()]
    return [{"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths]


def equal(left, right, *, key_order=True):
    if type(left) is not type(right): return False
    if isinstance(left, dict): return (list(left) == list(right) if key_order else left.keys() == right.keys()) and all(equal(left[key], right[key], key_order=key_order) for key in left)
    if isinstance(left, list): return len(left) == len(right) and all(equal(a, b, key_order=key_order) for a, b in zip(left, right))
    if isinstance(left, float): return left.hex() == right.hex()
    return left == right


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def qualify(path, sha256, wrapper, expected_records=None):
    if expected_records is not None and (type(expected_records) is not int or not 0 <= expected_records <= 10_000_000):
        raise ValueError("Expected record count must be 0..10000000")
    started = time.monotonic()
    implementation = implementation_evidence()
    ref = {"uri": Path(path).resolve().as_uri(), "sha256": sha256}
    count = 0
    native_hash, independent_hash = hashlib.sha256(), hashlib.sha256()
    with Artifacts().verified_stream(ref, max_bytes=1024**3) as snapshot, tempfile.TemporaryFile() as other:
        # On macOS duplicated file descriptors share offsets. Use independent
        # authenticated compressed snapshots, without expanding either to disk.
        shutil.copyfileobj(snapshot, other, length=1024**2)
        snapshot.seek(0); other.seek(0)
        with zipfile.ZipFile(snapshot) as native_zip, zipfile.ZipFile(other) as independent_zip:
            infos = native_zip.infolist()
            if len(infos) != 1 or infos[0].is_dir() or infos[0].flag_bits & 1 or infos[0].file_size > 16*1024**3:
                raise ValueError("Requires one bounded unencrypted ZIP member")
            with native_zip.open(infos[0]) as native, independent_zip.open(independent_zip.infolist()[0]) as independent:
                records = iter(ijson.items(independent, wrapper + ".item", use_float=True))
                def consume(row, index):
                    nonlocal count
                    old = next(records)
                    if not equal(row, old): raise ValueError(f"Typed/key-order difference at record {index}")
                    native_hash.update(canonical(row) + b"\n")
                    independent_hash.update(canonical(old) + b"\n")
                    count += 1
                    if count % 100000 == 0:
                        print(json.dumps({"archive":Path(path).name, "records":count, "seconds":round(time.monotonic()-started,2)}), flush=True)
                receipt = stream_json_array(native, wrapper=wrapper, on_record=consume, max_bytes=16*1024**3,
                    max_record=1024**2, max_records=10_000_000, max_depth=64,
                    min_integer=-(2**63)+1, record_encoding="python")
                exhausted = object()
                if next(records, exhausted) is not exhausted: raise ValueError("Independent decoder has additional records")
                if receipt["record_count"] != count or receipt["expanded_bytes"] != infos[0].file_size:
                    raise ValueError("Source count/expanded bytes disagreement")
                if expected_records is not None and count != expected_records:
                    raise ValueError("Pinned publication count disagreement")
                if native_hash.digest() != independent_hash.digest(): raise ValueError("Canonical hash disagreement")
    if implementation_evidence() != implementation:
        raise ValueError("Qualification implementation changed during scan")
    return {"archive":ref, "wrapper":wrapper, "receipt":receipt, "canonical_source_hash":native_hash.hexdigest(),
            "implementation": implementation,
            "typed_order_differences":0, "expected_records":expected_records,
            "seconds":time.monotonic()-started,
            "scope":"complete authenticated cached JSON framing and independent decoder comparison; publisher count is proved only when separately supplied"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--wrapper", required=True)
    parser.add_argument("--expected-records", type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.expected_records is not None and not 0 <= args.expected_records <= 10_000_000:
        parser.error("expected record count must be 0..10000000")
    report = qualify(args.archive, args.sha256, args.wrapper, args.expected_records)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__": main()
