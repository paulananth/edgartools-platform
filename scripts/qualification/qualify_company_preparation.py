"""Qualify the actual bounded preparation caller using frozen local evidence.

No census construction, acquisition, database writes, activation or deployment.
The old implementation is test-only and never packaged with the runtime.
"""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from edgar_warehouse.mdm.clean import (
    company_prepare,
    company_source,
    name_census,
    names,
    cascade,
)
from edgar_warehouse.workers import (
    source_read,
    source_combine,
    source_parquet,
    source_staging,
)
from tests.support import retired_company_preparation as historical


def sha(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(65536), b""):
            checksum.update(part)
    return checksum.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "landing-root",
        "landing-manifest",
        "ticker-manifest",
        "name-census",
        "artifact-root",
        "report",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--revision", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error("--limit must be 1..1000")
    root = args.landing_root.resolve()
    inputs = [args.landing_manifest, args.ticker_manifest, args.name_census]
    for path in (args.landing_manifest, args.ticker_manifest):
        inputs += [
            root / member["relative_path"]
            for member in json.loads(path.read_bytes())["tables"]
        ]
    rules = company_prepare.ROOT
    code = [
        Path(__file__),
        Path(company_prepare.__file__),
        *[
            Path(module.__file__)
            for module in (company_source, name_census, names, cascade)
        ],
        Path(historical.__file__),
        Path(source_read.__file__),
        Path(source_combine.__file__),
        Path(source_parquet.__file__),
        Path(source_staging.__file__),
        *source_read.runtime_files(),
        *source_combine.runtime_files(),
        *[
            rules / name
            for name in (
                "landed-preparation.yaml",
                "combine-landed.yaml",
                "census.yaml",
            )
        ],
    ]
    pins = {str(path.resolve()): sha(path) for path in [*inputs, *code]}
    args.artifact_root.mkdir(parents=True, exist_ok=False)
    request = {
        name: str(getattr(args, name))
        for name in (
            "landing_root",
            "landing_manifest",
            "ticker_manifest",
            "name_census",
        )
    }
    request.update(limit=args.limit, as_of=args.as_of, revision=args.revision)
    started = time.monotonic()
    baseline = historical.prepare_company_bundle(
        **request, output=str(args.artifact_root / "historical")
    )
    report = company_prepare.prepare_company_bundle(
        **request, output=str(args.artifact_root / "configured")
    )
    for name in baseline["files"]:
        if (args.artifact_root / "historical" / name).read_bytes() != (
            args.artifact_root / "configured" / name
        ).read_bytes():
            raise ValueError("Historical caller output differs: " + name)
    if baseline["scope"] != report["scope"]:
        raise ValueError("Historical scope differs")
    if (
        company_prepare.prepare_company_bundle(
            **request, output=str(args.artifact_root / "configured")
        )
        != report
    ):
        raise ValueError("Retry differs")
    verification = company_prepare.verify_company_bundle(
        str(args.artifact_root / "configured"), expected=report
    )
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json,sys; from edgar_warehouse.mdm.clean.company_prepare import verify_company_bundle; "
            "print(json.dumps(verify_company_bundle(sys.argv[1],expected=json.load(sys.stdin))))",
            str(args.artifact_root / "configured"),
        ],
        input=json.dumps(report),
        capture_output=True,
        text=True,
        check=True,
    )
    if json.loads(child.stdout) != verification:
        raise ValueError("Independent-process replay differs")
    if pins != {path: sha(Path(path)) for path in pins}:
        raise ValueError("Inputs or implementation changed during qualification")
    result = {
        "scope": report["scope"],
        "exact_original_bundle_bytes": True,
        "unchanged_retry": True,
        "separate_process_readback_verified": True,
        "frozen_census_sha256": sha(args.name_census),
        "pins": pins,
        "inventory_sha256": sha(args.artifact_root / "configured/inventory.json"),
        "artifact_root": str(args.artifact_root.resolve()),
        "elapsed_seconds": time.monotonic() - started,
        "installed_bundle_qualified": False,
        "whole_population_mastering_qualified": False,
        "census_construction_qualified": False,
    }
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "pins"}))


if __name__ == "__main__":
    main()
