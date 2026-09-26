"""Score a trial's rules file against the proven one, contract by contract.

usage: uv run --no-sync python score.py <proven source.yaml> <trial source.yaml>

Each proven contract is paired with the trial contract that maps the same
record type (same native_member, else the most shared field paths). The free
text of the envelope is shown side by side, not scored. The adapter is
compared key by key: equal, different, missing (in proven only) or extra
(in the trial only).
"""

from __future__ import annotations

import sys
from pathlib import Path

from edgar_warehouse.mdm.clean.store import digest
from edgar_warehouse.rules.files import load

SCORED = [
    "kind", "kind_field", "kind_values", "probable_kind_values", "classification",
    "record_key", "record_key_format", "identifiers", "identifier_formats",
    "fields", "field_shape", "relationships", "profiles", "provenance",
    "source_record_provenance", "matching", "retain_deferred", "native_member",
]
ENVELOPE = ["nonblocking_deferred_reasons", "publication_families"]
TEXT = ["provider", "family", "schema_version", "record_key", "publication_key",
        "effective_time", "semantics", "completeness"]


def paths(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from paths(item, f"{prefix}.{key}" if prefix else key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from paths(item, f"{prefix}[{index}]")
    else:
        yield prefix, value


def pair(proven: dict, trial: dict) -> list[tuple[str, str | None]]:
    pairs, free = [], dict(trial)
    for code, entry in proven.items():
        adapter = entry["contract"]["adapter"]
        member = adapter.get("native_member")
        best, score = None, -1
        for other, candidate in free.items():
            theirs = candidate.get("contract", {}).get("adapter", {})
            if member and theirs.get("native_member") == member:
                best, score = other, 10**6
                break
            shared = len({v for _, v in paths(adapter.get("fields", {}))}
                         & {v for _, v in paths(theirs.get("fields", {}))})
            if shared > score:
                best, score = other, shared
        pairs.append((code, best))
        free.pop(best, None)
    return pairs


def main(proven_path: str, trial_path: str) -> None:
    proven, trial = load(Path(proven_path)), load(Path(trial_path))
    print(f"digest equal: {digest(proven['mdm']) == digest(trial.get('mdm', {}))}")
    totals = {"equal": 0, "different": 0, "missing": 0, "extra": 0}
    for code, other in pair(proven["mdm"], trial.get("mdm", {})):
        print(f"\n## {code}  <->  {other}")
        if other is None:
            print("  no trial contract for this record type")
            continue
        mine, theirs = proven["mdm"][code]["contract"], trial["mdm"][other]["contract"]
        for key in TEXT:
            print(f"  text {key}:\n    proven: {mine.get(key)!r}\n    trial:  {theirs.get(key)!r}")
        a = dict(mine["adapter"], **{k: mine[k] for k in ENVELOPE if k in mine})
        b = dict(theirs.get("adapter", {}), **{k: theirs[k] for k in ENVELOPE if k in theirs})
        for key in SCORED + ENVELOPE:
            left = dict(paths(a[key], key)) if key in a else {}
            right = dict(paths(b[key], key)) if key in b else {}
            for path in sorted(set(left) | set(right)):
                if path in left and path in right:
                    verdict = "equal" if left[path] == right[path] else "different"
                else:
                    verdict = "missing" if path in left else "extra"
                totals[verdict] += 1
                if verdict != "equal":
                    print(f"  {verdict:9} {path}: proven={left.get(path)!r} trial={right.get(path)!r}")
        others = sorted(set(b) - set(SCORED) - set(ENVELOPE) - {"version"})
        if others:
            print(f"  unknown adapter keys in trial: {others}")
    extra = set(trial.get("mdm", {})) - {o for _, o in pair(proven["mdm"], trial.get("mdm", {}))}
    if extra:
        print(f"\ntrial contracts with no proven pair: {sorted(extra)}")
    print(f"\ntotals: {totals}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
