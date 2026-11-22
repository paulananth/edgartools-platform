#!/usr/bin/env python3
"""Give a fresh hosted PostgreSQL instance the stores' logins and two databases, from the stores folder's duty files.

    python <this skill>/scripts/provision_hosted_store.py --service <pg service>            # lists what it would do
    python <this skill>/scripts/provision_hosted_store.py --service <pg service> --confirm  # does it

A duty is one login and one file in the stores folder (default ~/.config/edgartools/hosted/), each holding two URLs of that login,
one a database: the data database (mdm, rdm, silver) and the control database (rules, bookkeeping, change_journal), as
`edgar_warehouse.database_connections` names them. The files: `owner.env` (the instance's administrator), `worker.env` (the loader, `edgar_loader`), `governance.env` (the governance
login) and `reader.env` (the diagnostic login, `ops_reader`). A missing duty file is made with a new password; a login is created with
the password its file already holds, so none is rotated. The administrator comes from the PostgreSQL service the instance's creation
saved (~/.pg_service.conf and ~/.pgpass); every file then takes the new instance's address, and the owner file the administrator's
new password. Prints names and counts only, never an address or a password.
The schemas come next (docs/runbooks/edgar-intelligence/init.md, "Initialize a hosted store", step 3).
"""

from __future__ import annotations

import argparse
import configparser
import os
import re
import secrets
import shlex
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from uuid import uuid4

from edgar_warehouse.database_connections import DATABASES as GROUPS_OF_STORES, url_variable

DATABASES = tuple(GROUPS_OF_STORES)  # data, control
SETTINGS = {url_variable(stores[0]): database for database, stores in GROUPS_OF_STORES.items()}  # each URL and its database
OWNER_FILE = "owner.env"
# Each duty: its file, its login, the databases it connects to and the group roles that carry its privileges. A group holds
# what its store's `init` grants it; the login holds nothing of its own, so no login can create anything (ddl_free checks the loader).
RUNTIME_ROLES = ("mdm_runtime", "rdm_runtime", "rules_agent", "bookkeeping_runtime", "change_journal_runtime", "silver_runtime")
LOADER = "edgar_loader"
GOVERNANCE = "governance"
READER = "ops_reader"  # reads sessions, locks and statistics (pg_monitor) and no table
DUTIES = {
    "worker.env": (LOADER, DATABASES, RUNTIME_ROLES),
    "governance.env": (GOVERNANCE, DATABASES, ("mdm_governance", "rules_governance")),
    "reader.env": (READER, DATABASES, ("pg_monitor",)),
}
# Groups put into other groups: the Bookkeeping worker duty, and the Rules agent's access for Rules governance.
GROUPS = {"bookkeeping_control": ("bookkeeping_runtime",), "rules_agent": ("rules_governance",)}
BUILT_IN = {"pg_monitor"}
LINE = re.compile(r"^(export )?([A-Z_]+)=(.*)$")


class Refused(ValueError):
    """A refusal this script words itself, so its text holds no address and no password."""


def private_write(path: Path, value: str) -> None:
    temporary = path.with_name(path.name + "." + uuid4().hex)
    with open(temporary, "w", opener=lambda p, flags: os.open(p, flags, 0o600)) as out:
        out.write(value)
        out.flush()
        os.fsync(out.fileno())
    temporary.replace(path)


def _value(raw: str) -> str:
    words = shlex.split(raw) if raw else [""]
    return words[0] if words else ""


def read_urls(folder: Path, name: str) -> dict[str, str]:
    """The file's URLs by setting; empty when the file is absent."""
    path = folder / name
    found = {}
    for line in path.read_text().splitlines() if path.exists() else ():
        match = LINE.match(line.strip())
        if match and match[2] in SETTINGS and _value(match[3]).startswith("postgres"):
            found[match[2]] = _value(match[3])
    return found


def read_url(folder: Path, name: str) -> str | None:
    """The file's login as a URL: both of its URLs name the same login and password, each its own database. None when the
    file holds neither; a file that holds one, or two logins, or a URL naming another database, is refused."""
    found = read_urls(folder, name)
    if not found:
        return None
    if set(found) != set(SETTINGS):
        raise Refused(f"{name} must hold {' and '.join(SETTINGS)}")
    for setting, url in found.items():
        if urlsplit(url).path.strip("/") != SETTINGS[setting]:
            raise Refused(f"{name}: {setting} must name the {SETTINGS[setting]} database")
    if len({urlsplit(url).netloc for url in found.values()}) != 1:
        raise Refused(f"{name}: its two URLs name two logins")
    return next(iter(found.values()))


def duty_file(url: str) -> str:
    """A duty file: one URL a database, each with the login and the address of `url`."""
    part = urlsplit(url)
    lines = [f"unset {' '.join(SETTINGS)}"] + [
        f"export {setting}={shlex.quote(urlunsplit(part._replace(path='/' + database)))}" for setting, database in SETTINGS.items()]
    return "\n".join(lines) + "\n"


def logins(folder: Path, admin: str) -> dict[str, tuple[str, set[str]]]:
    """Each duty's login with its one password and the databases it connects to, from the files that exist. A file that names
    another login than its duty's is refused: the file is the duty."""
    held: dict[str, tuple[str, set[str]]] = {}
    for name, (login, databases, _) in DUTIES.items():
        url = read_url(folder, name)
        if url is None:
            continue
        part = urlsplit(url)
        user = unquote(part.username or "")
        if user != login:
            raise Refused(f"{name} names {user or 'no login'}, and the {name.split('.')[0]} duty is {login}")
        held[login] = (unquote(part.password or ""), set(databases))
    if admin in held:
        raise Refused(f"{admin} is the administrator and cannot also be a duty login")
    return held


def readdress(url: str, host: str, port: int, admin: str, admin_password: str) -> str:
    """The URL on the new instance; the administrator's URL takes its new password."""
    part = urlsplit(url)
    user, password = unquote(part.username or ""), unquote(part.password or "")
    if user == admin:
        password = admin_password
    credentials = quote(user, safe="") + (":" + quote(password, safe="") if password else "")
    return urlunsplit((part.scheme, f"{credentials}@{host}:{port}", part.path, part.query, part.fragment))


def rewrite(folder: Path, host: str, port: int, admin: str, admin_password: str) -> int:
    changed = 0
    for name in (OWNER_FILE, *DUTIES):
        path = folder / name
        if not path.exists():
            continue
        lines = []
        for line in path.read_text().splitlines():
            match = LINE.match(line.strip())
            if match and match[2] in SETTINGS and _value(match[3]).startswith("postgres"):
                line = f"{match[1] or ''}{match[2]}={shlex.quote(readdress(_value(match[3]), host, port, admin, admin_password))}"
                changed += 1
            lines.append(line)
        private_write(path, "\n".join(lines) + "\n")
    return changed


def ensure_files(folder: Path, host: str, port: int, admin: dict[str, str] | None = None) -> list[str]:
    """Make each missing duty file with a new password for its login (and the owner file from the administrator). The names made."""
    made = []
    if admin is not None and not (folder / OWNER_FILE).exists():
        url = f"postgresql://{quote(admin['user'], safe='')}:{quote(admin['password'], safe='')}@{host}:{port}"
        private_write(folder / OWNER_FILE, duty_file(url))
        made.append(OWNER_FILE)
    for name, (login, _, _) in DUTIES.items():
        if (folder / name).exists() and read_url(folder, name):
            continue
        url = f"postgresql://{login}:{quote(secrets.token_urlsafe(24), safe='')}@{host}:{port}"
        private_write(folder / name, duty_file(url))
        made.append(name)
    return made


def ddl_free(conn, role: str, database: str) -> None:
    """Refuse a login that could change a schema: a CREATE on any schema of the database, an object it owns, or the
    superuser, create-database or create-role flag."""
    with conn.cursor() as cur:
        cur.execute("""SELECT coalesce(string_agg(nspname, ','), '') FROM pg_namespace WHERE nspname !~ '^pg_'
                       AND nspname <> 'information_schema' AND has_schema_privilege(%s, oid, 'CREATE')""", (role,))
        creates = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM pg_class WHERE relowner = (SELECT oid FROM pg_roles WHERE rolname = %s)", (role,))
        owned = cur.fetchone()[0]
        cur.execute("""SELECT count(*) FROM pg_roles WHERE rolname = %s
                       AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls)""", (role,))
        privileged = cur.fetchone()[0]
    if creates:
        raise Refused(f"{role} can create in {database}: {creates}")
    if owned:
        raise Refused(f"{role} owns {owned} objects in {database}")
    if privileged:
        raise Refused(f"{role} is a superuser, or can create databases or roles")


def administrator(service: str) -> dict[str, str]:
    """Host, port, user and password of the service the instance's creation saved."""
    services = configparser.ConfigParser()
    services.read(Path(os.environ.get("PGSERVICEFILE", Path.home() / ".pg_service.conf")))
    if service not in services:
        raise Refused(f"no PostgreSQL service {service}: create the instance through the snowflake-postgres skill")
    entry = services[service]
    host, port, user = entry.get("host"), entry.get("port", "5432"), entry.get("user")
    for line in Path(os.environ.get("PGPASSFILE", Path.home() / ".pgpass")).read_text().splitlines():
        fields = re.split(r"(?<!\\):", line, maxsplit=4)
        if len(fields) == 5 and fields[0] in (host, "*") and fields[1] in (port, "*") and fields[3] in (user, "*"):
            return {"host": host, "port": port, "user": user, "password": fields[4].replace("\\:", ":")}
    raise Refused(f"no saved password for service {service}")


def provision(conn, held: dict[str, tuple[str, set[str]]], admin: str, confirm: bool) -> list[str]:
    from psycopg2 import sql

    done = []
    groups_of = {login: groups for _, (login, _, groups) in DUTIES.items()}
    with conn.cursor() as cur:
        for role, (password, _) in sorted(held.items()):
            cur.execute("SELECT rolcanlogin FROM pg_roles WHERE rolname = %s", (role,))
            row = cur.fetchone()
            if row is None:
                done.append(f"create login {role}")
                if confirm:
                    cur.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s NOSUPERUSER NOCREATEDB NOCREATEROLE")
                                .format(sql.Identifier(role)), (password,))
            elif not row[0]:
                raise Refused(f"{role} exists and cannot log in")
        for login in sorted(held):
            for group in groups_of[login]:
                if group in BUILT_IN:
                    done.append(f"give {login} {group}: sessions, locks and statistics, no table")
                else:
                    cur.execute("SELECT rolcanlogin FROM pg_roles WHERE rolname = %s", (group,))
                    row = cur.fetchone()
                    if row is None:
                        done.append(f"create group {group}")
                        if confirm:
                            cur.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(group)))
                    elif row[0] and group not in held:  # a login of an earlier layout: its privileges stay, its login ends
                        done.append(f"{group} stops being a login and stays a group")
                        if confirm:
                            cur.execute(sql.SQL("ALTER ROLE {} NOLOGIN").format(sql.Identifier(group)))
                    done.append(f"put {login} in {group}")
                if confirm:
                    cur.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(group), sql.Identifier(login)))
        for group, members in GROUPS.items():
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (group,))
            made = any(group in groups for groups in groups_of.values())
            if cur.fetchone() is None and not made:
                done.append(f"create group {group}")
                if confirm:
                    cur.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(group)))
            for member in members:
                if not any(member in groups for groups in groups_of.values()):
                    raise Refused(f"no duty names {member}, which {group} needs")
                done.append(f"put {member} in {group}")
                if confirm:
                    cur.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(group), sql.Identifier(member)))
        for database in DATABASES:
            cur.execute("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s", (database,))
            row = cur.fetchone()
            if row is not None and row[0] != admin:
                raise Refused(f"{database} exists, owned by {row[0]}: reset it (the runbook's step 2), never adopt it")
            if row is None:
                done.append(f"create database {database}")
                if confirm:
                    cur.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(database), sql.Identifier(admin)))
            readers = sorted(role for role, (_, databases) in held.items() if database in databases and role != READER)
            done.append(f"{database}: connect for {', '.join(readers)} (never TEMPORARY: run-time code creates no table)")
            if confirm:
                cur.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database)))
                for role in readers:
                    cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database), sql.Identifier(role)))
                if READER in held:  # the diagnostic login reads catalogs and statistics: CONNECT, never a table
                    done.append(f"{database}: connect for {READER}")
                    cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database), sql.Identifier(READER)))
            elif READER in held:
                done.append(f"{database}: connect for {READER}")
    return done


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--service", required=True, help="The PostgreSQL service the instance's creation saved")
    parser.add_argument("--stores", type=Path, default=Path.home() / ".config/edgartools/hosted")
    parser.add_argument("--confirm", action="store_true", help="Do it (without it, only list it)")
    args = parser.parse_args(argv)
    try:
        import psycopg2

        admin = administrator(args.service)
        if args.confirm:
            made = ensure_files(args.stores, admin["host"], int(admin["port"]), admin)
            if made:
                print(f"made {', '.join(made)} (a new password for each login it names)")
        else:
            missing = [name for name in (OWNER_FILE, *DUTIES) if not (args.stores / name).exists()]
            if missing:
                print(f"would make {', '.join(missing)}")
        held = logins(args.stores, admin["user"])
        conn = psycopg2.connect(host=admin["host"], port=admin["port"], user=admin["user"], password=admin["password"],
                                dbname="postgres", sslmode="require", connect_timeout=10)
        conn.autocommit = True
        try:
            for step in provision(conn, held, admin["user"], args.confirm):
                print(step)
        finally:
            conn.close()
        if args.confirm and LOADER in held:
            for database in DATABASES:
                with psycopg2.connect(host=admin["host"], port=admin["port"], user=admin["user"], password=admin["password"],
                                      dbname=database, sslmode="require", connect_timeout=10) as check:
                    ddl_free(check, LOADER, database)
            print(f"{LOADER} can create nothing in any of the {len(DATABASES)} databases")
        if args.confirm:
            print(f"{rewrite(args.stores, admin['host'], int(admin['port']), admin['user'], admin['password'])} URLs now name the new instance")
        else:
            print("Nothing changed. Run again with --confirm.")
    except Refused as refused:
        print(refused, file=sys.stderr)
        return 1
    except Exception as error:  # noqa: BLE001  a driver's or a URL parser's error can quote the address: its class only
        print(f"failed: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
