"""CI runs every test folder, whole: a test CI never runs is an unused test."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

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


def test_storage_families_have_independent_bounded_jobs_and_all_gate_merge() -> None:
    jobs = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]
    expected = {
        "storage-adapters": ("storage_adapters", ["postgresql", "mysql", "mssql"]),
        "reference-storage": ("reference_storage", ["postgresql", "mysql"]),
        "silver-storage": ("silver_storage", ["postgresql", "mysql"]),
    }
    for name,(folder,engines) in expected.items():
        job = jobs[name]
        assert job["strategy"]["matrix"]["engine"] == engines
        assert 1 <= job["timeout-minutes"] <= 20
        commands = [step.get("run", "") for step in job["steps"]]
        assert any(f"pytest tests/{folder}/" in command for command in commands)
        assert any(step.get("if") == "always()" and "docker stop" in step.get("run", "")
                   for step in job["steps"])
    gate = jobs["ci-gate"]
    assert set(gate["needs"]) == set(jobs)-{"ci-gate"}
    assert gate["if"] == "always()"
    script = "\n".join(step.get("run", "") for step in gate["steps"])
    assert all("needs."+name+".result" in script for name in gate["needs"])
