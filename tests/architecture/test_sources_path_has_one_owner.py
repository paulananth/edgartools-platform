"""Sources and their mappings live beside the rules, not under them: one function, `rules.files.sources_root`, names the folder."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OWNER = ROOT / "edgar_warehouse" / "rules" / "files.py"
# In the package, where the rules folder is a parameter: a path built onto it (`root / "sources"`, `ROOT / 'sources'`, `.glob("sources/...")`).
BUILT = re.compile(r"""(?:ROOT|root)\s*/\s*['"]sources['"/]|\.glob\(['"]sources/""")


def _lines(folders):
    for folder in folders:
        for path in sorted((ROOT / folder).rglob("*.py")):
            if path not in (OWNER, Path(__file__)):
                yield path, path.read_text(encoding="utf-8", errors="replace").splitlines()


def test_no_module_but_the_resolver_builds_a_sources_path():
    found = [f"{path.relative_to(ROOT)}:{n}" for path, lines in _lines(["edgar_warehouse"])
             for n, line in enumerate(lines, 1) if BUILT.search(line)]
    assert found == [], f"call rules.files.sources_root instead: {found}"


def test_nothing_still_says_sources_are_under_rules():
    found = [f"{path.relative_to(ROOT)}:{n}" for path, lines in _lines(["edgar_warehouse", "scripts", "skills", "tests", "infra"])
             for n, line in enumerate(lines, 1) if "rules/sources" in line]
    assert found == [], found
