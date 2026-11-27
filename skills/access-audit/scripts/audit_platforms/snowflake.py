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


def connections() -> set[str]:
    """The SnowCLI connection names on this machine (names only)."""
    try:
        done = subprocess.run(["snow", "connection", "list", "--format", "json"], capture_output=True, text=True, check=False)
        return {row["connection_name"] for row in json.loads(done.stdout or "[]")}
    except (OSError, ValueError, KeyError, TypeError):  # no SnowCLI on this machine, or an unreadable list
        return set()


def configured(env) -> bool:
    """Audited whenever its connection exists: the default auditor connection needs no variable, and a machine without it skips Snowflake instead of ending the whole audit."""
    return connection_of(env) in connections()


def snow(connection: str, sql: str, soft: bool = False):
    done = subprocess.run(["snow", "sql", "-c", connection, "--format", "json", "-q", sql], capture_output=True, text=True, check=False)
    if done.returncode:  # its message can quote the account
        if soft:
            return None  # a view the role cannot read: the control is then not tested, never passed
        sys.exit("a Snowflake read failed (check the auditor connection and its role)")
    return json.loads(done.stdout or "[]")


def lower(rows):
    return [{k.lower(): (str(v).lower() if isinstance(v, bool) else v) for k, v in row.items()} for row in rows]


def places() -> dict[str, str]:
    """Each platform database that keeps exactly one schema, with that schema (the blocks of snowflake.yaml that name one)."""
    import yaml
    from edgar_warehouse.rules import files

    names = yaml.safe_load((files.ROOT / "snowflake.yaml").read_text(encoding="utf-8"))
    return {b["database"].upper(): b["schema"].upper() for b in names.values() if isinstance(b, dict) and "schema" in b}


def credential_policies(connection: str) -> int:
    password = snow(connection, f"select count(*) as n from {USAGE}.password_policies where deleted is null")
    attached = snow(connection, f"select count(distinct policy_db || '.' || policy_schema || '.' || policy_name) as n from {USAGE}.policy_references "
                                "where policy_kind = 'AUTHENTICATION_POLICY'")
    return int(password[0]["N"]) + int(attached[0]["N"])


def schemas(connection: str, kept: dict[str, str]) -> list[dict] | None:
    """Every schema of each platform database, read in its own information schema; None when one cannot be read."""
    found = []
    for database in kept:
        rows = snow(connection, f"select '{database}' as catalog_name, schema_name from {database}.information_schema.schemata", soft=True)
        if rows is None:
            return None
        found += lower(rows)
    return found


def schema_drift(kept: dict[str, str], found: list[dict] | None) -> list[str] | None:
    """Every schema of a platform database other than the one it keeps (INFORMATION_SCHEMA is Snowflake's own view), and each kept
    schema that is absent."""
    if found is None:
        return None
    held = {(r["catalog_name"].upper(), r["schema_name"].upper()) for r in found}
    missing = [f"{d}.{s} is missing" for d, s in kept.items() if (d, s) not in held]
    return missing + sorted(f"{r['catalog_name']}.{r['schema_name']}" for r in found if r["catalog_name"].upper() in kept
                  and r["schema_name"].upper() not in (kept[r["catalog_name"].upper()], "INFORMATION_SCHEMA"))


def collect(env, as_admin: bool = False) -> dict:
    connection = connection_of(env)
    if connection in FORBIDDEN_CONNECTIONS:
        sys.exit("that connection signs in as the operator's overall administrator account, which the audit never uses: use the auditor connection")
    role = snow(connection, "select current_role() as role")[0]["ROLE"].upper()
    if role in ADMIN and not as_admin:
        sys.exit("the Snowflake connection runs as an administrator role: use the read-only auditor role, or pass --as-admin to record the gap")
    kept = places()
    risky = ", ".join(f"'{p}'" for p in RISKY)
    return {
        "audit_role": role,
        "users": lower(snow(connection, f"select name, type, disabled, has_password, has_rsa_public_key, has_mfa, default_role from {USAGE}.users where deleted_on is null")),
        "admin_holders": [r["grantee_name"] for r in lower(snow(connection, f"select grantee_name from {USAGE}.grants_to_users where role = 'ACCOUNTADMIN' and deleted_on is null"))],
        "network_policies": len(snow(connection, f"select name from {USAGE}.network_policies where deleted is null")),
        "account_network_policy": next((r["value"] for r in lower(snow(connection, "show parameters like 'NETWORK_POLICY' in account"))), ""),
        "statement_timeout": int(next(r["value"] for r in lower(snow(connection, "show parameters like 'STATEMENT_TIMEOUT_IN_SECONDS' in account")))),
        # A role sees only the policies it holds a privilege on, so SHOW would list none: the usage views list every one (they lag by
        # hours). An authentication policy has no view of its own and is found by its attachments.
        "credential_policies": credential_policies(connection),
        "schema_drift": schema_drift(kept, schemas(connection, kept)),
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
    interactive = sorted(u["name"] for u in ev["users"] if u["name"].startswith("EDGARTOOLS") and u.get("type") != "SERVICE")
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
        c("TMO", ev["statement_timeout"] <= MAX_TIMEOUT, {"statement_timeout_s": ev["statement_timeout"]}, "Set a timeout on the account or on each service user"),
        c("POL", ev["credential_policies"] == 0 and not interactive, {"credential_policies": ev["credential_policies"], "platform_logins_not_service": interactive},
          "Make every platform login a TYPE = SERVICE user (no password possible) and drop any credential policy object: Snowflake keeps one only in a database",
          title="Credential rules are native: every platform login is a service user, and no credential policy object exists in any database"),
        c("SCH", not ev["schema_drift"], {"schema_drift": ev["schema_drift"]},
          "Keep in each platform database only the one schema rules/snowflake.yaml names: drop the others (skills/aws-snowflake-operations/scripts/one_schema_sql.py)",
          title="Each platform database holds only the one schema rules/snowflake.yaml names", tested=ev["schema_drift"] is not None),
    ]
