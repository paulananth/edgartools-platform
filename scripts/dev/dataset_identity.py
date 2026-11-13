#!/usr/bin/env python3
"""Fail on a rules change that moves something a store has registered under the same name.

Two kinds, both refused by the store at activation (which CI never reaches):
- a source change that moves a Dataset Contract's identity under the same dataset code;
- a merge rule whose steps changed under the same rule id and version.

A registered contract's record key and identifiers are immutable within one source code ("register a new source
code"), and so is a rule version ("Rule version already registered with different steps"). OpenFIGI, 2026-11-10: an
identifier was added under the same code, merged green, and refused on the first activation; then the rules that
named the moved source codes were refused too. This reads each changed source at the base and now and asks the
store's own `protected_change`, and compares each merge rule with its version at the base.

Usage: PYTHONPATH=. python scripts/dev/dataset_identity.py [base, default origin/main]
Exit 0: none moved. Exit 1: each dataset code and the parts that moved.
"""
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from edgar_warehouse.mdm.store import Conflict, protected_change
from edgar_warehouse.rules import files

SOURCES = "rules/sources"


def changed(base: str) -> list[str]:
    names = subprocess.run(["git", "diff", "--name-only", base, "--", SOURCES], capture_output=True, text=True,
                           check=True).stdout.split()
    return sorted({Path(n).parts[2] for n in names})


def moved(name: str, before_root: Path) -> list[str]:
    """The dataset codes of source `name` whose identity differs from the base's."""
    found = []
    try:
        before = files.source(name, before_root, steps=False)  # only its Dataset Contracts are compared
    except (OSError, files.RulesFileError):  # a new source: nothing registered under its codes yet
        return found
    after = files.source(name)
    for code, current in (before.get("dataset_contracts") or {}).items():
        proposed = (after.get("dataset_contracts") or {}).get(code)
        if proposed is None:
            continue  # retired, not moved
        try:
            protected_change(current["contract"], proposed["contract"])
        except Conflict as error:
            found.append(f"{name} {code}: {str(error).split(': ', 1)[-1]}")
    return found


def rules_moved(before_root: Path) -> list[str]:
    """The merge rules whose steps differ from the base's under the same kind, rule id and version."""
    def by_key(policy):
        return {(kind, r["rule_id"], str(r.get("version"))): r
                for kind, block in (policy.get("kinds") or {}).items() for r in block.get("rules") or []}
    try:
        before = by_key(files.policy(before_root))
    except (OSError, files.RulesFileError):
        return []
    after = by_key(files.policy())
    return [f"{kind}/{rid}@{version}: its steps changed under the same version"
            for (kind, rid, version), rule in sorted(after.items()) if (kind, rid, version) in before
            and before[(kind, rid, version)] != rule]


def main(argv: list[str]) -> int:
    base = argv[1] if len(argv) > 1 else "origin/main"
    names = changed(base)
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        archive = subprocess.run(["git", "archive", base, "rules"], capture_output=True, check=True).stdout
        with tarfile.open(fileobj=__import__("io").BytesIO(archive)) as tar:
            tar.extractall(tmp, filter="data")
        for name in names:
            problems += moved(name, Path(tmp) / "rules")
        problems += rules_moved(Path(tmp) / "rules")
    for problem in problems:
        print(f"dataset_identity: {problem}; register a new dataset code (v1 -> v2) or a new rule version "
              "(a descriptive label) instead of changing it", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
