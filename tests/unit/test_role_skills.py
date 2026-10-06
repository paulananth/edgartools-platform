"""The three role skills name commands the real CLI registers."""

from __future__ import annotations

from pathlib import Path

from edgar_warehouse.bundle import named_commands, unresolved
from edgar_warehouse.cli import build_parser

ROOT = Path(__file__).resolve().parents[2]
ROLES = (
    ("data-modeling", "data-modeling"),
    ("data-engineer", "data-engineer"),
    ("data-scientist", "data-scientist"),
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
    workflows: list[str] = []
    for folder, expected_name in ROLES:
        path = ROOT / "skills" / folder / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        meta = _frontmatter(text)
        assert meta["name"] == expected_name
        assert "Use when" in meta["description"]
        commands = [item for item in named_commands(path.parent) if item[0] == "SKILL.md"]
        assert commands, f"{folder} names no edgar-warehouse command"
        assert unresolved(parser, path.parent) == []
        workflows.append(text.split("## Workflow", 1)[1])
    assert len(set(workflows)) == len(ROLES)
