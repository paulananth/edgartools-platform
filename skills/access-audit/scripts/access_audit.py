#!/usr/bin/env python3
"""Audit who can do what on the data platform's systems, read-only, and grade each control PASS, FAIL or NOT_TESTED.

Usage: access_audit.py [--platform NAME ...] [--principal NAME ...] [--as-admin] [--json] [--repo PATH] [--list]
                       (exit 1 when any control fails)

The controls are platform-neutral objectives (audit_platforms/base.py); each platform is an adapter module that reads its
own evidence and grades the objectives it can. A platform is audited when its environment is set:
  snowflake   AUDIT_SNOWFLAKE_CONNECTION   a SnowCLI connection of the read-only auditor role
  postgres    DB_URL                       the read-only diagnostic login (reader.env)
  aws         AUDIT_AWS_PROFILE            a read-only audit profile (SecurityAudit)
  github      AUDIT_GITHUB_REPO            owner/name, read with the gh CLI
  workstation always                       client credential files, counts only
An administrator identity is refused unless --as-admin, which is then a finding. Output is counts and names of roles and
controls only: never an address, a password, a key or a value from the data. The script changes nothing.
To add a platform, add a module to audit_platforms/ with NAME, configured, collect, principals and controls.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_platforms.base import OBJECTIVES, control  # noqa: E402

PLATFORMS = ["snowflake", "postgres", "aws", "github", "workstation"]


def adapter(name: str):
    return importlib.import_module(f"audit_platforms.{name}")


def change_records(repo: Path, platform: str, names: list[str]) -> list[dict]:
    """Every access principal a platform audit found has a ticket and is defined in code (SOX program change)."""
    tickets = "\n".join(p.read_text(errors="replace") for p in (repo / ".scratch").rglob("*.md")) if (repo / ".scratch").exists() else ""
    code = "\n".join(p.read_text(errors="replace") for p in (repo / "infra").rglob("*.tf")) if (repo / "infra").exists() else ""
    ticketed = [n for n in names if n.lower() in tickets.lower()]
    coded = [n for n in names if n.lower() in code.lower()]
    return [control(platform, "CHG", len(ticketed) == len(names) and len(coded) == len(names),
                    {"principals": len(names), "with_ticket": len(ticketed), "in_terraform": len(coded)},
                    "Open a ticket with approver and back-out; define the principal in infra/terraform", tested=bool(names))]


def run(platforms: list[str], env, repo: Path, principals: list[str], as_admin: bool) -> list[dict]:
    return run_from_evidence({name: adapter(name).collect(env, as_admin) for name in platforms}, repo, principals)


def run_from_evidence(evidence_by_platform: dict, repo: Path, principals: list[str]) -> list[dict]:
    results = []
    for name, evidence in evidence_by_platform.items():
        module = adapter(name)
        results += module.controls(evidence)
        names = sorted(set(module.principals(evidence)) | set(principals if name == "snowflake" else []))
        if names:
            results += change_records(repo, name, names)
        for objective in ("ROT", "REV"):  # a signed record is read by a person
            if not any(r["id"] == f"{objective}.{name}" for r in results):
                results.append(control(name, objective, False, {}, "Record an owner and a date in the ticket", tested=False))
    return results


def matrix(results: list[dict], platforms: list[str]) -> list[str]:
    """Objective by platform: P pass, F fail, ? not tested, - the adapter has no test for it (a gap, not a pass)."""
    mark = {"PASS": "P", "FAIL": "F", "NOT_TESTED": "?"}
    lines = ["objective  " + "  ".join(f"{p[:11]:11}" for p in platforms)]
    for objective in OBJECTIVES:
        cells = []
        for p in platforms:
            found = [r for r in results if r["id"] == f"{objective}.{p}"]
            cells.append(f"{mark[found[0]['result']] if found else '-':11}")
        lines.append(f"{objective:10} " + "  ".join(cells))
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--platform", action="append", choices=PLATFORMS, help="audit only these (default: every configured one)")
    parser.add_argument("--principal", action="append", default=[], help="a Snowflake role or user to check for a change record (a new one the usage views lag on)")
    parser.add_argument("--as-admin", action="store_true", help="allow an administrator identity; the independence control then fails")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--list", action="store_true", help="show which platforms are configured")
    args = parser.parse_args(argv)
    configured = [p for p in PLATFORMS if adapter(p).configured(os.environ)]
    if args.list:
        print("configured:", ", ".join(configured) or "none")
        return 0
    platforms = args.platform or configured
    if not platforms:
        sys.exit("no platform is configured: set AUDIT_SNOWFLAKE_CONNECTION, DB_URL (reader.env), AUDIT_AWS_PROFILE or AUDIT_GITHUB_REPO")
    results = run(platforms, os.environ, Path(args.repo), args.principal, args.as_admin)
    if args.json:
        print(json.dumps(results))
    else:
        for r in sorted(results, key=lambda r: (r["result"] != "FAIL", r["result"] != "NOT_TESTED", r["id"])):
            print(f"{r['result']:10} {r['id']:18} {r['severity']:6} {r['title']}  [{r['refs']}]\n{'':10} evidence: {r['evidence']}"
                  + (f"\n{'':10} fix: {r['fix']}" if r["result"] != "PASS" else ""))
        print("\n".join(matrix(results, platforms)))
        counts = {k: sum(r["result"] == k for r in results) for k in ("PASS", "FAIL", "NOT_TESTED")}
        print(f"== {counts['PASS']} pass, {counts['FAIL']} fail, {counts['NOT_TESTED']} not tested")
    return 1 if any(r["result"] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
