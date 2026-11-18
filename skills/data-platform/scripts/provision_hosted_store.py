#!/usr/bin/env python3
"""Give a fresh hosted PostgreSQL instance the stores' logins and six databases, from the stores folder's own files.

    python <this skill>/scripts/provision_hosted_store.py --service <pg service>            # lists what it would do
    python <this skill>/scripts/provision_hosted_store.py --service <pg service> --confirm  # does it

The stores folder (default ~/.config/edgartools/hosted/) is authoritative: each login is created with the password its
own URL there holds, so no login is rotated. The instance's administrator comes from the PostgreSQL service the
instance's creation saved (~/.pg_service.conf and ~/.pgpass); every URL in the folder then gets the new instance's
address, and the administrator's URLs its new password. Prints names and counts only, never an address or a password.
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

DATABASES = ("mdm", "rdm", "rules", "bookkeeping", "change_journal", "silver")
FILES = ("connection.env", "worker.env", "governance.env", "reader.env")
# The diagnostic login: it reads sessions, locks and statistics (pg_monitor) and no table, and connects to no store.
# Its URL is the only one in reader.env, which is made on the first confirmed run.
READER, READER_FILE, READER_SETTING = "ops_reader", "reader.env", "DIAGNOSE_DATABASE_URL"
OPTIONAL = {READER_FILE}
# Group roles a login is put into: the Bookkeeping worker duty, and the Rules agent's access for Rules governance.
GROUPS = {"bookkeeping_control": ("bookkeeping_runtime",), "rules_agent": ("rules_governance",)}
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


def read_urls(folder: Path) -> dict[str, dict[str, str]]:
    """Each file's PostgreSQL URLs by setting name."""
    found = {}
    for name in FILES:
        urls = {}
        if name in OPTIONAL and not (folder / name).exists():
            found[name] = urls
            continue
        for line in (folder / name).read_text().splitlines():
            match = LINE.match(line.strip())
            if match and _value(match[3]).startswith("postgres"):
                urls[match[2]] = _value(match[3])
        found[name] = urls
    return found


def logins(urls: dict[str, dict[str, str]], admin: str) -> dict[str, tuple[str, set[str]]]:
    """Each login other than the administrator: its one password and the databases its URLs name.
    Two URLs that give one login different passwords are refused, and so is a store no login connects to."""
    held: dict[str, tuple[str, set[str]]] = {}
    for name, settings in urls.items():
        for setting, url in settings.items():
            part = urlsplit(url)
            user, password = unquote(part.username or ""), unquote(part.password or "")
            if not user or user == admin:
                continue
            database = part.path.strip("/")
            if user in held and held[user][0] != password:
                raise Refused(f"{setting} in {name} gives {user} another password than its other URLs")
            held.setdefault(user, (password, set()))[1].add(database)
    named = set().union(*(databases for _, databases in held.values()))
    missing = [database for database in DATABASES if database not in named]
    if missing:
        raise Refused(f"no URL in {', '.join(FILES)} names a login for {', '.join(missing)}")
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
    for name in FILES:
        if name in OPTIONAL and not (folder / name).exists():
            continue
        lines = []
        for line in (folder / name).read_text().splitlines():
            match = LINE.match(line.strip())
            if match and _value(match[3]).startswith("postgres"):
                moved = readdress(_value(match[3]), host, port, admin, admin_password)
                line = f"{match[1] or ''}{match[2]}={shlex.quote(moved)}"
                changed += 1
            lines.append(line)
        private_write(folder / name, "\n".join(lines) + "\n")
    return changed


def ensure_reader(folder: Path, host: str, port: int) -> bool:
    """Make reader.env with a new password for the diagnostic login, unless it is there. True when it made it."""
    path = folder / READER_FILE
    if path.exists():
        return False
    url = f"postgresql://{READER}:{quote(secrets.token_urlsafe(24), safe='')}@{host}:{port}/postgres"
    private_write(path, f"export {READER_SETTING}={shlex.quote(url)}\n")
    return True


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
        if READER in held:
            done.append(f"give {READER} pg_monitor: sessions, locks and statistics, no table")
            if confirm:
                cur.execute(sql.SQL("GRANT pg_monitor TO {}").format(sql.Identifier(READER)))
        for group, members in GROUPS.items():
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (group,))
            if cur.fetchone() is None and group not in held:  # a login made above serves as the group too
                done.append(f"create group {group}")
                if confirm:
                    cur.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(group)))
            for member in members:
                if member not in held:
                    raise Refused(f"no URL names {member}, which {group} needs")
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
                    cur.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(database),
                                                                             sql.Identifier(admin)))
            readers = sorted(role for role, (_, databases) in held.items() if database in databases)
            done.append(f"{database}: connect and temporary tables for {', '.join(readers)}")
            if confirm:
                cur.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database)))
                for role in readers:
                    cur.execute(sql.SQL("GRANT CONNECT, TEMPORARY ON DATABASE {} TO {}").format(sql.Identifier(database),
                                                                                    sql.Identifier(role)))
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
        if args.confirm and ensure_reader(args.stores, admin["host"], int(admin["port"])):
            print(f"made {READER_FILE} with a new login {READER}")
        elif not (args.stores / READER_FILE).exists():
            print(f"would make {READER_FILE} with a new login {READER} (diagnosis reads with it, never the owner)")
        urls = read_urls(args.stores)
        held = logins(urls, admin["user"])
        conn = psycopg2.connect(host=admin["host"], port=admin["port"], user=admin["user"], password=admin["password"],
                                dbname="postgres", sslmode="require", connect_timeout=10)
        conn.autocommit = True
        try:
            for step in provision(conn, held, admin["user"], args.confirm):
                print(step)
        finally:
            conn.close()
        if args.confirm:
            count = rewrite(args.stores, admin["host"], int(admin["port"]), admin["user"], admin["password"])
            print(f"{count} URLs in {', '.join(FILES)} now name the new instance")
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
