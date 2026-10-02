"""Producer workflow planning; planning never opens a database connection.

Validation and deployment ran the work in this process, through Bookkeeping's
callbacks. They return in mastering to-do 20c, with the work done by workers
in their own processes (to-do 20a removed the callbacks).
"""

from __future__ import annotations

import json
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.config import Blocked, canonical, digest, validate, worklist
from edgar_warehouse.bookkeeping.clean.feeds import resolve_feed
from edgar_warehouse.rules.files import load


def plan(
    *, source: str, feed: str, target: str, inputs: dict, rules_root: Path
) -> dict:
    binding = resolve_feed(rules_root, source, feed)
    feed = binding["feed"]
    document = load(rules_root / "sources" / binding["source"] / "source.yaml")
    configuration = validate(document, target)
    manifest = Artifacts().json(inputs)
    items = worklist(manifest, configuration)
    for item in items:
        unit = item["unit"]
        if "from" in unit["input"]:
            continue  # Exact prerequisite selectors are already validated.
        data = Artifacts().json(unit["input"])
        declared = (data.get("source"), data.get("feed"))
        keys = (unit["keys"].get("source"), unit["keys"].get("feed"))
        if declared != (binding["source"], feed) and keys != (binding["source"], feed):
            raise Blocked("Plan input lacks explicit selected source/feed membership")
        if "source_input" in data:
            Artifacts().verified(
                data["source_input"]["artifact"], max_bytes=16 * 1024**2
            )
    value = {
        "version": 1,
        "source": binding["source"],
        "feed": feed,
        "binding": binding,
        "target": target,
        "rules_digest": digest(document),
        "inputs": inputs,
        # The worker profile each step needs; a run pins each one's runtime
        # at its first admitted report.
        "profiles": {s["name"]: s["operation"] for s in configuration["steps"]},
        "expected": {
            s["name"]: sum(i["step"] == s["name"] for i in items)
            for s in configuration["steps"]
        },
    }
    return {**value, "plan_hash": digest(value)}


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan",))
    parser.add_argument("--source", required=True)
    parser.add_argument("--feed", required=True)
    parser.add_argument(
        "--rules-root", type=Path, default=Path(__file__).resolve().parents[2] / "rules"
    )
    parser.add_argument("--target", required=True)
    parser.add_argument("--input-manifest", required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = plan(
        source=args.source,
        feed=args.feed,
        target=args.target,
        inputs={"uri": args.input_manifest, "sha256": args.input_sha256},
        rules_root=args.rules_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical(value) + "\n")
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0
