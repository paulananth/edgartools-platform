from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ACCESS = (
    REPO_ROOT
    / "infra"
    / "terraform"
    / "access"
    / "snowflake"
    / "modules"
    / "account_access"
    / "main.tf"
)


def test_owner_inherits_bounded_reader_and_has_stage_access() -> None:
    source = ACCESS.read_text(encoding="utf-8")
    assert 'resource "snowflake_grant_account_role" "reader_to_dashboard_owner"' in source
    assert 'role_name        = snowflake_account_role.roles["reader"].name' in source
    assert 'parent_role_name = snowflake_account_role.roles["dashboard_owner"].name' in source
    assert 'privileges        = ["READ", "WRITE"]' in source
    assert "Caller's Rights" not in source


def test_decision_reader_grants_views_not_private_tables() -> None:
    source = ACCESS.read_text(encoding="utf-8")
    assert '"reader_decision_all_views"' in source
    assert '"reader_decision_future_views"' in source
    assert 'object_type_plural = "VIEWS"' in source
    assert "reader_decision_all_objects" not in source
    assert "reader_decision_future_objects" not in source
