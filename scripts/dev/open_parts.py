#!/usr/bin/env python3
"""Fail on a ticket marked resolved that still has an open part, in the tickets this branch changes.

CLAUDE.md: "Any unchecked part means the report says 'incomplete'". A part that is skipped or moved stays on the
list as `- [ ] ~~part~~ deferred to <ticket>: <why>`, which this check lets pass (ticket 157).

Usage: python3 scripts/dev/open_parts.py [base, default origin/main]
Exit 0: none. Exit 1: each file and open part.
"""
import re
import subprocess
import sys

TICKETS = ".scratch/*/issues/*.md"
RESOLVED = re.compile(r"^(Type:.*)?\bStatus: resolved\b(?![-\w])", re.IGNORECASE)
OPEN = re.compile(r"^\s*- \[ \] (?!~~)")


def open_parts(text: str) -> list[tuple[int, str]]:
    """(line number, line) of each open part that is not deferred, when the ticket's status says resolved."""
    lines = text.splitlines()
    if not any(RESOLVED.match(line) for line in lines):
        return []
    fenced, found = False, []
    for number, line in enumerate(lines, 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and OPEN.match(line):
            found.append((number, line.strip()))
    return found


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def changed(base: str) -> list[str]:
    """Ticket files this branch changes against `base`, plus untracked ones."""
    # From the merge-base, so tickets that `base` gained since this branch was cut are not this branch's.
    fork = _git("merge-base", base, "HEAD").strip()
    tracked = _git("diff", "--name-only", "--diff-filter=d", fork, "--", TICKETS).split()
    return sorted({*tracked, *_git("ls-files", "--others", "--exclude-standard", "--", TICKETS).split()})


def main(argv: list[str]) -> int:
    late = []
    for path in changed(argv[1] if len(argv) > 1 else "origin/main"):
        with open(path, encoding="utf-8", errors="replace") as handle:
            late += [(path, number, line) for number, line in open_parts(handle.read())]
    for path, number, line in late:
        print(f"open_parts: {path}:{number}: {line} (the ticket says resolved; tick the part, or mark it "
              "`- [ ] ~~part~~ deferred to <ticket>: <why>`)", file=sys.stderr)
    return 1 if late else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
