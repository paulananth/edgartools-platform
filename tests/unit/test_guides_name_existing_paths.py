"""CLAUDE.md and AGENTS.md name only paths that exist (ticket 85).

Both are read at the start of every session; a path the rebuild deleted sends
a session looking for code that is gone."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("stale_paths", ROOT / "scripts" / "dev" / "stale_paths.py")
stale_paths = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stale_paths)


def test_the_guides_name_no_missing_path():
    for name in ("CLAUDE.md", "AGENTS.md"):
        assert stale_paths.missing((ROOT / name).read_text()) == [], name


def test_a_missing_path_is_found():
    assert stale_paths.missing("see `edgar_warehouse/no_such_module.py` and `rules/`") == [
        (1, "edgar_warehouse/no_such_module.py")]
