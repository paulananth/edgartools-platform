"""The Mastering Policy's kind documents, one JSON file per entity kind.

Rules are data (operator, 2026-09-24): source priority and field rules for a
kind live in `<kind>.json` here, and every caller composes the policy body from
this loader rather than restating a kind. Adding Person or Fund is a new file,
not an edit to a source adapter.
"""

from __future__ import annotations

import json
from pathlib import Path

FOLDER = Path(__file__).parent


def load_kinds() -> dict[str, dict]:
    """Every kind document in this folder, keyed by kind name."""
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(FOLDER.glob("*.json"))
    }


def load_proposal(name: str) -> dict:
    """A proposed addition to a kind, kept out of the live policy.

    `proposals/` is not globbed by `load_kinds`, so a proposal changes no
    live policy digest until an approval moves its rules into the kind file.
    """
    return json.loads(
        (FOLDER / "proposals" / f"{name}.json").read_text(encoding="utf-8")
    )
