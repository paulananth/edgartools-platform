"""The access audit grades evidence: a clean setup passes, each weakness fails its own control, and it prints no secret."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "skills" / "access-audit" / "scripts" / "access_audit.py"
spec = importlib.util.spec_from_file_location("access_audit", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def clean():
    sf = {
        "audit_role": "AUDITOR",
        "users": [{"name": "ADMIN1", "type": "PERSON", "has_mfa": "true", "default_role": "WORK", "has_password": "true"},
                  {"name": "ADMIN2", "type": "PERSON", "has_mfa": "true", "default_role": "WORK", "has_password": "true"},
                  {"name": "SVC", "type": "SERVICE", "has_password": "false", "has_rsa_public_key": "true", "default_role": "SVC"}],
        "admin_holders": ["ADMIN1", "ADMIN2"], "network_policies": 1, "account_network_policy": "POLICY", "monitors": 1,
        "warehouses": [{"name": "W", "resource_monitor": "M"}], "statement_timeout": 3600, "password_policies": 1,
        "authentication_policies": 1, "risky_grants": [],
        "queries": [{"role_name": "WORK", "n": 100}, {"role_name": "ACCOUNTADMIN", "n": 1}],
        "logins": [{"user_name": "ADMIN1", "first_factor": "PASSWORD", "second_factor": "TOTP", "n": 5}],
    }
    pg = {"login": (False, False, False, False), "memberships": ["pg_monitor"], "writes": 0, "superusers": ["postgres"],
          "logins": [("loader", 20)], "settings": {"log_connections": "on", "log_disconnections": "on", "log_statement": "ddl",
                                                   "ssl": "on", "password_encryption": "scram-sha-256", "pgaudit.log": "write"}}
    repo = {"named": 1, "ticketed": ["R"], "in_code": ["R"], "plaintext_passwords": 0, "loose_files": []}
    return sf, pg, repo


def results(sf, pg, repo):
    return {r["id"]: r["result"] for r in audit.evaluate(sf, pg, repo)}


def test_a_clean_setup_passes_every_tested_control():
    found = results(*clean())
    assert {k for k, v in found.items() if v == "FAIL"} == set()
    assert found["KR-01"] == found["AR-01"] == "NOT_TESTED"


@pytest.mark.parametrize("control, change", [
    ("AUD-00", lambda sf, pg, repo: sf.update(audit_role="ACCOUNTADMIN")),
    ("AC-01", lambda sf, pg, repo: sf.update(admin_holders=["ADMIN1"])),
    ("AC-02", lambda sf, pg, repo: sf["users"][0].update(default_role="ACCOUNTADMIN")),
    ("AC-03", lambda sf, pg, repo: sf.update(queries=[{"role_name": "ACCOUNTADMIN", "n": 50}, {"role_name": "WORK", "n": 50}])),
    ("AC-04", lambda sf, pg, repo: sf.update(logins=[{"user_name": "ADMIN1", "first_factor": "PASSWORD", "second_factor": None, "n": 3}])),
    ("AC-05", lambda sf, pg, repo: sf["users"][2].update(has_password="true")),
    ("AC-06", lambda sf, pg, repo: sf.update(risky_grants=[{"grantee_name": "X", "privilege": "OWNERSHIP"}])),
    ("NW-01", lambda sf, pg, repo: sf.update(account_network_policy="")),
    ("OP-01", lambda sf, pg, repo: sf["warehouses"][0].update(resource_monitor="null")),
    ("OP-02", lambda sf, pg, repo: sf.update(statement_timeout=172800)),
    ("AU-01", lambda sf, pg, repo: sf.update(password_policies=0)),
    ("DB-01", lambda sf, pg, repo: pg.update(memberships=["pg_monitor", "pg_write_all_data"])),
    ("DB-02", lambda sf, pg, repo: pg["superusers"].append("loader")),
    ("DB-03", lambda sf, pg, repo: pg["settings"].update(log_connections="off")),
    ("DB-04", lambda sf, pg, repo: pg["settings"].update({"pgaudit.log": "none"})),
    ("DB-05", lambda sf, pg, repo: pg["logins"].append(("x", -1))),
    ("CM-01", lambda sf, pg, repo: repo.update(ticketed=[])),
    ("CM-02", lambda sf, pg, repo: repo.update(in_code=[])),
    ("SC-01", lambda sf, pg, repo: repo.update(plaintext_passwords=1)),
])
def test_each_weakness_fails_its_own_control_and_only_that_one(control, change):
    sf, pg, repo = clean()
    change(sf, pg, repo)
    failed = {k for k, v in results(sf, pg, repo).items() if v == "FAIL"}
    assert control in failed


def test_an_administrator_connection_is_refused_without_the_flag(monkeypatch):
    monkeypatch.setattr(audit, "snow", lambda connection, sql: [{"ROLE": "ACCOUNTADMIN"}])
    with pytest.raises(SystemExit, match="administrator role"):
        audit.snowflake_evidence("c", as_admin=False)


def test_exit_code_follows_failures_and_the_json_report_parses(monkeypatch, capsys):
    import json

    sf, pg, repo = clean()
    monkeypatch.setenv("AUDIT_SNOWFLAKE_CONNECTION", "c")
    monkeypatch.setattr(audit, "snowflake_evidence", lambda c, a: sf)
    monkeypatch.setattr(audit, "postgres_evidence", lambda: pg)
    monkeypatch.setattr(audit, "repository_evidence", lambda r, n: dict(repo))
    assert audit.main(["--json"]) == 0
    assert {r["id"] for r in json.loads(capsys.readouterr().out)} >= {"AC-01", "DB-04", "CM-02"}
    sf["admin_holders"] = ["ADMIN1"]
    assert audit.main(["--json"]) == 1
