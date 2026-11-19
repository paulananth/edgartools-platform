"""The role guards: only what a role lacks is applied, absent roles are skipped, values cannot carry SQL."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "infra" / "scripts" / "harden-hosted-roles.py"
spec = importlib.util.spec_from_file_location("harden", SCRIPT)
harden = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harden)

GUARDS = {"loader": {"limit": 300, "settings": {"work_mem": "64MB", "pgaudit.log": "ddl,role"}}}


def test_a_role_without_its_guards_gets_each_one():
    steps = harden.plan({"loader": -1}, {}, GUARDS)
    assert [s[1] for s in steps] == ["connection limit", "work_mem", "pgaudit.log"]
    assert steps[0][2] == 'ALTER ROLE "loader" CONNECTION LIMIT 300' and steps[1][2] == "ALTER ROLE \"loader\" SET work_mem = '64MB'"


def test_a_role_that_holds_its_guards_gets_nothing_and_a_missing_role_is_skipped():
    assert harden.plan({"loader": 300}, {"loader": {"work_mem": "64MB", "pgaudit.log": "ddl,role"}}, GUARDS) == []
    assert harden.plan({}, {}, GUARDS) == []


def test_only_the_difference_is_applied():
    steps = harden.plan({"loader": 300}, {"loader": {"work_mem": "384MB", "pgaudit.log": "ddl,role"}}, GUARDS)
    assert [s[1] for s in steps] == ["work_mem"]


def test_a_value_that_could_carry_sql_is_refused():
    with pytest.raises(ValueError, match="unsafe"):
        harden.plan({"loader": -1}, {}, {"loader": {"limit": 1, "settings": {"work_mem": "1MB'; drop table x; --"}}})


def test_the_repository_guards_name_every_audit_control():
    loader = harden.GUARDS["edgar_loader"]
    assert loader["limit"] > 0 and loader["settings"]["work_mem"] and "pgaudit.log" in loader["settings"]
    assert all(g["limit"] > 0 and "statement_timeout" in g["settings"] for n, g in harden.GUARDS.items())
