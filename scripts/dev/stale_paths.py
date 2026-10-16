"""List the repository paths a guide names that do not exist (ticket 85).

Reads each file given (default: CLAUDE.md and AGENTS.md), takes every token
that looks like a repository path (it has a slash and starts with a top-level
folder of this repository; a bare top-level file name is not checked), and
prints the ones missing, with their line numbers. Skipped: a git-ignored path
(a local backup folder) and a placeholder (`<source>`, `*`, `{dev,prod}`).
Exit 1 when any is missing. Run from the repository root:

    python scripts/dev/stale_paths.py [FILE ...]
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOP = {p.name for p in ROOT.iterdir() if not p.name.startswith(".")} | {".scratch", ".planning", ".github"}
TOKEN = re.compile(r"(?<![\w/.~-])((?:\.?[A-Za-z0-9_-]+/)+[A-Za-z0-9_.*<>{}-]*)")


def ignored(path: str) -> bool:
    """A path git ignores (a local backup folder) is never in a checkout."""
    return subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode == 0


def missing(text: str) -> list[tuple[int, str]]:
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        for raw in TOKEN.findall(line):
            path = raw.rstrip(".,:;)")
            if path.split("/")[0] not in TOP or any(c in path for c in "*<>{}"):
                continue
            if not (ROOT / path).exists() and not ignored(path):
                out.append((n, path))
    return out


def main(argv: list[str]) -> int:
    found = False
    for name in argv or ["CLAUDE.md", "AGENTS.md"]:
        for n, path in missing((ROOT / name).read_text()):
            found = True
            print(f"{name}:{n}: {path}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
