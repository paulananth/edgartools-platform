"""Keep a copy of one try. A path writes the case. No path is not confirmed."""

from __future__ import annotations

import json
import os
from pathlib import Path


def keep_copy(case, path) -> dict:
    """Write the case JSON to a confirmed path. Nothing is written without one."""
    if path is None or path == "":
        return {"refused": "The path is not confirmed."}
    target = Path(path)
    if _under_rules(target):
        return {"refused": "A copy is not written under rules/."}
    if target.is_dir():
        return {"refused": "The path is a folder."}
    if not target.parent.is_dir():
        return {"refused": "The folder is not there."}
    text = json.dumps(case, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    target.write_text(text, encoding="utf-8")
    return {"kept": str(target)}


def _under_rules(path: Path) -> bool:
    """True when an existing ancestor of `path` is the rules folder, whatever its spelling."""
    from .files import ROOT

    root = Path(ROOT)
    if not root.exists():
        return False
    node = path if path.is_absolute() else Path.cwd() / path
    while True:
        if node.exists():
            try:
                if os.path.samefile(node, root):
                    return True
            except OSError:
                pass
        parent = node.parent
        if parent == node:
            return False
        node = parent
