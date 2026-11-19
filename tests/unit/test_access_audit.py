"""The access audit grades platform-neutral objectives through adapters: a clean platform passes, each weakness fails its own objective."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "access-audit" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import access_audit as audit  # noqa: E402
from audit_platforms import aws, github, postgres, snowflake, workstation  # noqa: E402
from audit_platforms.base import OBJECTIVES  # noqa: E402


def snowflake_clean():
    return {
        "audit_role": "AUDITOR",
        "users": [{"name": "A1", "type": "PERSON", "has_mfa": "true", "default_role": "WORK", "has_password": "true"},
                  {"name": "A2", "type": "PERSON", "has_mfa": "true", "default_role": "WORK", "has_password": "true"},
                  {"name": "SVC", "type": "SERVICE", "has_password": "false", "has_rsa_public_key": "true", "default_role": "SVC"}],
        "admin_holders": ["A1", "A2"], "network_policies": 1, "account_network_policy": "P", "monitors": 1,
        "warehouses": [{"name": "W", "resource_monitor": "M"}], "statement_timeout": 3600, "password_policies": 1,
        "authentication_policies": 1, "risky_grants": [], "queries": [{"role_name": "WORK", "n": 100}, {"role_name": "ACCOUNTADMIN", "n": 1}],
        "logins": [{"user_name": "A1", "first_factor": "PASSWORD", "second_factor": "TOTP", "n": 5}],
    }


def postgres_clean():
    return {"login": (False, False, False, False), "memberships": ["pg_monitor"], "writes": 0, "superusers": ["postgres"], "logins": [("l", 20)],
            "settings": {"log_connections": "on", "log_disconnections": "on", "log_statement": "ddl", "ssl": "on", "password_encryption": "scram-sha-256",
                         "pgaudit.log": "write", "statement_timeout": "60000", "idle_in_transaction_session_timeout": "600000"}}


def aws_clean():
    return {"identity_kind": "role", "audit_named": True, "root_mfa": True, "root_keys": 0, "console_users": 2, "console_without_mfa": 0,
            "keys_active": 1, "keys_old": 0, "admin_users": 0, "admin_roles": 1, "admin_visible": True, "password_policy": True,
            "trail_logging": 1, "trails": 1, "public_block": True, "budgets": 1}


def github_clean():
    return {"protected": True, "reviews_required": 1, "status_checks": 2, "secret_scanning": True, "visibility": "public", "admin_permission": False}


def workstation_clean():
    return {"plaintext_passwords": 0, "loose_files": [], "files_held": 3}


CLEAN = {"snowflake": (snowflake, snowflake_clean), "postgres": (postgres, postgres_clean), "aws": (aws, aws_clean),
         "github": (github, github_clean), "workstation": (workstation, workstation_clean)}


def graded(platform, change=None):
    module, make = CLEAN[platform]
    ev = make()
    if change:
        change(ev)
    return {c["objective"]: c["result"] for c in module.controls(ev)}


@pytest.mark.parametrize("platform", sorted(CLEAN))
def test_a_clean_platform_has_no_failure(platform):
    assert "FAIL" not in graded(platform).values()


def test_every_control_names_a_known_objective_and_carries_severity_and_framework_references():
    for platform, (module, make) in CLEAN.items():
        for c in module.controls(make()):
            assert c["objective"] in OBJECTIVES and c["id"] == f"{c['objective']}.{platform}" and c["severity"] and c["refs"]


@pytest.mark.parametrize("platform, objective, change", [
    ("snowflake", "IND", lambda e: e.update(audit_role="ACCOUNTADMIN")),
    ("snowflake", "ADM", lambda e: e.update(admin_holders=["A1"])),
    ("snowflake", "OPS", lambda e: e["users"][0].update(default_role="ACCOUNTADMIN") or e.update(admin_holders=["A1", "A2"], queries=[{"role_name": "ACCOUNTADMIN", "n": 50}, {"role_name": "W", "n": 50}])),
    ("snowflake", "AUT", lambda e: e.update(logins=[{"user_name": "A1", "first_factor": "PASSWORD", "second_factor": None, "n": 3}])),
    ("snowflake", "LPR", lambda e: e.update(risky_grants=[{"grantee_name": "X", "privilege": "OWNERSHIP"}])),
    ("snowflake", "NET", lambda e: e.update(account_network_policy="")),
    ("snowflake", "CST", lambda e: e["warehouses"][0].update(resource_monitor="null")),
    ("snowflake", "TMO", lambda e: e.update(statement_timeout=172800)),
    ("snowflake", "POL", lambda e: e.update(password_policies=0)),
    ("postgres", "IND", lambda e: e.update(memberships=["pg_monitor", "pg_write_all_data"])),
    ("postgres", "LPR", lambda e: e["superusers"].append("loader")),
    ("postgres", "LOG", lambda e: e["settings"].update({"pgaudit.log": "none"})),
    ("postgres", "CST", lambda e: e["logins"].append(("x", -1))),
    ("postgres", "TMO", lambda e: e["settings"].update(statement_timeout="0", idle_in_transaction_session_timeout="0")),
    ("aws", "IND", lambda e: e.update(identity_kind="root")),
    ("aws", "ADM", lambda e: e.update(root_keys=1)),
    ("aws", "AUT", lambda e: e.update(console_without_mfa=1)),
    ("aws", "LPR", lambda e: e.update(admin_users=1)),
    ("aws", "NET", lambda e: e.update(public_block=False)),
    ("aws", "CST", lambda e: e.update(budgets=0)),
    ("aws", "POL", lambda e: e.update(password_policy=False)),
    ("aws", "LOG", lambda e: e.update(trail_logging=0)),
    ("aws", "ROT", lambda e: e.update(keys_old=2)),
    ("github", "CHG", lambda e: e.update(protected=False)),
    ("github", "SEC", lambda e: e.update(secret_scanning=False)),
    ("github", "IND", lambda e: e.update(admin_permission=True)),
    ("workstation", "SEC", lambda e: e.update(plaintext_passwords=1)),
    ("workstation", "SEC", lambda e: e.update(loose_files=["x"])),
])
def test_each_weakness_fails_its_own_objective(platform, objective, change):
    assert graded(platform, change)[objective] == "FAIL"


def test_a_control_the_auditor_cannot_see_is_not_tested_never_passed():
    assert graded("snowflake", lambda e: e.update(admin_holders=["HIDDEN"]))["ADM"] == "NOT_TESTED"
    assert graded("snowflake", lambda e: e.update(authentication_policies=None))["POL"] == "NOT_TESTED"
    assert graded("aws", lambda e: e.update(public_block=None))["NET"] == "NOT_TESTED"


def test_the_coverage_matrix_marks_an_objective_an_adapter_does_not_test_as_a_gap():
    results = audit.run_from_evidence({"postgres": postgres_clean()}, Path("."), [])
    row = {line.split()[0]: line.split()[1:] for line in audit.matrix(results, ["postgres"])[1:]}
    assert row["LPR"] == ["P"] and row["ADM"] == ["-"] and row["ROT"] == ["?"]


def test_change_records_need_a_ticket_and_code_for_every_principal(tmp_path):
    (tmp_path / ".scratch" / "t" / "issues").mkdir(parents=True)
    (tmp_path / ".scratch" / "t" / "issues" / "1.md").write_text("role ROLE_A and ROLE_B")
    (tmp_path / "infra" / "terraform").mkdir(parents=True)
    (tmp_path / "infra" / "terraform" / "x.tf").write_text('resource "r" "a" { name = "role_a" }')
    one = audit.change_records(tmp_path, "snowflake", ["ROLE_A"])[0]
    two = audit.change_records(tmp_path, "snowflake", ["ROLE_A", "ROLE_B"])[0]
    assert one["result"] == "PASS" and two["result"] == "FAIL" and two["evidence"] == {"principals": 2, "with_ticket": 2, "in_terraform": 1}


@pytest.mark.parametrize("adapter_module, rows", [(snowflake, [{"ROLE": "ACCOUNTADMIN"}])])
def test_an_administrator_snowflake_connection_is_refused_without_the_flag(monkeypatch, adapter_module, rows):
    monkeypatch.setattr(snowflake, "snow", lambda connection, sql, soft=False: rows)
    with pytest.raises(SystemExit, match="administrator role"):
        snowflake.collect({"AUDIT_SNOWFLAKE_CONNECTION": "c"}, as_admin=False)


def test_a_non_audit_aws_identity_is_refused_without_the_flag(monkeypatch):
    monkeypatch.setattr(aws, "aws", lambda env, *a, soft=False: {"Arn": "arn:aws:iam::1:user/deployer", "Account": "1"})
    with pytest.raises(SystemExit, match="read-only audit identity"):
        aws.collect({}, as_admin=False)


def test_exit_code_follows_failures_and_the_json_report_parses(monkeypatch, capsys):
    monkeypatch.setenv("DIAGNOSE_DATABASE_URL", "postgresql://x")
    state = {"ev": postgres_clean()}
    monkeypatch.setattr(postgres, "collect", lambda env, as_admin=False: state["ev"])
    assert audit.main(["--platform", "postgres", "--json"]) == 0
    assert {r["id"] for r in json.loads(capsys.readouterr().out)} >= {"IND.postgres", "LOG.postgres"}
    state["ev"] = {**postgres_clean(), "superusers": ["loader"]}
    assert audit.main(["--platform", "postgres", "--json"]) == 1


# --- remediation -------------------------------------------------------------------------------------------------
import access_remediate as remediate  # noqa: E402


def plan(*changes):
    return {"resource_changes": [{"address": a, "change": {"actions": actions, "after": after}} for a, actions, after in changes]}


def test_a_plan_is_summarised_and_a_destroy_is_refused_without_the_flag():
    ok = plan(("snowflake_account_role.a", ["create"], {"name": "R"}), ("snowflake_service_user.b", ["update"], {"name": "U"}))
    assert remediate.summarize(ok) == {"create": 1, "update": 1, "delete": 0}
    with pytest.raises(SystemExit, match="destroy"):
        remediate.summarize(plan(("snowflake_account_role.a", ["delete"], None)))
    assert remediate.summarize(plan(("snowflake_account_role.a", ["delete"], None)), allow_destroy=True)["delete"] == 1


def test_a_plan_that_touches_the_operators_admin_account_is_always_refused():
    touching = plan(("snowflake_user.x", ["update"], {"name": "ananp11"}))
    with pytest.raises(SystemExit, match="operator's own administrator"):
        remediate.summarize(touching, allow_destroy=True)


def test_the_bootstrap_sql_creates_a_non_administrator_with_a_public_key_only():
    sql = remediate.bootstrap_sql("PUBLICKEY")
    assert "PUBLICKEY" in sql and "ACCOUNTADMIN" not in sql.upper().replace("NOT AN ADMINISTRATOR", "") and "manage grants" in sql
    assert "PRIVATE" not in sql.upper()


def test_apply_needs_the_operators_words_and_records_them(tmp_path, monkeypatch):
    for name in ("SNOWFLAKE_ORGANIZATION", "SNOWFLAKE_ACCOUNT_NAME", "ACCESS_ADMIN_USER", "ACCESS_ADMIN_ROLE", "ACCESS_ADMIN_PRIVATE_KEY_FILE"):
        monkeypatch.setenv(name, "x")
    shown = plan(("snowflake_account_role.a", ["create"], {"name": "R"}))

    class Done:
        def __init__(self, out=""):
            self.returncode, self.stdout = 0, out

    monkeypatch.setattr(remediate, "terraform", lambda *a, env=None: Done(json.dumps(shown)))
    with pytest.raises(SystemExit, match="--words"):
        remediate.main(["apply", "--approvals", str(tmp_path / "a.jsonl")])
    remediate.main(["apply", "--words", "yes apply it", "--approvals", str(tmp_path / "a.jsonl")])
    line = json.loads((tmp_path / "a.jsonl").read_text())
    assert line["words"] == "yes apply it" and line["plan"]["create"] == 1 and line["at"].endswith("ET")


def test_the_operators_admin_account_is_never_the_access_admin(monkeypatch):
    for name in ("SNOWFLAKE_ORGANIZATION", "SNOWFLAKE_ACCOUNT_NAME", "ACCESS_ADMIN_ROLE", "ACCESS_ADMIN_PRIVATE_KEY_FILE"):
        monkeypatch.setenv(name, "x")
    monkeypatch.setenv("ACCESS_ADMIN_USER", "ANANP11")
    with pytest.raises(SystemExit, match="never the access admin"):
        remediate.tf_env()


@pytest.mark.parametrize("connection", ["edgartools-prod", "snowconn"])
def test_the_audit_refuses_the_connections_that_sign_in_as_the_operators_admin(connection):
    with pytest.raises(SystemExit, match="overall administrator"):
        snowflake.collect({"AUDIT_SNOWFLAKE_CONNECTION": connection}, as_admin=True)
