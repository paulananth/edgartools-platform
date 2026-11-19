"""PostgreSQL: the diagnostic login, superusers, login roles and the logging settings, read through that login."""
from __future__ import annotations

import re
import sys

from .base import control

NAME = "postgres"
PLATFORM_SUPERUSERS = {"postgres", "snowflake_superuser"}


def configured(env) -> bool:
    return bool(env.get("DIAGNOSE_DATABASE_URL"))


def collect(env, as_admin: bool = False) -> dict:
    import psycopg2

    try:
        conn = psycopg2.connect(re.sub(r"^postgresql\+\w+", "postgresql", env["DIAGNOSE_DATABASE_URL"]), connect_timeout=10)
    except psycopg2.Error:
        sys.exit("cannot connect as the diagnostic login")
    conn.set_session(readonly=True, autocommit=True)
    with conn.cursor() as cur:
        def ask(sql: str):
            cur.execute(sql)
            return cur.fetchall()
        return {
            "login": ask("select rolsuper, rolcreaterole, rolcreatedb, rolreplication from pg_roles where rolname = current_user")[0],
            "memberships": [r[0] for r in ask("select b.rolname from pg_auth_members m join pg_roles a on a.oid = m.member join pg_roles b on b.oid = m.roleid where a.rolname = current_user")],
            "writes": ask("select count(*) from information_schema.role_table_grants where grantee = current_user and privilege_type in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')")[0][0],
            "superusers": [r[0] for r in ask("select rolname from pg_roles where rolsuper and rolcanlogin")],
            "logins": ask("select rolname, rolconnlimit from pg_roles where rolcanlogin and rolname !~ '^(pg_|snowflake)'"),
            "settings": dict(ask("select name, setting from pg_settings where name in ('log_connections', 'log_disconnections', 'log_statement', 'pgaudit.log', 'ssl', 'password_encryption', 'statement_timeout', 'idle_in_transaction_session_timeout')")),
        }


def principals(ev: dict) -> list[str]:
    return []


def controls(ev: dict) -> list[dict]:
    c = lambda *a, **k: control(NAME, *a, **k)  # noqa: E731
    s = ev["settings"]
    logged = (s.get("log_connections") == "on" and s.get("log_disconnections") == "on" and s.get("log_statement") in ("ddl", "mod", "all")
              and s.get("ssl") == "on" and s.get("password_encryption") == "scram-sha-256")
    return [
        c("IND", not any(ev["login"]) and ev["memberships"] == ["pg_monitor"] and ev["writes"] == 0,
          {"flags": sum(bool(x) for x in ev["login"]), "memberships": ev["memberships"], "write_grants": ev["writes"]}, "Revoke extra membership or privilege"),
        c("LPR", set(ev["superusers"]) <= PLATFORM_SUPERUSERS, {"superusers": sorted(ev["superusers"])}, "Remove superuser from any other login"),
        c("LOG", logged and s.get("pgaudit.log", "none") != "none",
          {k: s.get(k) for k in ("log_connections", "log_disconnections", "log_statement", "ssl", "password_encryption", "pgaudit.log")},
          "Enable pgaudit write and role classes for the runtime logins, or record the accepted risk"),
        c("CST", all(limit >= 0 for _, limit in ev["logins"]), {"login_roles": len(ev["logins"]), "unlimited": sum(limit < 0 for _, limit in ev["logins"])}, "Set a connection limit per login role"),
        c("TMO", s.get("statement_timeout", "0") != "0" or s.get("idle_in_transaction_session_timeout", "0") != "0",
          {"statement_timeout": s.get("statement_timeout"), "idle_in_transaction_session_timeout": s.get("idle_in_transaction_session_timeout")}, "Set a bound on runtime logins"),
    ]
