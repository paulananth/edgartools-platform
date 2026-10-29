"""The profiling program stays generic (plan decision: SEC, Company and Person are examples only).

Skill and spec files may name a specific source, kind or identifier only inside
a section whose heading contains "Examples". Scripts may not name one at all.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# Every skill (operator, 2026-10-08: "Skills must not hardcode anything"), found by its
# folder so a new skill is checked by default, and the program's specs.
EXEMPT = {
    # General teaching skills about data work anywhere; their plain English ("a filing
    # cabinet", "company data") is a metaphor, not this repo's sources.
    "data-engineering-fundamentals",
    "data-scientist",
    # Documents how this platform actually masters Securities: naming its sources is its
    # purpose (operator, 2026-10-20: "Security master must document how the actual
    # security mastering is done so exempt").
    "security-master",
    # The operator's rulings for company financials: naming its sources and concepts is
    # its purpose (operator, 2026-10-21: "New company-financials skill (Recommended)").
    "company-financials",
    # This deployment's AWS and Snowflake operations: naming its accounts, objects and
    # sources is its purpose (operator, 2026-10-28: "specific occasional tasks move it to
    # a skill or rules file").
    "aws-snowflake-operations",
}
SCOPE = tuple(
    f"skills/{d.name}" for d in sorted((ROOT / "skills").iterdir()) if d.is_dir() and d.name not in EXEMPT
) + ("docs/specs/rdm", "docs/specs/agent-context", "docs/specs/profiling")
# Sources, kinds and identifiers this repo happens to hold today. Lowercase
# "person" stays allowed: "personal data" is generic.
SPECIFIC = re.compile(
    r"\b(SEC|sec\.gov|EDGAR|GLEIF|LEI|CIK|EIN|SIC|10-K|8-K|Company|company|companies|Person|"
    r"Contoso|accession\w*|tickers?|mdm\.company|filings?|"
    # Operator, 2026-10-28: "Skill can not test security or company it must be generic".
    # Lowercase "securities" stays allowed, as an ordinary word in organisation names.
    r"N-?PORT|OpenFIGI|13F|FIGIs?|CUSIPs?|ISINs?|Security|Securities)\b"
    # Source codes and format names as written in rules files (`gleif`, `sec.ownership`, `sec_cik`, `lei`).
    r"|\b(gleif\w*|sec[._]\w+|lei|nport\w*|n-port|openfigi\w*|thirteenf\w*)\b"
)
# In a skill, a pull request number is history: it belongs in a ticket or an Examples section,
# not in the how-to. A spec may cite the PR that approved it.
HISTORY = re.compile(r"(?<![\w/&])#\d{3,}\b")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def _files() -> list[Path]:
    found = []
    for folder in SCOPE:
        base = ROOT / folder
        if base.is_dir():
            found += [p for p in sorted(base.rglob("*")) if p.suffix in {".md", ".py", ".yaml", ".sh"}]
        elif base.is_file():
            found.append(base)
    return found


def specific_names(path: Path, root: Path = ROOT, history: bool | None = None) -> list[str]:
    """Each line naming a specific source, kind or identifier outside an Examples section;
    in a skill (or with `history`), also each pull request number."""
    if history is None:
        history = path.relative_to(root).parts[0] == "skills"
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
        found = list(SPECIFIC.finditer(line))
        if history:
            found += list(HISTORY.finditer(line))
        hits += [f"{path.relative_to(root)}:{number}: {m.group(0)}" for m in sorted(found, key=lambda m: m.start())]
    return hits


def test_scope_has_files():
    assert _files(), "nothing in scope: the lint would pass vacuously"


def test_every_exempt_skill_exists():
    assert EXEMPT <= {d.name for d in (ROOT / "skills").iterdir() if d.is_dir()}


@pytest.mark.parametrize("path", _files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_specific_names_outside_examples(path):
    assert specific_names(path) == []


def test_lint_catches_a_name_and_spares_examples(tmp_path):
    doc = tmp_path / "x.md"
    doc.write_text("# A\nKeys such as a CIK.\n## Examples\nA CIK.\n### More\nAn LEI.\n## B\nA Company.\n"
                   "Run `--source gleif` with `sec_cik`; selected, secure.\nBuilt by #960; color #fff.\n")
    assert [h.split(": ", 1)[1] for h in specific_names(doc, tmp_path, history=True)] == ["CIK", "Company", "gleif", "sec_cik", "#960"]


def test_lint_catches_a_security_source_and_spares_the_ordinary_word(tmp_path):
    doc = tmp_path / "x.md"
    doc.write_text("# A\nA Security from N-PORT, OpenFIGI or 13F, by its CUSIP, ISIN or FIGI.\n"
                   "Read `nport.yaml`; an org named for securities.\n")
    assert [h.split(": ", 1)[1] for h in specific_names(doc, tmp_path)] == [
        "Security", "N-PORT", "OpenFIGI", "13F", "CUSIP", "ISIN", "FIGI", "nport"]
