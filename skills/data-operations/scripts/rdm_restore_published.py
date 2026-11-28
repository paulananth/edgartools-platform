#!/usr/bin/env python3
"""Restore every published RDM code set from git into an empty RDM store, and check each pin.

Usage (source the store's worker.env first):
    python rdm_restore_published.py

Each version under rules/reference/published/<code set>/<version> is drafted from its
canonical.jsonl, approved under the operator's standing ruling (no approval is asked), published, and its sha256 compared with
its pin.json. A code set holds one version, so none supersedes another. Run it
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
    return body


def cli(*args: str) -> str:
    done = subprocess.run([sys.executable, "-c", "from edgar_warehouse.cli import main; raise SystemExit(main())", *args],
                          capture_output=True, text=True)
    if done.returncode:
        raise SystemExit(f"rdm {args[0]} failed: {done.stderr.strip()[-300:]}")
    return done.stdout


# Operator ruling: "RDM codes should be auto loaded no approval needed". A published version is a file in git with its
# pin, so restoring it changes nothing the pin does not check; the approval record names this ruling.
STANDING_BY = "operator standing ruling"  # not the drafter ("restore from git"): the store refuses a self-approval
STANDING_WORDS = "RDM codes should be auto loaded no approval needed (operator standing ruling)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--by", default=STANDING_BY, help="Who the approval record names (default: the standing ruling)")
    parser.add_argument("--words", default=STANDING_WORDS, help="The words the approval record holds (default: the standing ruling)")
    parser.add_argument("--progress-run-id", help="Publish code-set progress to a hosted clear run")
    args = parser.parse_args()
    code_sets = [path for path in sorted(PUBLISHED.iterdir()) if path.is_dir()]
    record = set_total = set_state = None
    if args.progress_run_id:
        from edgar_warehouse.hosted_store_clear_progress import record_unit, set_step_state, set_step_total
        record, set_state, set_total = record_unit, set_step_state, set_step_total
        if not code_sets:
            set_total(args.progress_run_id, "rdm", 1)
            set_state(args.progress_run_id, "rdm", "failed")
            record(args.progress_run_id, "rdm", "no-published-sets", "failed")
            return 1
        set_total(args.progress_run_id, "rdm", len(code_sets))
        set_state(args.progress_run_id, "rdm", "running")
    differing = []
    with tempfile.TemporaryDirectory() as tmp:
        for code_set in code_sets:
            if record:
                record(args.progress_run_id, "rdm", code_set.name, "running")
            set_ok = True
            try:
                for version in sorted((v.name for v in code_set.iterdir() if v.is_dir()), key=int):
                    draft = Path(tmp) / f"{code_set.name}-{version}.json"
                    draft.write_text(json.dumps(draft_body(code_set.name, version)))
                    cli("rdm", "draft", "--file", str(draft))
                    cli("rdm", "approve", "--by", args.by, "--words", args.words, code_set.name, version)
                    sha = json.loads(cli("rdm", "publish", "--out", str(Path(tmp) / "out"), code_set.name, version))["sha256"]
                    pin = json.loads((code_set / version / "pin.json").read_text())["sha256"]
                    matches_pin = sha == pin
                    print(code_set.name, version, "pin ok" if matches_pin else "PIN DIFFERS", flush=True)
                    if not matches_pin:
                        differing.append(f"{code_set.name} {version}")
                        set_ok = False
            except SystemExit:
                if record:
                    record(args.progress_run_id, "rdm", code_set.name, "failed")
                raise
            except Exception:
                if record:
                    record(args.progress_run_id, "rdm", code_set.name, "failed")
                raise
            if record:
                record(args.progress_run_id, "rdm", code_set.name, "completed" if set_ok else "failed")
    return 1 if differing else 0


if __name__ == "__main__":
    raise SystemExit(main())
