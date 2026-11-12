"""A skill holds the rule and the method; a ticket number belongs in the ticket.

The files in KNOWN still cite tickets and are counted exactly, so a new citation
fails and a removed one is recorded by lowering the count here.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TICKET = re.compile(r"\btickets? \d+", re.IGNORECASE)
KNOWN = {
    "skills/company-financials/SKILL.md": 8,
    "skills/security-master/SKILL.md": 12,
}


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
