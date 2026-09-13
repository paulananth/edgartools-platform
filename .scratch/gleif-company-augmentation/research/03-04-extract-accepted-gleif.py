#!/usr/bin/env python3
"""Extract fixed GLEIF records touching Ticket 02's accepted LEIs.

The three Golden Copy archives are streamed without extraction. Outputs are
local research artifacts; this script performs no network or production I/O.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from collections.abc import Iterable
from pathlib import Path

import orjson

ROOT = Path(__file__).resolve().parent


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def accepted_leis() -> set[str]:
    result: set[str] = set()
    with (ROOT / "02-cohort-dispositions.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row["disposition"] == "accepted_same_legal_entity":
                result.add(row["accepted_lei"])
    if len(result) != 308:
        raise RuntimeError(f"expected 308 accepted LEIs, found {len(result)}")
    return result


def scalar(value: object) -> str | None:
    if isinstance(value, dict):
        value = value.get("$")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def strings(value: object) -> Iterable[str]:
    if isinstance(value, dict):
        if set(value) == {"$"}:
            if text := scalar(value):
                yield text
            return
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)
    elif isinstance(value, str):
        yield value


def record_leis(record: dict, accepted: set[str]) -> set[str]:
    return {value for value in strings(record) if value in accepted}


def stream_records(handle, wrapper: str):
    """Stream GLEIF's pretty-printed top-level record array."""
    marker = f'"{wrapper}":['.encode()
    in_records = False
    record_lines: list[bytes] = []
    for line in handle:
        stripped = line.rstrip(b"\r\n")
        if not in_records:
            if marker in stripped:
                in_records = True
            continue
        if not record_lines:
            if stripped == b"{":
                record_lines.append(line)
                continue
            if stripped == b"]}" or not stripped.strip():
                continue
            raise RuntimeError(f"unexpected material between records: {stripped[:120]!r}")
        record_lines.append(line)
        if stripped == b"}]}":
            payload = b"".join(record_lines).rstrip(b"\r\n")[:-2]
            yield orjson.loads(payload)
            return
        if stripped in {b"}", b"},"}:
            payload = b"".join(record_lines)
            if stripped == b"},":
                payload = payload.rstrip(b"\r\n")[:-1]
            yield orjson.loads(payload)
            record_lines.clear()
    if record_lines:
        raise RuntimeError(f"truncated {wrapper} record")
    if not in_records:
        raise RuntimeError(f"JSON did not contain a {wrapper} array")


def stream_archive(path: Path, wrapper: str):
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) != 1:
            raise RuntimeError(f"expected one member in {path.name}, found {len(members)}")
        member = members[0].filename
    process = subprocess.Popen(
        ["unzip", "-p", str(path), member],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdout is None or process.stderr is None:
        raise RuntimeError(f"failed to stream {path.name}")
    try:
        with process.stdout as handle:
            yield from stream_records(handle, wrapper)
        stderr = process.stderr.read().decode(errors="replace")
        status = process.wait()
        if status != 0:
            raise RuntimeError(f"unzip failed for {path.name}: {stderr[-2000:]}")
    except BaseException:
        process.terminate()
        process.wait()
        raise
    finally:
        process.stderr.close()


def extract(source: Path, destination: Path, accepted: set[str], wrapper: str) -> dict:
    scanned = 0
    retained = 0
    touched: set[str] = set()
    digest = hashlib.sha256()
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        for record in stream_archive(source, wrapper):
            scanned += 1
            matched = record_leis(record, accepted)
            if not matched:
                continue
            row = {"accepted_leis_touched": sorted(matched), "record": record}
            line = canonical_json(row) + "\n"
            handle.write(line)
            digest.update(line.encode())
            retained += 1
            touched.update(matched)
            if scanned % 500_000 == 0:
                print(
                    f"{source.name}: scanned={scanned:,} retained={retained:,}",
                    file=sys.stderr,
                    flush=True,
                )
    return {
        "source": source.name,
        "destination": destination.name,
        "records_scanned": scanned,
        "records_retained": retained,
        "accepted_leis_touched": len(touched),
        "sha256": digest.hexdigest(),
    }


def self_test() -> None:
    import io

    accepted = {"A" * 20}
    record = {"Relationship": {"StartNode": {"NodeID": {"$": "A" * 20}}}}
    assert record_leis(record, accepted) == accepted
    assert record_leis({"LEI": {"$": "B" * 20}}, accepted) == set()
    parsed = list(stream_records(io.BytesIO(b'{"relations":[\n{\n"x": 1\n}]}'), "relations"))
    assert parsed == [{"x": 1}]
    print("self-test passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--family",
        choices=("level1", "relationship", "exception", "all"),
        default="all",
    )
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return

    accepted = accepted_leis()
    families = {
        "level1": (
            ROOT / "01-20260911-1600-gleif-goldencopy-lei2-golden-copy.json.zip",
            ROOT / "03-accepted-level1-records.jsonl",
            "records",
        ),
        "relationship": (
            ROOT / "01-20260911-1600-gleif-goldencopy-rr-golden-copy.json.zip",
            ROOT / "04-accepted-relationship-records.jsonl",
            "relations",
        ),
        "exception": (
            ROOT / "01-20260911-1600-gleif-goldencopy-repex-golden-copy.json.zip",
            ROOT / "04-accepted-exception-records.jsonl",
            "exceptions",
        ),
    }
    selected = families if args.family == "all" else {args.family: families[args.family]}
    manifest = {
        "manifest_version": "gleif-accepted-record-extract-v1",
        "accepted_lei_count": len(accepted),
        "families": {
            family: extract(source, destination, accepted, wrapper)
            for family, (source, destination, wrapper) in selected.items()
        },
    }
    output = ROOT / f"03-04-extract-manifest-{args.family}.json"
    output.write_text(canonical_json(manifest) + "\n", encoding="utf-8")
    print(canonical_json(manifest))


if __name__ == "__main__":
    main()
