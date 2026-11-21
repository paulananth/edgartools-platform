"""PostgreSQL: the diagnostic login, superusers, login roles and the logging settings, read through that login."""
from __future__ import annotations

import re
import sys

from edgar_warehouse.database_connections import DATABASES, instance_url

from .base import control

NAME = "postgres"
PLATFORM_SUPERUSERS = {"postgres", "snowflake_superuser"}
# Logins the platform makes with the instance and uses itself (the administrator account and the application login, a member
# of the platform's write group): a connection limit on them can lock the platform out, so the limit control does not count them.
PLATFORM_LOGINS = PLATFORM_SUPERUSERS | {"application"}


def configured(env) -> bool:
    from edgar_warehouse.database_connections import configured as named

    return named("mdm", env)


def collect(env, as_admin: bool = False) -> dict:
    import psycopg2

    try:
        from edgar_warehouse.database_connections import instance_url

        url = instance_url(env).set(drivername="postgresql").render_as_string(hide_password=False)
        conn = psycopg2.connect(url, connect_timeout=10)
    except psycopg2.Error:
        sys.exit("cannot connect as the diagnostic login")
    conn.set_session(readonly=True, autocommit=True)
    with conn.cursor() as cur:
        def ask(sql: str):
            cur.execute(sql)
            return cur.fetchall()
        return {
            "public_objects": {database: public_objects(env, database) for database in DATABASES},
            "login": ask("select rolsuper, rolcreaterole, rolcreatedb, rolreplication from pg_roles where rolname = current_user")[0],
            "memberships": [r[0] for r in ask("select b.rolname from pg_auth_members m join pg_roles a on a.oid = m.member join pg_roles b on b.oid = m.roleid where a.rolname = current_user")],
            "writes": ask("select count(*) from information_schema.role_table_grants where grantee = current_user and privilege_type in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')")[0][0],
            "superusers": [r[0] for r in ask("select rolname from pg_roles where rolsuper and rolcanlogin")],
            "logins": [row for row in ask("select rolname, rolconnlimit from pg_roles where rolcanlogin and rolname !~ '^(pg_|snowflake)'")
                       if row[0] not in PLATFORM_LOGINS],
            "role_settings": ask("select r.rolname, s.setconfig from pg_db_role_setting s join pg_roles r on r.oid = s.setrole where s.setdatabase = 0"),
            "settings": dict(ask("select name, setting from pg_settings where name in ('log_connections', 'log_disconnections', 'log_statement', 'pgaudit.log', 'ssl', 'password_encryption', 'statement_timeout', 'idle_in_transaction_session_timeout')")),
        }


def public_objects(env, database: str) -> int | None:
    """How many tables, views, sequences or functions sit in the database's public schema; None when it cannot be read."""
    import psycopg2

    try:
        url = instance_url(env, database).set(drivername="postgresql").render_as_string(hide_password=False)
        with psycopg2.connect(url, connect_timeout=10) as conn, conn.cursor() as cur:
            cur.execute("select (select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'public' "
                        "and c.relkind in ('r', 'p', 'v', 'm', 'S', 'f')) + (select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                        "where n.nspname = 'public' and not exists (select 1 from pg_depend d where d.objid = p.oid and d.deptype = 'e'))")
            return cur.fetchone()[0]
    except psycopg2.Error:
        return None


def principals(ev: dict) -> list[str]:
    return []


def controls(ev: dict) -> list[dict]:
    c = lambda *a, **k: control(NAME, *a, **k)  # noqa: E731
    s = ev["settings"]
    held = [count for count in ev.get("public_objects", {}).values() if count is not None]
    audited = [role for role, config in ev.get("role_settings", []) if any(c.startswith("pgaudit.log=") and c != "pgaudit.log=none" for c in config)]
    logged = (s.get("log_connections") == "on" and s.get("log_disconnections") == "on" and s.get("log_statement") in ("ddl", "mod", "all")
              and s.get("ssl") == "on" and s.get("password_encryption") == "scram-sha-256")
    return [
        c("IND", not any(ev["login"]) and ev["memberships"] == ["pg_monitor"] and ev["writes"] == 0,
          {"flags": sum(bool(x) for x in ev["login"]), "memberships": ev["memberships"], "write_grants": ev["writes"]}, "Revoke extra membership or privilege"),
        c("LPR", set(ev["superusers"]) <= PLATFORM_SUPERUSERS, {"superusers": sorted(ev["superusers"])}, "Remove superuser from any other login"),
        c("LOG", logged and (s.get("pgaudit.log", "none") != "none" or bool(audited)),
          {**{k: s.get(k) for k in ("log_connections", "log_disconnections", "log_statement", "ssl", "password_encryption", "pgaudit.log")},
           "roles_with_audit_classes": len(audited)},
          "Enable pgaudit write and role classes for the runtime logins, or record the accepted risk"),
        c("CST", all(limit >= 0 for _, limit in ev["logins"]), {"login_roles": len(ev["logins"]), "unlimited": sum(limit < 0 for _, limit in ev["logins"]), "unlimited_roles": sorted(r for r, limit in ev["logins"] if limit < 0)}, "Set a connection limit per login role"),
        c("SCH", all(count == 0 for count in held), {"public_objects": ev.get("public_objects")}, "Move every object out of public into its store's own schema, and expose nothing from public",
          tested=bool(held) and all(count is not None for count in ev.get("public_objects", {}).values())),
        c("TMO", s.get("statement_timeout", "0") != "0" or s.get("idle_in_transaction_session_timeout", "0") != "0",
          {"statement_timeout": s.get("statement_timeout"), "idle_in_transaction_session_timeout": s.get("idle_in_transaction_session_timeout")}, "Set a bound on runtime logins"),
    ]
