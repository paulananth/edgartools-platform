"""Read-only source/feed resolution from existing Rules descriptors."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.config import digest
from edgar_warehouse.rules.files import load


def resolve_feed(root: Path, source: str, feed: str) -> dict:
    if not source or not feed:
        raise ValueError("Both source and feed are required")
    documents = [(path.parent.name, load(path)) for path in sorted(root.glob("sources/*/source.yaml"))]
    matches = [(name, body) for name, body in documents if name == source]
    if not matches:
        matches = [(name, body) for name, body in documents if any(
            entry["contract"].get("provider", "").casefold() == source.casefold()
            for entry in body.get("mdm", {}).values()
        )]
    if len(matches) != 1:
        raise ValueError(f"Source {source!r} must resolve to exactly one Rules document")
    name, body = matches[0]
    if body.get("source") != name:
        raise ValueError("Rules source identity disagrees with its document name")
    bronze_family = body.get("bronze", {}).get("family")
    datasets = []
    for code, entry in sorted(body.get("mdm", {}).items()):
        contract = entry["contract"]
        member = contract.get("adapter", {}).get("native_member")
        labels = {code, member, bronze_family, contract.get("family")}
        labels.update(contract.get("publication_families", []))
        if feed in labels:
            datasets.append({"code": code, "member": member, "family": contract.get("family"),
                             "publication_families": contract.get("publication_families", [])})
    if not datasets and feed != bronze_family:
        raise ValueError(f"Feed {feed!r} is not declared by source {name!r}")
    return {"source": name, "requested_source": source, "feed": feed,
            "rules_digest": digest(body), "datasets": datasets,
            "targets": sorted(body.get("bookkeeping", {}).get("targets", {}))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--feed", required=True)
    parser.add_argument("--rules-root", type=Path, default=Path(__file__).resolve().parents[3] / "rules")
    args = parser.parse_args()
    try:
        result = resolve_feed(args.rules_root, args.source, args.feed)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
