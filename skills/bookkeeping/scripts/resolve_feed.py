"""Read-only source/feed resolution from existing Rules descriptors."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.config import digest
from edgar_warehouse.rules.files import load


from edgar_warehouse.bookkeeping.clean.feeds import resolve_feed


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
