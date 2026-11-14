"""Draft the next version of a published RDM code set: its published rows plus added codes.

    rdm_next_version.py <code set> <version> --add <codes.yaml> --out <draft.yaml> [--root rules/reference/published]

The published version is read from `<root>/<code set>/<published>/` and refused unless its rows rebuild
the pinned sha256 exactly, so the draft carries every code as published. Each added code is a row in the
published shape (`code`, `label`, `definition`, `parent_code`, `properties`, `crosswalk`); a code already
held is refused. The draft is what `edgar-warehouse rdm draft --file` reads; approval and publishing stay
with the RDM workflow (data-profiling CODE-SETS.md).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

from edgar_warehouse.rdm.store import CODE_COLUMNS, canonical

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "rules" / "reference" / "published"


def published(root: Path, code_set: str) -> tuple[str, list[dict]]:
    pin = json.loads(max((root / code_set).glob("*/pin.json"), key=lambda p: int(p.parent.name)).read_text())
    data = (root / code_set / pin["version"] / "canonical.jsonl").read_bytes()
    if hashlib.sha256(data).hexdigest() != pin["sha256"]:
        raise SystemExit(f"{code_set} {pin['version']}: canonical.jsonl differs from its pin")
    return pin["version"], [json.loads(line) for line in data.decode("utf-8").splitlines()]


def depths(rows: list[dict]) -> dict[str, int]:
    parent = {r["code"]: r.get("parent_code") for r in rows}

    def depth(code: str) -> int:
        return 1 if parent.get(code) is None else 1 + depth(parent[code])

    return {code: depth(code) for code in parent}


def draft(code_set: str, version: str, published_version: str, rows: list[dict], added: list[dict]) -> dict:
    held = {r["code"] for r in rows}
    if refused := sorted(r["code"] for r in added if r["code"] in held):
        raise SystemExit(f"already held: {refused}")
    rows = [*rows, *({"crosswalk": [], "labels": [["en", "preferred", r["label"]]], **r} for r in added)]
    level_of = depths(rows)
    names = {level_of[r["code"]]: r["level"] for r in rows if r.get("level")}
    codes = [{k: r[k] for k in CODE_COLUMNS if r.get(k) is not None} for r in rows]
    labels = [{"code": r["code"], "language": lang, "kind": kind, "label": text}
              for r in rows for lang, kind, text in r.get("labels", [])]
    crosswalk = [{"from_code": r["code"], **x} for r in rows for x in r.get("crosswalk", [])]
    return {"code_set": {"code_set": code_set}, "version": version, "supersedes": published_version,
            "codes": codes, "labels": labels, "levels": [{"depth": d, "name": n} for d, n in sorted(names.items())],
            "crosswalk": crosswalk}


def rebuilds(rows: list[dict], pin_sha256: str) -> bool:
    """The published rows, rebuilt through the draft's shape, give the pinned bytes."""
    level_of = depths(rows)
    levels = {level_of[r["code"]]: r["level"] for r in rows if r.get("level")}
    codes = [{**{k: r.get(k) for k in CODE_COLUMNS},
              "labels": [{"language": lang, "kind": kind, "label": text, "source": ""}
                         for lang, kind, text in r.get("labels", [])],
              "crosswalk": r.get("crosswalk", [])} for r in rows]
    return hashlib.sha256(canonical(codes, levels)).hexdigest() == pin_sha256


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("code_set")
    parser.add_argument("version")
    parser.add_argument("--add", required=True, type=Path, help="YAML list of the codes to add")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    published_version, rows = published(args.root, args.code_set)
    pin = json.loads((args.root / args.code_set / published_version / "pin.json").read_text())
    if not rebuilds(rows, pin["sha256"]):
        raise SystemExit(f"{args.code_set} {published_version}: its rows do not rebuild the pinned bytes")
    body = draft(args.code_set, args.version, published_version, rows, yaml.safe_load(args.add.read_text()) or [])
    args.out.write_text(yaml.safe_dump(body, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"{args.out}: {args.code_set} {args.version} supersedes {published_version}, "
          f"{len(body['codes'])} codes ({len(body['codes']) - len(rows)} added)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
