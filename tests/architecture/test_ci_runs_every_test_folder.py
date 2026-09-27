"""CI runs every test folder, whole: a test CI never runs is an unused test."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _pytest_lines() -> list[str]:
    return [line for line in CI.read_text(encoding="utf-8").splitlines() if "pytest" in line]


def test_every_test_folder_is_run_by_ci() -> None:
    folders = {path.parent.name for path in (REPO_ROOT / "tests").glob("*/test_*.py")}
    named = set(re.findall(r"tests/([a-z_]+)/", "\n".join(_pytest_lines())))
    assert folders - named == set(), "add a CI step for each of these test folders"


def test_ci_deselects_no_tests() -> None:
    assert not [line for line in _pytest_lines() if re.search(r"\s-k\s|--deselect|--ignore", line)]
