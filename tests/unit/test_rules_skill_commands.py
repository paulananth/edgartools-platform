"""Every `rules` command and flag the Data Onboarding and Refining Rules skills
name exists."""
import argparse
import re
from pathlib import Path

import pytest

from edgar_warehouse.rules.cli import register

SKILLS = Path(__file__).resolve().parents[2] / "skills"
FILES = [
    SKILLS / "data-onboarding" / "SKILL.md",
    SKILLS / "data-onboarding" / "APPROVE.md",
    SKILLS / "refining-rules" / "SKILL.md",
]

def _built():
    parser = argparse.ArgumentParser()
    register(parser.add_subparsers())
    rules = parser._subparsers._group_actions[0].choices["rules"]
    return rules._subparsers._group_actions[0].choices

def _named(path):
    # A code span or a fenced command may wrap onto the next line.
    text = path.read_text().replace("\\\n", " ")
    spans = re.findall(r"`(?:uv run --extra mdm )?(?:edgar-warehouse )?rules ([a-z-]+)([^`]*)`", text)
    fenced = re.findall(r"edgar-warehouse rules ([a-z-]+)([^\n]*)", text)
    return spans + fenced

@pytest.mark.parametrize("path", FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_every_rules_command_the_skill_names_exists(path):
    named = {command for command, _ in _named(path)}
    assert named, "the skill names no command"
    assert named <= set(_built())

@pytest.mark.parametrize("path", FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_every_flag_the_skill_writes_exists_on_its_command(path):
    built = _built()
    for command, rest in _named(path):
        for flag in re.findall(r"--[a-z0-9-]+", rest):
            assert flag in built[command]._option_string_actions, f"rules {command} {flag}"

def test_migrate_means_a_schema_upgrade_and_load_moves_files():
    built = _built()
    assert "--agent-role" in built["migrate"]._option_string_actions
    for command in ("load", "unload"):
        assert {"--root", "--version"} <= set(built[command]._option_string_actions)
    assert "--to-db" not in built["migrate"]._option_string_actions

def test_each_skill_says_when_to_use_the_other():
    onboarding = " ".join(FILES[0].read_text().split())
    refining = " ".join(FILES[2].read_text().split())
    assert "use **refining-rules**" in onboarding
    assert "use **data-onboarding**" in refining
    for text in (onboarding, refining):
        assert "## Hard stops" in text
