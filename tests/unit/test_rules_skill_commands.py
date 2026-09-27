"""Every `rules` command the rules skill names exists, or the skill says it is not built."""
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
    return set(rules._subparsers._group_actions[0].choices)


def test_every_rules_command_the_skill_names_exists():
    text = SKILL.read_text()
    named = set(re.findall(r"`(?:edgar-warehouse )?rules ([a-z-]+)", text))
    assert named - NOT_BUILT <= _built()
    assert not NOT_BUILT & _built(), "built now: drop the skill's fallback and NOT_BUILT"
    for command in NOT_BUILT:
        assert re.search(rf"rules {command}\b.{{0,80}}Not built\s+yet", text, re.DOTALL), command
