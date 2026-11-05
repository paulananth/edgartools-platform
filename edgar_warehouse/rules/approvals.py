"""The operator's approvals of the rules, kept in git beside the rules (ticket 193).

`rules/approvals.yaml` lists, for each rules document, the digest of the version the operator approved, their
exact words, who they are, when, and the merge on `main` that made the rules final. A store that loads the rules
(`rules load`) approves every version whose digest is listed, on that merge and those words, with no test run
(operator, 2026-11-04: "the rules must also be in git"; "you dont need proof to activate once the rules are
finalized"). A rules change is a new digest, so it needs its own line: nothing is approved by being near an
approved version.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from edgar_warehouse.bookkeeping.clean.config import digest

from . import files

FILE = "approvals.yaml"
KEYS = ("kind", "name", "digest", "by", "words", "at", "finalized")
HEADER = """# The operator's approvals of the rules (ticket 193): one line per rules document and digest. `rules load` approves
# a saved version whose digest is listed here, in these words, on that merge, with no test run. A rules change
# is a new digest and needs a new line (`edgar-warehouse rules approvals write`, then the operator's words).
"""


def read(root: Path | None = None) -> list[dict]:
    """The listed approvals; none when the file is absent. A malformed line refuses the whole file."""
    path = (root or files.ROOT) / FILE
    if not path.exists():
        return []
    body = yaml.safe_load(path.read_text()) or {}
    entries = body.get("approvals") if isinstance(body, dict) and body.get("version") == 1 else None
    if not isinstance(entries, list):
        raise ValueError(f"{FILE} is `version: 1` and a list `approvals`")
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != set(KEYS) or any(
                not isinstance(entry[key], str) or not entry[key].strip() for key in KEYS):
            raise ValueError(f"{FILE}: each approval names exactly {', '.join(KEYS)}, all text")
        if entry["kind"] not in files.LAYOUT or not re.fullmatch(r"[0-9a-f]{64}", entry["digest"]):
            raise ValueError(f"{FILE}: {entry['kind']} {entry['name']}: a known kind and a 64-digit digest")
    keys = [(e["kind"], e["name"], e["digest"]) for e in entries]
    if len(set(keys)) != len(keys):
        raise ValueError(f"{FILE}: a document and digest are approved once")
    return entries


def current(root: Path | None = None) -> list[tuple[str, str, str]]:
    """Every rules document under the root with the digest `rules save` would store: (kind, name, digest)."""
    return [(kind, name, digest(files.LAYOUT[kind][0](path))) for kind, name, path in files.documents(root)]


def missing(root: Path | None = None) -> list[tuple[str, str, str]]:
    """The documents whose current digest has no listed approval."""
    listed = {(e["kind"], e["name"], e["digest"]) for e in read(root)}
    return [item for item in current(root) if item not in listed]


def write(root: Path | None, *, by: str, words: str, finalized: str, at: str) -> list[dict]:
    """Approve every document at its current digest, in the operator's words: keep the lines already listed for
    a digest that is still current, add the missing ones, drop the lines of digests no document has any more."""
    root = root or files.ROOT
    now = current(root)
    kept = {(e["kind"], e["name"], e["digest"]): e for e in read(root)}
    entries = [kept.get(item) or dict(zip(KEYS, (*item, by, words, at, finalized))) for item in now]
    entries.sort(key=lambda e: (e["kind"], e["name"]))
    (root / FILE).write_text(HEADER + yaml.dump({"version": 1, "approvals": entries}, sort_keys=False, width=200))
    return entries


def apply(rules, saved: list[dict], root: Path | None = None) -> list[dict]:
    """Approve each saved version whose digest is listed and that is not approved yet; the saved rows, updated."""
    listed = {(e["kind"], e["name"], e["digest"]): e for e in read(root)}
    out = []
    for row in saved:
        entry = listed.get((row["kind"], row["name"], row["digest"]))
        if entry and not row.get("approved_by"):
            row = rules.approve(row["kind"], row["name"], row["version"], by=entry["by"], words=entry["words"],
                                finalized=entry["finalized"])
        out.append(row)
    return out
