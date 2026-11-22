"""Snowflake: users, administrators, policies, warehouses and the usage record, read through a SnowCLI connection."""
from __future__ import annotations

import json
import subprocess
import sys

from .base import control

NAME = "snowflake"
ADMIN = {"ACCOUNTADMIN", "SECURITYADMIN", "SYSADMIN", "USERADMIN", "ORGADMIN"}
RISKY = ("OWNERSHIP", "MANAGE GRANTS", "CREATE USER", "CREATE ROLE", "MANAGE WAREHOUSES", "CREATE INTEGRATION")
MAX_TIMEOUT = 4 * 3600
USAGE = "snowflake.account_usage"


# The operator's overall administrator account and the connections that sign in as it: the audit never uses or changes them.
PROTECTED_USERS = {"ANANP11"}
FORBIDDEN_CONNECTIONS = {"edgartools-prod", "snowconn"}


DEFAULT_CONNECTION = "edgartools-audit"  # the read-only auditor's own connection: the audit needs no variable to run


def connection_of(env) -> str:
    return env.get("AUDIT_SNOWFLAKE_CONNECTION") or DEFAULT_CONNECTION


def configured(env) -> bool:
    return True


def snow(connection: str, sql: str, soft: bool = False):
    done = subprocess.run(["snow", "sql", "-c", connection, "--format", "json", "-q", sql], capture_output=True, text=True, check=False)
    if done.returncode:  # its message can quote the account
        if soft:
            return None  # a view the role cannot read: the control is then not tested, never passed
        sys.exit("a Snowflake read failed (check the auditor connection and its role)")
    return json.loads(done.stdout or "[]")


def lower(rows):
    return [{k.lower(): (str(v).lower() if isinstance(v, bool) else v) for k, v in row.items()} for row in rows]


def expected_policies() -> dict:
    """The policy file's values with the database it names resolved from snowflake.yaml."""
    import yaml
    from edgar_warehouse.rules import files

    policy = yaml.safe_load((files.ROOT / "snowflake_policy.yaml").read_text(encoding="utf-8"))
    names = yaml.safe_load((files.ROOT / "snowflake.yaml").read_text(encoding="utf-8"))
    where = policy["location"]
    return {**policy, "location": {"database": names[where["database_of"]]["database"], "schema": where["schema"]}}


def found_policies(connection: str, database: str):
    """The live password and authentication policies with their properties, read through the administrator's read-only procedure
    (the auditor holds no privilege on a policy: the only one that reads it also lets a role attach it); None when unreadable."""
    rows = snow(connection, f"call {database}.control.audit_credential_policies()", soft=True)
    return json.loads(next(iter(rows[0].values()))) if rows else None


def policy_drift(expected: dict, found: dict | None) -> list[str]:
    """Every way the live policies differ from snowflake_policy.yaml: a policy missing, in another database or schema, or with another value."""
    if found is None:
        return ["the policies could not be read"]
    place = (expected["location"]["database"].upper(), expected["location"]["schema"].upper())
    drift = []
    for kind in ("password", "authentication"):
        want = expected[kind]
        held = [p for p in found[kind] if p["name"].upper() == want["name"].upper()]
        drift += [f"{kind} policy {p['name']} is in {p['database_name']}.{p['schema_name']}, not {place[0]}.{place[1]}"
                  for p in found[kind] if (p["database_name"].upper(), p["schema_name"].upper()) != place]
        if not held:
            drift.append(f"{kind} policy {want['name']} is missing")
            continue
        properties = held[0]["properties"]
        if kind == "password":
            drift += [f"password {key}: {properties.get('password_' + key)}, expected {value}"
                      for key, value in want.items() if key != "name" and str(properties.get("password_" + key)) != str(value)]
        else:
            methods = {m.strip().upper() for m in properties.get("authentication_methods", "").strip("[]").split(",") if m.strip()}
            if methods != {m.upper() for m in want["methods"]}:
                drift.append(f"authentication methods: {sorted(methods)}, expected {sorted(m.upper() for m in want['methods'])}")
    return drift


def collect(env, as_admin: bool = False) -> dict:
    connection = connection_of(env)
    if connection in FORBIDDEN_CONNECTIONS:
        sys.exit("that connection signs in as the operator's overall administrator account, which the audit never uses: use the auditor connection")
    role = snow(connection, "select current_role() as role")[0]["ROLE"].upper()
    if role in ADMIN and not as_admin:
        sys.exit("the Snowflake connection runs as an administrator role: use the read-only auditor role, or pass --as-admin to record the gap")
    expected = expected_policies()
    policies = found_policies(connection, expected["location"]["database"])
    risky = ", ".join(f"'{p}'" for p in RISKY)
    return {
        "audit_role": role,
        "users": lower(snow(connection, f"select name, type, disabled, has_password, has_rsa_public_key, has_mfa, default_role from {USAGE}.users where deleted_on is null")),
        "admin_holders": [r["grantee_name"] for r in lower(snow(connection, f"select grantee_name from {USAGE}.grants_to_users where role = 'ACCOUNTADMIN' and deleted_on is null"))],
        "network_policies": len(snow(connection, f"select name from {USAGE}.network_policies where deleted is null")),
        "account_network_policy": next((r["value"] for r in lower(snow(connection, "show parameters like 'NETWORK_POLICY' in account"))), ""),
        "monitors": len(snow(connection, "show resource monitors")),
        "warehouses": lower(snow(connection, "show warehouses")),
        "statement_timeout": int(next(r["value"] for r in lower(snow(connection, "show parameters like 'STATEMENT_TIMEOUT_IN_SECONDS' in account")))),
        "policy_drift": policy_drift(expected, policies),
        "password_policies": len(policies["password"]) if policies else 0,  # read from the live reader: the usage views lag by hours
        "authentication_policies": len(policies["authentication"]) if policies else None,
        "risky_grants": lower(snow(connection, f"select grantee_name, privilege from {USAGE}.grants_to_roles where deleted_on is null and granted_on in "
                                   f"('ACCOUNT', 'ROLE', 'WAREHOUSE', 'DATABASE') and privilege in ({risky}) and grantee_name not in "
                                   "('ACCOUNTADMIN', 'SECURITYADMIN', 'SYSADMIN', 'USERADMIN', 'ORGADMIN')")),
        "queries": lower(snow(connection, f"select role_name, count(*) as n from {USAGE}.query_history where start_time > dateadd(day, -7, current_timestamp()) group by 1")),
        "logins": lower(snow(connection, f"select user_name, first_authentication_factor as first_factor, second_authentication_factor as second_factor, "
                             f"count(*) as n from {USAGE}.login_history where is_success = 'YES' and event_timestamp > dateadd(day, -7, current_timestamp()) group by 1, 2, 3")),
    }


def principals(ev: dict) -> list[str]:
    return sorted({u["name"] for u in ev["users"] if u["name"].startswith("EDGARTOOLS")} | {r["grantee_name"] for r in ev["risky_grants"]
                  if r["grantee_name"].startswith("EDGARTOOLS")})


def controls(ev: dict) -> list[dict]:
    c = lambda *a, **k: control(NAME, *a, **k)  # noqa: E731
    users = {u["name"]: u for u in ev["users"]}
    admins = [users[a] for a in ev["admin_holders"] if a in users]
    seen = len(admins) == len(ev["admin_holders"]) and bool(admins)  # an auditor that cannot see the admins tests nothing
    total = sum(int(r["n"]) for r in ev["queries"]) or 1
    as_admin = sum(int(r["n"]) for r in ev["queries"] if (r["role_name"] or "").upper() == "ACCOUNTADMIN")
    admin_password = sum(int(r["n"]) for r in ev["logins"] if r["user_name"] in ev["admin_holders"] and r["first_factor"] == "PASSWORD" and not r["second_factor"])
    services = [u for u in ev["users"] if u.get("type") == "SERVICE"]
    ungoverned = [w["name"] for w in ev["warehouses"] if (w.get("resource_monitor") or "null") == "null"]
    defaulting = sum((a.get("default_role") or "").upper() == "ACCOUNTADMIN" for a in admins)
    return [
        c("IND", ev["audit_role"] not in ADMIN, {"audit_role": ev["audit_role"]}, "Use the read-only auditor role"),
        c("ADM", len(admins) >= 2 and all(a.get("has_mfa") == "true" for a in admins),
          {"admin_holders": len(ev["admin_holders"]), "visible": len(admins), "with_mfa": sum(a.get("has_mfa") == "true" for a in admins)},
          "Add a second admin; enrol MFA for every admin", tested=seen),
        c("OPS", as_admin / total < 0.05 and defaulting == 0, {"queries_7d": total, "as_accountadmin": as_admin, "admins_defaulting_to_accountadmin": defaulting},
          "Run loads and tools under named least-privilege roles; default the admin to a working role", tested=seen),
        c("AUT", admin_password == 0 and all(u.get("has_password") == "false" and u.get("has_rsa_public_key") == "true" for u in services),
          {"admin_password_logins_7d": admin_password, "service_users": len(services)}, "MFA or key pair for admins; key pair for every service user"),
        c("LPR", not ev["risky_grants"], {"roles_with_risky_grants": len({r["grantee_name"] for r in ev["risky_grants"]})}, "Revoke or justify in a change record"),
        c("NET", bool(ev["account_network_policy"]), {"account_policy_set": bool(ev["account_network_policy"]), "policies": ev["network_policies"]},
          "Set an account network policy; add one per service user"),
        c("CST", not ungoverned, {"warehouses_without_monitor": len(ungoverned), "monitors": ev["monitors"]}, "Create a resource monitor with a credit quota"),
        c("TMO", ev["statement_timeout"] <= MAX_TIMEOUT, {"statement_timeout_s": ev["statement_timeout"]}, "Set a timeout on the account or on each service user"),
        c("POL", ev["password_policies"] > 0 and (ev["authentication_policies"] or 0) > 0 and not ev.get("policy_drift"),
          {"password_policies": ev["password_policies"], "authentication_policies": ev["authentication_policies"], "drift_from_snowflake_policy_yaml": ev.get("policy_drift")},
          "Apply the access Terraform root from rules/snowflake_policy.yaml (policies live in the Gold database's POLICIES schema, no other database)",
          tested=ev["authentication_policies"] is not None),
    ]
