#!/usr/bin/env python3
"""Audit who can do what on the hosted data platform, read-only, and report each control as PASS, FAIL or NOT_TESTED.

Usage: access_audit.py [--json] [--as-admin] [--repo PATH]       (exit 1 when any control fails)

Evidence: Snowflake through the SnowCLI connection AUDIT_SNOWFLAKE_CONNECTION (a read-only auditor role; an administrator
role is refused unless --as-admin, which is itself reported as a finding), PostgreSQL through DIAGNOSE_DATABASE_URL (the
read-only diagnostic login), and this repository's tickets and Terraform. The output holds counts and names of roles and
controls only: never an address, a password, a key or a value from the data. The script changes nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

ADMIN = {"ACCOUNTADMIN", "SECURITYADMIN", "SYSADMIN", "USERADMIN", "ORGADMIN"}
RISKY = ("OWNERSHIP", "MANAGE GRANTS", "CREATE USER", "CREATE ROLE", "MANAGE WAREHOUSES", "CREATE INTEGRATION")
PLATFORM_SUPERUSERS = {"postgres", "snowflake_superuser"}
CHANGE_TIMEOUT = 4 * 3600  # an account statement timeout above this is a standing risk for an unattended login


def snow(connection: str, sql: str) -> list[dict]:
    done = subprocess.run(["snow", "sql", "-c", connection, "--format", "json", "-q", sql], capture_output=True, text=True,
                          check=False)
    if done.returncode:  # its message can quote the account
        sys.exit("a Snowflake read failed (check AUDIT_SNOWFLAKE_CONNECTION and its role)")
    return json.loads(done.stdout or "[]")


def lower(rows: list[dict]) -> list[dict]:
    return [{k.lower(): v for k, v in row.items()} for row in rows]


def snowflake_evidence(connection: str, as_admin: bool) -> dict:
    role = snow(connection, "select current_role() as role")[0]["ROLE"].upper()
    if role in ADMIN and not as_admin:
        sys.exit("the connection runs as an administrator role: use the read-only auditor role, or pass --as-admin to record the gap")
    usage = "snowflake.account_usage"
    return {
        "audit_role": role,
        "users": lower(snow(connection, "show users")),
        "admin_holders": [r["grantee_name"] for r in lower(snow(connection, "show grants of role ACCOUNTADMIN"))],
        "network_policies": len(snow(connection, "show network policies")),
        "account_network_policy": next((r["value"] for r in lower(snow(connection, "show parameters like 'NETWORK_POLICY' in account"))), ""),
        "monitors": len(snow(connection, "show resource monitors")),
        "warehouses": lower(snow(connection, "show warehouses")),
        "statement_timeout": int(next(r["value"] for r in lower(snow(connection, "show parameters like 'STATEMENT_TIMEOUT_IN_SECONDS' in account")))),
        "password_policies": len(snow(connection, "show password policies")),
        "authentication_policies": len(snow(connection, "show authentication policies")),
        "risky_grants": lower(snow(connection, "select grantee_name, privilege from %s.grants_to_roles where deleted_on is null and "
                                   "granted_on in ('ACCOUNT', 'ROLE', 'WAREHOUSE', 'DATABASE') and privilege in (%s) and grantee_name not in "
                                   "('ACCOUNTADMIN', 'SECURITYADMIN', 'SYSADMIN', 'USERADMIN', 'ORGADMIN')"
                                   % (usage, ", ".join(f"'{p}'" for p in RISKY)))),
        "queries": lower(snow(connection, "select role_name, count(*) as n from %s.query_history where start_time > dateadd(day, -7, "
                              "current_timestamp()) group by 1" % usage)),
        "logins": lower(snow(connection, "select user_name, first_authentication_factor as first_factor, second_authentication_factor "
                             "as second_factor, count(*) as n from %s.login_history where is_success = 'YES' and event_timestamp > "
                             "dateadd(day, -7, current_timestamp()) group by 1, 2, 3" % usage)),
    }


def postgres_evidence() -> dict:
    import psycopg2

    url = os.environ.get("DIAGNOSE_DATABASE_URL")
    if not url:
        sys.exit("DIAGNOSE_DATABASE_URL is not set: source the stores folder's reader.env (it is never printed)")
    try:
        conn = psycopg2.connect(re.sub(r"^postgresql\+\w+", "postgresql", url), connect_timeout=10)
    except psycopg2.Error:
        sys.exit("cannot connect as the diagnostic login")
    conn.set_session(readonly=True, autocommit=True)
    with conn.cursor() as cur:
        def ask(sql: str):
            cur.execute(sql)
            return cur.fetchall()
        return {
            "login": ask("select rolsuper, rolcreaterole, rolcreatedb, rolreplication from pg_roles where rolname = current_user")[0],
            "memberships": [r[0] for r in ask("select b.rolname from pg_auth_members m join pg_roles a on a.oid = m.member join pg_roles b "
                                              "on b.oid = m.roleid where a.rolname = current_user")],
            "writes": ask("select count(*) from information_schema.role_table_grants where grantee = current_user and privilege_type "
                          "in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')")[0][0],
            "superusers": [r[0] for r in ask("select rolname from pg_roles where rolsuper and rolcanlogin")],
            "logins": ask("select rolname, rolconnlimit from pg_roles where rolcanlogin and rolname !~ '^(pg_|snowflake)'"),
            "settings": dict(ask("select name, setting from pg_settings where name in ('log_connections', 'log_disconnections', "
                                 "'log_statement', 'pgaudit.log', 'ssl', 'password_encryption')")),
        }


def repository_evidence(repo: Path, names: list[str]) -> dict:
    tickets = "\n".join(p.read_text(errors="replace") for p in (repo / ".scratch").rglob("*.md")) if (repo / ".scratch").exists() else ""
    code = "\n".join(p.read_text(errors="replace") for p in (repo / "infra" / "terraform").rglob("*.tf")) if (repo / "infra").exists() else ""
    home = Path.home()
    plain, loose = 0, []
    connections = home / ".snowflake" / "connections.toml"
    if connections.exists():
        plain = len(re.findall(r"^\s*password\s*=", connections.read_text(), re.M | re.I))
        if stat.S_IMODE(connections.stat().st_mode) & 0o077:
            loose.append("connections.toml")
    for folder in (home / ".snowflake" / "keys", home / ".config" / "edgartools" / "hosted"):
        for p in folder.glob("*") if folder.exists() else []:
            if p.is_file() and stat.S_IMODE(p.stat().st_mode) & 0o077 and p.suffix != ".pub":
                loose.append(p.name)
    return {"ticketed": [n for n in names if n.lower() in tickets.lower()], "in_code": [n for n in names if n.lower() in code.lower()],
            "plaintext_passwords": plain, "loose_files": loose}


def control(cid, title, refs, ok, evidence, fix, tested=True):
    return {"id": cid, "title": title, "refs": refs, "result": ("PASS" if ok else "FAIL") if tested else "NOT_TESTED",
            "evidence": evidence, "fix": fix}


def evaluate(sf: dict, pg: dict, repo: dict) -> list[dict]:
    users = {u["name"]: u for u in sf["users"]}
    admins = [users[a] for a in sf["admin_holders"] if a in users]
    people = [u for u in sf["users"] if (u.get("type") or "PERSON") != "SERVICE"]
    total = sum(int(r["n"]) for r in sf["queries"]) or 1
    as_admin = sum(int(r["n"]) for r in sf["queries"] if (r["role_name"] or "").upper() == "ACCOUNTADMIN")
    admin_password = sum(int(r["n"]) for r in sf["logins"] if r["user_name"] in sf["admin_holders"] and r["first_factor"] == "PASSWORD"
                         and not r["second_factor"])
    services = [u for u in sf["users"] if u.get("type") == "SERVICE"]
    ungoverned = [w["name"] for w in sf["warehouses"] if (w.get("resource_monitor") or "null") == "null"]
    loose = [r for r in sf["risky_grants"]]
    return [
        control("AUD-00", "The audit ran as a read-only auditor, independent of what it audits", "SOC2 CC1.3; SOX ITGC segregation",
                sf["audit_role"] not in ADMIN, {"audit_role": sf["audit_role"]}, "Create a read-only auditor role (security, usage and governance viewers)"),
        control("AC-01", "Administrators: at least two (one break-glass), each with MFA", "SOX ITGC access; SOC2 CC6.1; ITIL service access",
                len(admins) >= 2 and all(a.get("has_mfa") == "true" for a in admins),
                {"admin_holders": len(admins), "with_mfa": sum(a.get("has_mfa") == "true" for a in admins)}, "Add a second admin; enrol MFA for every admin"),
        control("AC-02", "No administrator's default role is ACCOUNTADMIN", "SOC2 CC6.3 least privilege",
                all((a.get("default_role") or "").upper() != "ACCOUNTADMIN" for a in admins),
                {"admins_defaulting_to_accountadmin": sum((a.get("default_role") or "").upper() == "ACCOUNTADMIN" for a in admins)}, "Default to a working role"),
        control("AC-03", "Daily operations do not run as ACCOUNTADMIN", "SOX ITGC operations; SOC2 CC6.3",
                as_admin / total < 0.05, {"queries_7d": total, "as_accountadmin": as_admin}, "Run loads and monitoring under named least-privilege roles"),
        control("AC-04", "No password-only login by an administrator", "SOC2 CC6.1; SOX ITGC access",
                admin_password == 0, {"admin_password_logins_7d": admin_password}, "MFA or key pair for admins; service users never use an admin"),
        control("AC-05", "Service identities use key pair, no password", "SOC2 CC6.1",
                all(u.get("has_password") == "false" and u.get("has_rsa_public_key") == "true" for u in services),
                {"service_users": len(services)}, "Convert to key pair", tested=bool(services)),
        control("AC-06", "No role other than the admin roles holds ownership or grant-management privileges", "SOC2 CC6.3; SOX ITGC access",
                not loose, {"roles_with_risky_grants": len({r["grantee_name"] for r in loose})}, "Revoke or justify in a change record"),
        control("NW-01", "A network policy applies to the account", "SOC2 CC6.6 boundary protection",
                bool(sf["account_network_policy"]), {"account_policy_set": bool(sf["account_network_policy"]), "policies": sf["network_policies"]},
                "Set an account network policy; add one per service user"),
        control("OP-01", "Every warehouse has a resource monitor", "SOX ITGC operations; ITIL financial management",
                not ungoverned, {"warehouses_without_monitor": len(ungoverned), "monitors": sf["monitors"]}, "Create a monitor with a credit quota"),
        control("OP-02", "Account statement timeout is bounded", "SOC2 A1.1 capacity",
                sf["statement_timeout"] <= CHANGE_TIMEOUT, {"statement_timeout_s": sf["statement_timeout"]}, "Set a timeout on the account or on each service user"),
        control("AU-01", "Password and authentication policies exist", "SOC2 CC6.1; SOX ITGC access",
                sf["password_policies"] > 0 and sf["authentication_policies"] > 0,
                {"password_policies": sf["password_policies"], "authentication_policies": sf["authentication_policies"]}, "Create both"),
        control("DB-01", "The diagnostic login cannot write or administer", "SOC2 CC6.3; SOX ITGC access",
                not any(pg["login"]) and pg["memberships"] == ["pg_monitor"] and pg["writes"] == 0,
                {"flags": sum(bool(x) for x in pg["login"]), "memberships": pg["memberships"], "write_grants": pg["writes"]}, "Revoke extra membership or privilege"),
        control("DB-02", "Only the platform's own roles are superusers that can log in", "SOC2 CC6.3",
                set(pg["superusers"]) <= PLATFORM_SUPERUSERS, {"superusers": sorted(pg["superusers"])}, "Remove superuser from any other login"),
        control("DB-03", "Connections, disconnections and DDL are logged, and the connection is encrypted", "SOC2 CC7.2 monitoring; SOX ITGC operations",
                pg["settings"].get("log_connections") == "on" and pg["settings"].get("log_disconnections") == "on"
                and pg["settings"].get("log_statement") in ("ddl", "mod", "all") and pg["settings"].get("ssl") == "on"
                and pg["settings"].get("password_encryption") == "scram-sha-256",
                {k: pg["settings"].get(k) for k in ("log_connections", "log_disconnections", "log_statement", "ssl", "password_encryption")}, "Set the parameters"),
        control("DB-04", "Data-changing statements are audited (pgaudit) for the runtime logins", "SOX ITGC data integrity; SOC2 CC7.2",
                pg["settings"].get("pgaudit.log", "none") != "none", {"pgaudit.log": pg["settings"].get("pgaudit.log")},
                "Enable pgaudit write and role classes for the runtime logins, or record the accepted risk"),
        control("DB-05", "Every login role has a connection limit", "SOC2 A1.1 capacity",
                all(limit >= 0 for _, limit in pg["logins"]), {"login_roles": len(pg["logins"]), "unlimited": sum(limit < 0 for _, limit in pg["logins"])},
                "Set a limit per login role"),
        control("CM-01", "Every platform access role or user has a change record in a ticket", "SOX ITGC program change; ITIL change enablement",
                len(repo["ticketed"]) == repo["named"], {"named": repo["named"], "ticketed": len(repo["ticketed"])}, "Open a ticket with approver and back-out"),
        control("CM-02", "Every platform access role or user is defined in code", "SOX ITGC program change; SOC2 CC8.1",
                len(repo["in_code"]) == repo["named"], {"named": repo["named"], "in_terraform": len(repo["in_code"])}, "Add it to infra/terraform/access/snowflake"),
        control("SC-01", "No password is stored in plain text in a client file, and secret files are private", "SOC2 CC6.1; SOX ITGC access",
                repo["plaintext_passwords"] == 0 and not repo["loose_files"],
                {"plaintext_passwords": repo["plaintext_passwords"], "files_readable_by_others": len(repo["loose_files"])}, "Key pair or keychain; chmod 600"),
        control("KR-01", "Key and credential rotation is dated and owned", "SOC2 CC6.1; ITIL information security", False, {}, "Record owner and next rotation in the ticket", tested=False),
        control("AR-01", "Access is reviewed on a schedule with a signed record", "SOX ITGC access review; SOC2 CC6.2", False, {}, "Schedule a quarterly review ticket", tested=False),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--as-admin", action="store_true", help="allow an administrator connection; AUD-00 then fails")
    parser.add_argument("--repo", default=".")
    args = parser.parse_args(argv)
    connection = os.environ.get("AUDIT_SNOWFLAKE_CONNECTION")
    if not connection:
        sys.exit("AUDIT_SNOWFLAKE_CONNECTION is not set: name the SnowCLI connection of the read-only auditor role")
    sf, pg = snowflake_evidence(connection, args.as_admin), postgres_evidence()
    names = sorted({u["name"] for u in sf["users"] if u["name"].startswith("EDGARTOOLS")}
                   | {r["grantee_name"] for r in sf["risky_grants"] if r["grantee_name"].startswith("EDGARTOOLS")} | {"EDGARTOOLS_PROD_LOG_READER"})
    repo = repository_evidence(Path(args.repo), names)
    repo["named"] = len(names)
    results = evaluate(sf, pg, repo)
    if args.json:
        print(json.dumps(results))
    else:
        for r in results:
            print(f"{r['result']:10} {r['id']}  {r['title']}  [{r['refs']}]\n           evidence: {r['evidence']}"
                  + (f"\n           fix: {r['fix']}" if r["result"] != "PASS" else ""))
        counts = {k: sum(r["result"] == k for r in results) for k in ("PASS", "FAIL", "NOT_TESTED")}
        print(f"== {counts['PASS']} pass, {counts['FAIL']} fail, {counts['NOT_TESTED']} not tested")
    return 1 if any(r["result"] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
