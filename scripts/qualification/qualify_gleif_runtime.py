"""Qualify a complete cached GLEIF runtime scan against pinned independent evidence.

No network requests, publication, Rules activation or mastering writes. A receipt
is written only after count, canonical hash, compressed/expanded size and EOF
agree, with the actual runtime/native binary unchanged before and after scanning.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from edgar_warehouse.mdm.clean import gleif_source, gleif_publication, evidence as evidence_module, store as store_module
from edgar_warehouse.rules import source_engine, files
from edgar_warehouse.workers import source_attestation, source_stream, source_readings

MEMBERS = {"level1": "lei2", "relationships": "rr", "reporting_exceptions": "repex"}


def pinned_document(path, digest):
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != digest:
        raise ValueError(f"Pinned evidence changed: {path}")
    return json.loads(body)


def qualify(member, format_name, parity_path, parity_sha256, publisher_path, publisher_sha256):
    parity = pinned_document(parity_path, parity_sha256)
    api = pinned_document(publisher_path, publisher_sha256)
    if api["data"]["type"] != MEMBERS[member]:
        raise ValueError("Publisher member differs from requested member")
    publisher = api["data"]["full_file"][format_name]
    if parity["receipt"]["record_count"] != publisher["record_count"]:
        raise ValueError("Independent corpus count differs from publisher count")
    if format_name == "xml" and parity["publisher"] != publisher:
        raise ValueError("Independent XML evidence differs from publisher metadata")
    archive = parity["archive"]
    uri = urlparse(archive["uri"])
    if uri.scheme != "file" or uri.netloc:
        raise ValueError("Runtime qualification requires a local cached archive")
    path = Path(unquote(uri.path))
    if path.stat().st_size != publisher["size"]:
        raise ValueError("Cached compressed size differs from publisher size")
    # JSON has no header date: its release time is the manifest's publisher slot.
    # XML ContentDate comes from separately pinned capture-header evidence.
    content_date = (parity["content_date"] if format_name == "xml" else
                    api["data"]["publish_date"].replace(" ", "T") + "+00:00")
    metadata = {"format": format_name + ".zip", "cdf_version": publisher["cdf_version"],
                "content_date": content_date, "file_content": "GLEIF_FULL_PUBLISHED",
                "delta_start": None, "record_count": publisher["record_count"]}
    runtime = [Path(__file__), Path(gleif_source.__file__), Path(gleif_publication.__file__),
               Path(source_attestation.__file__), Path(source_stream.__file__), Path(source_readings.__file__),
               Path(files.__file__),
               Path(store_module.__file__), Path(evidence_module.__file__), *source_engine.runtime_files(),
               files.ROOT / "sources" / "gleif" / f"{member.replace('_', '-')}-{format_name}.yaml",
               parity_path, publisher_path]

    def evidence():
        return [{"path": str(p.resolve()), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                for p in runtime]

    before, observed, started = evidence(), 0, time.monotonic()

    def consume(row, index):
        nonlocal observed
        if index != observed:
            raise ValueError("Runtime callback ordinal differs from source order")
        observed += 1
        if observed % 100_000 == 0:
            print(json.dumps({"member": member, "format": format_name, "records": observed,
                              "seconds": round(time.monotonic() - started, 2)}), flush=True)

    with path.open("rb") as stream:
        receipt = gleif_publication.attest_publication(stream, member=member, metadata=metadata,
            expected_sha256=archive["sha256"], on_record=consume)
    if observed != receipt["record_count"] or observed != publisher["record_count"]:
        raise ValueError("Runtime callback/publication count differs")
    if receipt["canonical_source_hash"] != parity["canonical_source_hash"]:
        raise ValueError("Runtime canonical hash differs from independent full corpus")
    if receipt["expanded_bytes"] != parity["receipt"]["expanded_bytes"]:
        raise ValueError("Runtime expanded size differs from independent corpus")
    if receipt["compressed_bytes"] != publisher["size"]:
        raise ValueError("Runtime compressed size differs from publisher")
    if evidence() != before:
        raise ValueError("Runtime implementation or pinned evidence changed during scan")
    return {"archive": archive, "member": member, "format": format_name,
            "publisher_metadata": {"path": str(publisher_path), "sha256": publisher_sha256},
            "independent_full_parity_report": {"path": str(parity_path), "sha256": parity_sha256},
            "runtime_implementation": before, "metadata": metadata, "receipt": receipt,
            "callback_count": observed, "seconds": time.monotonic() - started,
            "scope": "complete configured runtime attestation matches pinned independent full corpus; "
                     "actual native extension hashed before/after; not installed mastering qualification"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--member", choices=MEMBERS, required=True)
    parser.add_argument("--format", choices=("json", "xml"), required=True)
    parser.add_argument("--parity-report", type=Path, required=True)
    parser.add_argument("--parity-sha256", required=True)
    parser.add_argument("--publisher-metadata", type=Path, required=True)
    parser.add_argument("--publisher-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = qualify(args.member, args.format, args.parity_report, args.parity_sha256,
                     args.publisher_metadata, args.publisher_sha256)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"complete": args.member, "format": args.format,
                      "records": result["callback_count"], "seconds": result["seconds"]}), flush=True)


if __name__ == "__main__":
    main()
