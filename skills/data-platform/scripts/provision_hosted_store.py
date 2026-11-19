#!/usr/bin/env python3
"""Give a fresh hosted PostgreSQL instance the stores' logins and six databases, from the stores folder's own files.

    python <this skill>/scripts/provision_hosted_store.py --service <pg service>            # lists what it would do
    python <this skill>/scripts/provision_hosted_store.py --service <pg service> --confirm  # does it
    ... --loader   every runtime URL in the stores folder names the one login edgar_loader
    ... --retire   with --loader: the six runtime logins become NOLOGIN groups (no URL may still name one)

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
FILES = ("owner.env", "worker.env", "governance.env", "reader.env")
# The diagnostic login: it reads sessions, locks and statistics (pg_monitor) and no table, and connects to no store.
# Its URL is the only one in reader.env, which is made on the first confirmed run.
READER, READER_FILE, READER_SETTING = "ops_reader", "reader.env", "DIAGNOSE_DATABASE_URL"
OPTIONAL = {READER_FILE}
# Every load uses one login, `edgar_loader`: a member of the runtime role of each store, so it holds exactly their
# privileges and none of its own. None of them can create anything (ddl_free checks it): a load changes rows, never a
# schema. A store's schema is made and changed by its owner login, with the commands of the initialize runbook.
LOADER = "edgar_loader"
RUNTIME_ROLES = ("mdm_runtime", "rdm_runtime", "rules_agent", "bookkeeping_runtime", "change_journal_runtime",
                 "silver_runtime")
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


LOADER_FILES = ("worker.env", "governance.env")  # the files that name a runtime login; reader.env never does


def _loader_password(folder: Path) -> str:
    """The password the loader's URLs already hold (one login, one password), else a new one."""
    for name in LOADER_FILES:
        path = folder / name
        for line in path.read_text().splitlines() if path.exists() else ():
            match = LINE.match(line.strip())
            if match and _value(match[3]).startswith("postgres"):
                part = urlsplit(_value(match[3]))
                if unquote(part.username or "") == LOADER and part.password:
                    return part.password
    return quote(secrets.token_urlsafe(24), safe="")


def use_loader(folder: Path) -> int:
    """Point every runtime URL in the stores folder (worker.env, governance.env) at the one loader login. The
    administrator's and the governance logins are not runtime URLs and stay. Each file that changes is kept as
    `<file>.before-loader` (mode 0600) the first time. Returns how many URLs changed (0 when all are already it)."""
    password, total = _loader_password(folder), 0
    for name in LOADER_FILES:
        path = folder / name
        if not path.exists():
            continue
        changed, lines = 0, []
        for line in path.read_text().splitlines():
            match = LINE.match(line.strip())
            if match and _value(match[3]).startswith("postgres"):
                part = urlsplit(_value(match[3]))
                if unquote(part.username or "") in RUNTIME_ROLES:
                    moved = urlunsplit((part.scheme, f"{LOADER}:{password}@{part.hostname}:{part.port}", part.path, part.query, part.fragment))
                    line = f"{match[1] or ''}{match[2]}={shlex.quote(moved)}"
                    changed += 1
            lines.append(line)
        if changed:
            kept = folder / f"{name}.before-loader"
            if not kept.exists():
                private_write(kept, path.read_text())
            private_write(path, "\n".join(lines) + "\n")
        total += changed
    return total


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


def ensure_reader(folder: Path, host: str, port: int) -> bool:
    """Make reader.env with a new password for the diagnostic login, unless it is there. True when it made it."""
    path = folder / READER_FILE
    if path.exists():
        return False
    url = f"postgresql://{READER}:{quote(secrets.token_urlsafe(24), safe='')}@{host}:{port}/postgres"
    private_write(path, f"export {READER_SETTING}={shlex.quote(url)}\n")
    return True


def retire(conn, confirm: bool, named: frozenset[str] | set[str] = frozenset()) -> list[str]:
    """The runtime roles stop being logins once every load uses `edgar_loader`: each becomes a NOLOGIN group, and the loader
    keeps its privileges through its membership. Refused, changing nothing, while a URL in the stores folder still names one
    (`named`: run `--loader` first). NOLOGIN stops new logins and ends no open session, so the roles are made NOLOGIN first and the
    sessions logged in as them counted after, and if any remain they are made logins again and the run is refused: a login made
    between a check and the change cannot slip through. A role that cannot log in, or does not exist, is left alone."""
    still = sorted(set(named) & set(RUNTIME_ROLES))
    if still:
        raise Refused(f"a URL in the stores folder still names {', '.join(still)}: run --loader first")
    steps, change = [], []
    with conn.cursor() as cur:
        for role in RUNTIME_ROLES:
            cur.execute("SELECT rolcanlogin FROM pg_roles WHERE rolname = %s", (role,))
            found = cur.fetchone()
            if not found or not found[0]:
                steps.append(f"{role} cannot log in already")
            else:
                change.append(role)
                steps.append(f"{'retire' if confirm else 'would retire'} {role}: NOLOGIN")
        if confirm:
            for role in change:  # the names are the fixed RUNTIME_ROLES, never read from anywhere
                cur.execute(f'ALTER ROLE "{role}" NOLOGIN')
        open_sessions = {}
        for role in change:
            cur.execute("SELECT count(*) FROM pg_stat_activity WHERE usename = %s", (role,))
            count = cur.fetchone()[0]
            if count:
                open_sessions[role] = count
        if open_sessions:
            if confirm:
                for role in change:  # a refusal leaves every role as it was
                    cur.execute(f'ALTER ROLE "{role}" LOGIN')
            raise Refused(f"{', '.join(sorted(open_sessions))} still has open sessions logged in as it: end them, then run again")
    return steps


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
        if LOADER in held:
            for role in RUNTIME_ROLES:
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
                if cur.fetchone() is None and role not in held:
                    done.append(f"create group {role}")
                    if confirm:
                        cur.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
                done.append(f"put {LOADER} in {role}")
                if confirm:
                    cur.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(role), sql.Identifier(LOADER)))
        if READER in held:
            done.append(f"give {READER} pg_monitor: sessions, locks and statistics, no table")
            if confirm:
                cur.execute(sql.SQL("GRANT pg_monitor TO {}").format(sql.Identifier(READER)))
        for group, members in GROUPS.items():
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (group,))
            made = group in held or (LOADER in held and group in RUNTIME_ROLES)  # a login or runtime role made above
            if cur.fetchone() is None and not made:
                done.append(f"create group {group}")
                if confirm:
                    cur.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(group)))
            for member in members:
                if member not in held and not (LOADER in held and member in RUNTIME_ROLES):
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
            if READER in held:  # the diagnostic login reads catalogs and statistics: CONNECT, never a table
                done.append(f"{database}: connect for {READER}")
                if confirm:
                    cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database), sql.Identifier(READER)))
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
    parser.add_argument("--loader", action="store_true",
                        help=f"Point every runtime URL in worker.env at the one login {LOADER}, which creates nothing")
    parser.add_argument("--retire", action="store_true",
                        help="Make the six runtime logins NOLOGIN groups: refused while a URL names one or a session is logged in as one (use with --loader)")
    args = parser.parse_args(argv)
    try:
        import psycopg2

        admin = administrator(args.service)
        if args.confirm and ensure_reader(args.stores, admin["host"], int(admin["port"])):
            print(f"made {READER_FILE} with a new login {READER}")
        elif not (args.stores / READER_FILE).exists():
            print(f"would make {READER_FILE} with a new login {READER} (diagnosis reads with it, never the owner)")
        if args.loader and args.confirm:
            print(f"{use_loader(args.stores)} runtime URLs in the stores folder now name {LOADER} (each changed file is kept as <file>.before-loader)")
        elif args.loader:
            print(f"would point every runtime URL in worker.env at {LOADER}, a member of {len(RUNTIME_ROLES)} runtime roles")
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
        if args.confirm and LOADER in held:
            for database in DATABASES:
                with psycopg2.connect(host=admin["host"], port=admin["port"], user=admin["user"], password=admin["password"],
                                      dbname=database, sslmode="require", connect_timeout=10) as check:
                    ddl_free(check, LOADER, database)
            print(f"{LOADER} can create nothing in any of the {len(DATABASES)} databases")
        if args.confirm:
            count = rewrite(args.stores, admin["host"], int(admin["port"]), admin["user"], admin["password"])
            print(f"{count} URLs in {', '.join(FILES)} now name the new instance")
        if args.retire:  # last: the loader's safety check and the new addresses have passed
            conn = psycopg2.connect(host=admin["host"], port=admin["port"], user=admin["user"], password=admin["password"],
                                    dbname="postgres", sslmode="require", connect_timeout=10)
            conn.autocommit = True
            try:
                for step in retire(conn, args.confirm, set(held)):
                    print(step)
            finally:
                conn.close()
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
