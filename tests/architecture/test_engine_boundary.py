"""Python reaches the Rust engine only through its facade (mastering to-do 15;
operator, 2026-10-02: "rust engine is under the cover always using python")."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "edgar_warehouse"
FACADE = ROOT / "rules" / "engine.py"


def test_only_the_facade_imports_the_engine() -> None:
    importers = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*.py")
        if re.search(r"^\s*(import|from)\s+source_contract\b", path.read_text(encoding="utf-8"), re.M)
    }
    assert importers == {FACADE.relative_to(ROOT).as_posix()}
