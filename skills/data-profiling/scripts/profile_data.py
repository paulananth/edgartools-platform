"""Profile a data set: python profile_data.py --help (run from this folder, with DuckDB).

    uv run --with duckdb --with pyyaml python profile_data.py run --name <set> \
        --input <part>=<file|folder|zip|db file|env:VARIABLE> ... --out <folder>
    uv run --with duckdb --with pyyaml python profile_data.py approve --findings <folder>/findings.yaml \
        --by <operator> --words "<their exact words>"
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from profiling import inputs, report, run  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="profile_data.py", description="Profile a data set for the data-profiling skill")
    commands = parser.add_subparsers(dest="command", required=True)
    profile = commands.add_parser("run", help="Profile every input; write findings.yaml and REPORT.md")
    profile.add_argument("--name", required=True, help="the operator's name for the data set")
    profile.add_argument("--input", action="append", required=True, metavar="NAME=LOCATION",
                         help="a file, folder, zip, database file, or env:VARIABLE holding a read-only database address")
    profile.add_argument("--out", required=True, type=Path)
    profile.add_argument("--limit-gb", type=float, default=inputs.DEFAULT_LIMIT / inputs.GB)
    profile.add_argument("--sample", type=int, default=inputs.SAMPLE_RECORDS)
    profile.add_argument("--seed", type=int, default=0)
    profile.add_argument("--kinds", default="", help="existing master kinds, comma separated")
    approve = commands.add_parser("approve", help="Record the operator's approval, in their exact words")
    approve.add_argument("--findings", required=True, type=Path)
    approve.add_argument("--by", required=True)
    approve.add_argument("--words", required=True)
    args = parser.parse_args(argv)

    if args.command == "run":
        sources = dict(item.split("=", 1) for item in args.input)
        findings = run.profile_inputs(sources, args.name, int(args.limit_gb * inputs.GB), args.sample, args.seed,
                                      tuple(k for k in args.kinds.split(",") if k), args.out / ".work")
        data, text = report.write(findings, args.out)
        print(f"wrote {data} and {text}")
        return 0
    findings = yaml.safe_load(args.findings.read_text(encoding="utf-8"))
    findings["approval"] = {"status": "approved", "approved_by": args.by, "approved_words": args.words,
                            "approved_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    args.findings.write_text(yaml.safe_dump(findings, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
    print(f"approved {args.findings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
