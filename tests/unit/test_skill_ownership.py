"""The skills' ownership table: every skill has one row, every named skill exists, and a hand-off is written on both sides."""

from __future__ import annotations

import re
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2] / "skills"
COLUMNS = ["skill", "owns", "inputs", "outputs", "hands off to", "receives from", "touch point"]


def table() -> dict[str, dict[str, str]]:
    text = (SKILLS / "OWNERSHIP.md").read_text()
    section = text.split("## The contract", 1)[1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        match = re.match(r"\| \[([a-z0-9-]+)\]\(([a-z0-9-]+)/SKILL\.md\) \|(.*)\|\s*$", line)
        if match:
            cells = [c.strip() for c in match.group(3).split("|")]
            assert match.group(1) == match.group(2) and len(cells) == len(COLUMNS) - 1, line[:80]
            rows[match.group(1)] = dict(zip(COLUMNS[1:], cells))
    return rows


def names(cell: str) -> set[str]:
    return set() if cell == "none" else {n.strip() for n in cell.split(",")}


def test_every_skill_has_one_row_and_no_row_names_a_missing_skill():
    skills = {p.parent.name for p in SKILLS.glob("*/SKILL.md")}
    rows = table()
    assert set(rows) == skills, (skills - set(rows), set(rows) - skills)


def test_every_cell_says_something():
    for skill, row in table().items():
        assert all(len(value) > 3 for value in row.values()), skill


def test_a_hand_off_is_written_on_both_sides():
    rows = table()
    for sender, row in rows.items():
        for receiver in names(row["hands off to"]):
            assert receiver in rows, f"{sender} hands off to {receiver}, which is no skill"
            assert sender in names(rows[receiver]["receives from"]), f"{sender} hands off to {receiver}, which does not list it under Receives from"
        for source in names(row["receives from"]):
            assert source in rows and sender in names(rows[source]["hands off to"]), f"{sender} receives from {source}, which does not hand off to it"


def test_the_monitoring_and_operations_skills_touch_each_other():
    rows = table()
    ring = {"data-operations", "load-monitoring", "database-monitoring", "production-support"}
    for skill in ring:
        assert names(rows[skill]["hands off to"]) & (ring - {skill}), skill  # none of the four stands alone
    assert "load-monitoring" in names(rows["data-operations"]["hands off to"]) and "data-operations" in names(rows["load-monitoring"]["hands off to"])
