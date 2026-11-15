"""The hosted reset puts back each database's owner and grants exactly as read from its access list."""
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "reset_hosted_databases", Path(__file__).parents[2] / "infra" / "scripts" / "reset-hosted-databases.py")
reset = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reset)


def test_an_access_list_becomes_the_grants_other_than_the_owners_own():
    acl = ["=T/admin", "admin=CTc/admin", "app_runtime=c/admin", "app_reader=c/admin"]
    assert reset.grants(acl, "admin") == [("PUBLIC", "TEMPORARY"), ("app_runtime", "CONNECT"), ("app_reader", "CONNECT")]


def test_a_database_with_no_access_list_has_no_grants():
    assert reset.grants(None, "admin") == []
    assert reset.grants([], "admin") == []


def test_every_database_the_platform_holds_is_named():
    assert reset.DATABASES == ("mdm", "rdm", "rules", "bookkeeping", "change_journal", "silver")
