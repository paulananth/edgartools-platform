#!/usr/bin/env python3
"""What does a source's load need from the operator? Read-only, from the rules files.

A target that takes run inputs declares them under `run:` in its source's rules (`facts` are values given with
`--fact name=value`, `files` are given with `--file name=path`). This prints, for each source and target, those
names and the comment block written above the target, which is where the rules say how each input is produced.

    run_inputs.py [--rules rules/sources] [source ...]

Names and comments only; a rules file holds no value from the data.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml


def targets_with_inputs(document: dict) -> dict[str, dict]:
    """target name -> {"facts": [...], "files": [...]} for each target of the document that declares `run`."""
    targets = ((document.get("bookkeeping") or {}).get("targets")) or {}
    found = {}
    for name, target in targets.items():
        run = (target or {}).get("run") or {}
        if run.get("facts") or run.get("files"):
            found[name] = {"facts": list(run.get("facts") or []), "files": list(run.get("files") or [])}
    return found


def comment_above(lines: list[str], target: str) -> list[str]:
    """The contiguous `#` lines directly above the line that opens `target:`, in reading order."""
    for index, line in enumerate(lines):
        if line.strip() == f"{target}:":
            block = []
            for above in reversed(lines[:index]):
                if not above.strip().startswith("#"):
                    break
                block.append(above.strip().lstrip("#").strip())
            return list(reversed(block))
    return []


def mentions(lines: list[str], name: str, limit: int = 3) -> list[str]:
    """Up to `limit` comment lines of the file that name the input, as a whole word."""
    word = re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)")
    found = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") and word.search(stripped):
            found.append(stripped.lstrip("#").strip())
        if len(found) == limit:
            break
    return found


def describe(source: str, text: str) -> list[str]:
    document = yaml.safe_load(text) or {}
    lines = text.splitlines()
    out = []
    for target, inputs in targets_with_inputs(document).items():
        out.append(f"{source} / {target}")
        out.append(f"  facts: {', '.join(inputs['facts']) or 'none'}")
        out.append(f"  files: {', '.join(inputs['files']) or 'none'}")
        block = [line for line in comment_above(lines, target) if line]
        out += [f"  | {line}" for line in block]
        if not block:
            for name in [*inputs["facts"], *inputs["files"]]:
                for line in mentions(lines, name) or ["(no comment in the rules says how it is produced)"]:
                    out.append(f"  | {name}: {line}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rules", type=Path, default=Path("rules/sources"))
    parser.add_argument("source", nargs="*", help="a source (default: every source that takes run inputs)")
    args = parser.parse_args()
    shown = 0
    for path in sorted(args.rules.glob("*/source.yaml")):
        source = path.parent.name
        if args.source and source not in args.source:
            continue
        lines = describe(source, path.read_text(encoding="utf-8"))
        shown += bool(lines)
        print("\n".join(lines))
    if not shown:
        print("No source takes run inputs" if not args.source else "None of those sources takes run inputs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
