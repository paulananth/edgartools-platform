"""A skill holds the rule and the method: no ticket number, no date of a ruling or a run, and a
SKILL.md short enough to read whole. Those belong in the ticket, or behind a pointer.

KNOWN is empty: no skill file cites a ticket. DATES counts the dates that are not history: a folder
name in a path, an example of a value. A file in either is counted exactly.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TICKET = re.compile(r"\btickets? \d+", re.IGNORECASE)
KNOWN: dict[str, int] = {}
# A calendar date, but not a rule version's name (`2026-10-25.1`, `security-2026-10-24.isin`).
DATE = re.compile(r"(?<![\w.-])20\d\d-\d{2}-\d{2}(?!\.\d|[\w-])")
DATES = {
     # a folder name in two paths
    "skills/data-onboarding/REFERENCE.md": 1,  # an example of a refused value
}
MAX_LINES = 500


def citations(text: str) -> int:
    return len(TICKET.findall(text))


def test_a_ticket_citation_is_counted():
    assert citations("decided (ticket 12), see Tickets 3 and 4; a ticketed 9") == 2


def test_skills_cite_only_the_known_tickets():
    found = {}
    for path in sorted((ROOT / "skills").rglob("*")):
        if path.suffix in {".md", ".py", ".yaml", ".sh"}:
            count = citations(path.read_text(encoding="utf-8"))
            if count:
                found[str(path.relative_to(ROOT))] = count
    assert found == KNOWN


def test_every_skill_is_in_the_index():
    index = (ROOT / "skills" / "README.md").read_text(encoding="utf-8")
    skills = sorted(p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md"))
    assert [s for s in skills if f"]({s}/SKILL.md)" not in index] == []


def _counted(pattern: re.Pattern) -> dict[str, int]:
    found = {}
    for path in sorted((ROOT / "skills").rglob("*")):
        if path.suffix in {".md", ".py", ".yaml", ".sh"}:
            count = len(pattern.findall(path.read_text(encoding="utf-8")))
            if count:
                found[str(path.relative_to(ROOT))] = count
    return found


def test_a_date_is_counted_and_a_version_name_is_not():
    text = "(operator, 2026-10-20: yes) version 2026-10-25.1 of security-2026-10-24.isin, as_of 2026-10-05T00:00:00Z"
    assert DATE.findall(text) == ["2026-10-20"]


def test_skills_hold_only_the_known_dates():
    assert _counted(DATE) == DATES


def test_every_skill_file_is_short_enough_to_read_whole():
    long = {p.parent.name: n for p in sorted((ROOT / "skills").glob("*/SKILL.md"))
            if (n := len(p.read_text(encoding="utf-8").splitlines())) >= MAX_LINES}
    assert long == {}
