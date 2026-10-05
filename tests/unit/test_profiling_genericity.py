"""The profiling program stays generic (plan decision: SEC, Company and Person are examples only).

Skill and spec files may name a specific source, kind or identifier only inside
a section whose heading contains "Examples". Scripts may not name one at all.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCOPE = (
    "skills/data-profiling",
    "skills/data-quality",
    "docs/specs/rdm",
    "docs/specs/agent-context",
    "docs/specs/profiling",
)
# Sources, kinds and identifiers this repo happens to hold today. Lowercase
# "person" stays allowed: "personal data" is generic.
SPECIFIC = re.compile(
    r"\b(SEC|sec\.gov|EDGAR|GLEIF|LEI|CIK|EIN|SIC|10-K|8-K|Company|company|companies|Person|"
    r"Contoso|accession\w*|tickers?|mdm\.company|filings?)\b"
)
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def _files() -> list[Path]:
    found = []
    for folder in SCOPE:
        base = ROOT / folder
        if base.is_dir():
            found += [p for p in sorted(base.rglob("*")) if p.suffix in {".md", ".py", ".yaml", ".sh"}]
    return found


def specific_names(path: Path, root: Path = ROOT) -> list[str]:
    """Each line naming a specific source, kind or identifier outside an Examples section."""
    hits, examples_level = [], None
    in_code = False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if path.suffix == ".md":
            if line.startswith("```"):
                in_code = not in_code
            heading = None if in_code else _HEADING.match(line)
            if heading:
                level = len(heading.group(1))
                if examples_level is not None and level <= examples_level:
                    examples_level = None
                if "Examples" in heading.group(2):
                    examples_level = level
            if examples_level is not None:
                continue
        hits += [f"{path.relative_to(root)}:{number}: {m.group(0)}" for m in SPECIFIC.finditer(line)]
    return hits


def test_scope_has_files():
    assert _files(), "nothing in scope: the lint would pass vacuously"


@pytest.mark.parametrize("path", _files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_specific_names_outside_examples(path):
    assert specific_names(path) == []


def test_lint_catches_a_name_and_spares_examples(tmp_path):
    doc = tmp_path / "x.md"
    doc.write_text("# A\nKeys such as a CIK.\n## Examples\nA CIK.\n### More\nAn LEI.\n## B\nA Company.\n")
    assert [h.split(": ", 1)[1] for h in specific_names(doc, tmp_path)] == ["CIK", "Company"]
