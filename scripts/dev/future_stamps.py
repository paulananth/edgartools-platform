#!/usr/bin/env python3
"""Fail on an ET stamp later than the clock in what this branch adds under .scratch/.

A ticket stamps each finished part with its completion time ("2026-11-01 17:25 ET").
A stamp later than now was guessed, not read from the clock (ticket 155).

Usage: python3 scripts/dev/future_stamps.py [base, default origin/main]
Exit 0: none. Exit 1: each file and stamp later than now.
"""
import re
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
STAMP = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d) (\d\d):(\d\d) ET\b")
WHERE = ".scratch"


def future(text: str, now: datetime) -> list[tuple[int, str]]:
    """(line number, stamp) of each ET stamp in `text` later than `now`."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        for match in STAMP.finditer(line):
            try:
                when = datetime(*map(int, match.groups()), tzinfo=ET)
            except ValueError:  # 2026-02-31 is no date
                continue
            if when > now:
                found.append((number, match.group(0)))
    return found


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def added(base: str) -> dict[str, str]:
    """The lines this branch adds under .scratch/ by file: tracked changes against `base`, and untracked files."""
    files: dict[str, list[str]] = {}
    current = None
    for line in _git("diff", "--unified=0", base, "--", WHERE).splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("+") and not line.startswith("+++") and current:
            files.setdefault(current, []).append(line[1:])
    for path in _git("ls-files", "--others", "--exclude-standard", "--", WHERE).split():
        with open(path, encoding="utf-8", errors="replace") as handle:
            files[path] = handle.read().splitlines()
    return {path: "\n".join(lines) for path, lines in files.items()}


def main(argv: list[str]) -> int:
    now = datetime.now(ET)
    late = [(path, stamp) for path, text in added(argv[1] if len(argv) > 1 else "origin/main").items()
            for _, stamp in future(text, now)]
    for path, stamp in late:
        print(f"future_stamps: {path}: {stamp} is later than now ({now:%Y-%m-%d %H:%M} ET); read the clock "
              "(TZ=America/New_York date) and stamp that", file=sys.stderr)
    return 1 if late else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
