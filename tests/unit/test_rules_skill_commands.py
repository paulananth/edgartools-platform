"""Every `rules` command and flag the rules skill names exists, or the skill says it is not built."""
import argparse
import re
from pathlib import Path

from edgar_warehouse.rules.cli import register

SKILL = Path(__file__).resolve().parents[2] / "skills" / "rules" / "SKILL.md"
# Named in the skill with a fallback, and marked "Not built yet" there.
NOT_BUILT = {"profile", "check"}


def _built():
    parser = argparse.ArgumentParser()
    register(parser.add_subparsers())
    rules = parser._subparsers._group_actions[0].choices["rules"]
    return rules._subparsers._group_actions[0].choices


def _named():
    # A code span may wrap onto the next line.
    return re.findall(r"`(?:edgar-warehouse )?rules ([a-z-]+)([^`]*)`", SKILL.read_text())


def test_every_rules_command_the_skill_names_exists():
    text = SKILL.read_text()
    named = {command for command, _ in _named()}
    assert named - NOT_BUILT <= set(_built())
    assert not NOT_BUILT & set(_built()), "built now: drop the skill's fallback and NOT_BUILT"
    for command in NOT_BUILT:
        assert re.search(rf"rules {command}\b.{{0,80}}Not built\s+yet", text, re.DOTALL), command


def test_every_flag_the_skill_writes_exists_on_its_command():
    built = _built()
    for command, rest in _named():
        if command in NOT_BUILT:
            continue
        for flag in re.findall(r"--[a-z0-9-]+", rest):
            assert flag in built[command]._option_string_actions, f"rules {command} {flag}"
