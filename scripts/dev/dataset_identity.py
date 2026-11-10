#!/usr/bin/env python3
"""Fail on a source change that moves a Dataset Contract's identity under the same dataset code.

A registered contract's record key and identifiers are immutable within one source code: the store refuses
the change at activation ("register a new source code"), which CI never reaches (OpenFIGI, 2026-11-10: an
identifier was added under the same code, merged green, and refused on the first activation). This reads each
changed source at the base and now and asks the store's own `protected_change`.

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
        before = files.source(name, before_root)
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


def main(argv: list[str]) -> int:
    base = argv[1] if len(argv) > 1 else "origin/main"
    names = changed(base)
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        if names:
            archive = subprocess.run(["git", "archive", base, SOURCES], capture_output=True, check=True).stdout
            with tarfile.open(fileobj=__import__("io").BytesIO(archive)) as tar:
                tar.extractall(tmp, filter="data")
        for name in names:
            problems += moved(name, Path(tmp) / "rules")
    for problem in problems:
        print(f"dataset_identity: {problem}; register a new dataset code (v1 -> v2) instead of changing it",
              file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
