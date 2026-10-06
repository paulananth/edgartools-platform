"""Role skills: platform skills name real CLI commands; the course skill does not."""

from __future__ import annotations

from pathlib import Path

from edgar_warehouse.bundle import named_commands, unresolved
from edgar_warehouse.cli import build_parser

ROOT = Path(__file__).resolve().parents[2]
OPERATIONAL = (("data-modeling", "data-modeling"),)
SCIENTIST = ("data-scientist", "data-scientist")
SCIENTIST_SECTIONS = (
    "## 1. Collection & Storage",
    "## 2. Preparation (cleaning)",
    "## 3. Exploration & Visualization (EDA)",
    "## 4. Experimentation & Prediction",
    "## Deliverable checklist",
)
FUNDAMENTALS = ("data-engineering-fundamentals", "data-engineering-fundamentals")
FUNDAMENTALS_SECTIONS = (
    "## Role definition",
    "## Where data engineering sits in the data workflow",
    "## Concept modules",
    "## Three core stories",
    "## Response templates",
    "## Lexicon",
    "## Guardrails",
)


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        raise AssertionError("skill file has no YAML frontmatter")
    _marker, raw, _body = text.split("---", 2)
    fields: dict[str, str] = {}
    for line in raw.strip().splitlines():
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def test_role_skills_name_registered_commands() -> None:
    parser = build_parser()
    bodies: list[str] = []
    for folder, expected_name in OPERATIONAL:
        path = ROOT / "skills" / folder / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        meta = _frontmatter(text)
        assert meta["name"] == expected_name
        assert "Use when" in meta["description"]
        commands = [item for item in named_commands(path.parent) if item[0] == "SKILL.md"]
        assert commands, f"{folder} names no edgar-warehouse command"
        assert unresolved(parser, path.parent) == []
        bodies.append(text.split("## Workflow", 1)[1])

    folder, expected_name = FUNDAMENTALS
    path = ROOT / "skills" / folder / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    meta = _frontmatter(text)
    assert meta["name"] == expected_name
    assert meta["description"].startswith("Use when")
    assert "pipelines" in meta["description"]
    for heading in FUNDAMENTALS_SECTIONS:
        assert heading in text
    assert "Seagate, November 2018" in text
    assert "undated in the source" in text
    assert len(text.splitlines()) < 500
    commands = [item for item in named_commands(path.parent) if item[0] == "SKILL.md"]
    assert commands == []
    assert unresolved(parser, path.parent) == []
    bodies.append(text.split("## Concept modules", 1)[1])

    folder, expected_name = SCIENTIST
    path = ROOT / "skills" / folder / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    meta = _frontmatter(text)
    assert meta["name"] == expected_name
    assert meta["description"].startswith("Use when")
    assert "standard data science workflow" in meta["description"]
    for heading in SCIENTIST_SECTIONS:
        assert heading in text
    commands = [item for item in named_commands(path.parent) if item[0] == "SKILL.md"]
    assert commands == []
    assert unresolved(parser, path.parent) == []
    bodies.append(text.split("## 1. Collection & Storage", 1)[1])
    assert len(set(bodies)) == len(OPERATIONAL) + 2
