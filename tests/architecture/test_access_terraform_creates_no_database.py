"""The Snowflake access root creates no database: its policies live in a schema of the Gold database, from rules/snowflake_policy.yaml
(operator, 2026-11-21: "you cannot be creating a database ... remove creating unapproved db")."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACCESS = ROOT / "infra" / "terraform" / "access" / "snowflake"


def test_the_access_root_declares_no_database():
    found = [str(p.relative_to(ROOT)) for p in ACCESS.rglob("*.tf") if 'resource "snowflake_database"' in p.read_text()]
    assert found == [], f"a database is created only with the operator's approval: {found}"


def test_the_policies_are_read_from_the_policy_file_not_written_in_terraform():
    text = (ACCESS / "accounts" / "prod" / "main.tf").read_text()
    assert "rules/snowflake_policy.yaml" in text and "min_length           = 14" not in text


def test_the_owner_role_and_the_gold_database_ownership_are_declared_from_the_names_file():
    text = (ACCESS / "accounts" / "prod" / "main.tf").read_text()
    assert 'resource "snowflake_account_role" "owner"' in text and "local.names.owner" in text
    assert 'resource "snowflake_grant_ownership" "gold_database"' in text
    assert 'resource "snowflake_database"' not in text


def test_the_root_never_plans_a_grant_to_the_administrator_role():
    assert "ACCOUNTADMIN" not in (ACCESS / "accounts" / "prod" / "main.tf").read_text().split("resource \"snowflake_account_role\" \"owner\"")[1]
