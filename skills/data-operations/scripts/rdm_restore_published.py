#!/usr/bin/env python3
"""Restore every published RDM code set from git into an empty RDM store, and check each pin.

Usage (source the store's worker.env first):
    python rdm_restore_published.py --by <name> --words "<their exact words>"

Each version under rules/reference/published/<code set>/<version> is drafted from its
canonical.jsonl, approved in the operator's words, published, and its sha256 compared with
its pin.json. Versions run in order, so a later version supersedes the one before. Run it
on an empty RDM: a version already published stops the run at that version. A hash that
differs from its pin exits 1 after naming it.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from edgar_warehouse.rules import files

PUBLISHED = files.ROOT / "reference" / "published"
CODE_KEYS = ("code", "label", "definition", "parent_code", "valid_from", "valid_to", "status", "invalid_reason")
OPTIONAL_KEYS = ("value", "unit", "properties")  # kept only when the published row holds one


def draft_body(name: str, version: str) -> dict:
    rows = [json.loads(line) for line in (PUBLISHED / name / version / "canonical.jsonl").read_text().splitlines() if line.strip()]
    levels = list(dict.fromkeys(r["level"] for r in rows if r["level"] is not None))
    body = {
        "code_set": {"code_set": name, "name": name.replace("-", " "), "definition": "", "authority": "", "steward": ""},
        "version": version, "created_by": "restore from git",
        "codes": [{**{k: r[k] for k in CODE_KEYS}, **{k: r[k] for k in OPTIONAL_KEYS if r.get(k) is not None}} for r in rows],
        "labels": [{"code": r["code"], "language": a, "kind": b, "label": c} for r in rows for a, b, c in r["labels"]],
        "levels": [{"depth": i + 1, "name": n, "definition": ""} for i, n in enumerate(levels)],
        "crosswalk": [{"from_code": r["code"], "to_set": t, "to_version": v, "to_code": c, "match_type": m}
                      for r in rows for t, v, c, m in r["crosswalk"]],
    }
    if int(version) > 1:
        body["supersedes"] = str(int(version) - 1)
    return body


def cli(*args: str) -> str:
    done = subprocess.run([sys.executable, "-c", "from edgar_warehouse.cli import main; raise SystemExit(main())", *args],
                          capture_output=True, text=True)
    if done.returncode:
        raise SystemExit(f"rdm {args[0]} failed: {done.stderr.strip()[-300:]}")
    return done.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--by", required=True)
    parser.add_argument("--words", required=True, help="The operator's exact words approving the restore")
    args = parser.parse_args()
    differing = []
    with tempfile.TemporaryDirectory() as tmp:
        for code_set in sorted(PUBLISHED.iterdir()):
            for version in sorted((v.name for v in code_set.iterdir()), key=int):
                draft = Path(tmp) / f"{code_set.name}-{version}.json"
                draft.write_text(json.dumps(draft_body(code_set.name, version)))
                cli("rdm", "draft", "--file", str(draft))
                cli("rdm", "approve", "--by", args.by, "--words", args.words, code_set.name, version)
                sha = json.loads(cli("rdm", "publish", "--out", str(Path(tmp) / "out"), code_set.name, version))["sha256"]
                pin = json.loads((code_set / version / "pin.json").read_text())["sha256"]
                print(code_set.name, version, "pin ok" if sha == pin else "PIN DIFFERS", flush=True)
                if sha != pin:
                    differing.append(f"{code_set.name} {version}")
    return 1 if differing else 0


if __name__ == "__main__":
    raise SystemExit(main())
