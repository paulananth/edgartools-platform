#!/usr/bin/env python3
"""Persistent shared PostgreSQL 16 with silver beside MDM, so a run completes both together.

Run with uv run --extra mdm infra/scripts/local-test-stores.py --help.
Connection details are written to a private env file, never stdout.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import sys
import time
from uuid import uuid4

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from edgar_warehouse.database_connections import DATABASES, database_of, url_variable  # noqa: E402

# Two databases, each store a schema under its own owner (skills/data-platform/CONNECTIONS.md).
STORES = ("mdm", "rdm", "rules", "bookkeeping", "change_journal")
ALL_STORES = (*STORES, "silver")
# Mastering and MDM's registration authority keep `public`, so MDM's owner owns the data database; the control database is
# the server's, and each store's owner gets CREATE on its database for its own schema.
DATABASE_OWNER = {"data": "mdm_owner", "control": "postgres"}


def databases(stores) -> list[str]:
    return [database for database in DATABASES if any(database_of(store) == database for store in stores)]


def runtime_login(store: str) -> str:
    return store + "_runtime"


def owner_login(store: str) -> str:
    return store + "_owner"
EXTRA_LOGINS = ("mdm_governance", "rules_governance")
LOADER, GOVERNANCE = "edgar_loader", "governance"  # the duty logins: one each, a member of the roles that hold the privileges
IMAGE = "postgres:16-alpine"
LABEL = "org.edgartools.local-tests.owner"
# Server settings for a full load (ticket 194): the default 4 MB of work memory sends each merge statement's
# working set to temporary files. A store made earlier keeps its settings: `ALTER SYSTEM SET work_mem` and reload.
SERVER_SETTINGS = ("-c", "work_mem=256MB")


def private_write(path: Path, value: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex)
    with open(temporary, "w", opener=lambda p, flags: os.open(p, flags, 0o600)) as out:
        out.write(value)
        out.flush()
        os.fsync(out.fileno())
    temporary.replace(path)


def file_hash(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


class LocalStores:
    def __init__(self, root: Path, worktree: Path):
        self.root = root.resolve()
        self.owner = str(worktree.resolve())
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def folder(self, name: str) -> Path:
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", name):
            raise ValueError("Use a short lowercase environment name, with digits or dashes")
        return self.root / "environments" / name

    @contextmanager
    def locked(self, name: str):
        folder = self.folder(name)
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (folder / ".lock").open("a") as lock:
            os.chmod(lock.name, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield folder

    def docker(self, *args: str, stdout=subprocess.PIPE):
        found = subprocess.run(["docker", *args], stdout=stdout, stderr=subprocess.PIPE, timeout=180)
        if found.returncode:
            # Docker and SQL errors can include credentials or row values.
            raise RuntimeError("Local Docker operation failed; no connection or data values were printed")
        return found.stdout

    def resource(self, kind: str, name: str):
        found = subprocess.run(["docker", kind, "inspect", name], capture_output=True, timeout=15)
        if found.returncode:
            return None
        return json.loads(found.stdout)[0]

    def identity(self, name: str, *, create=False):
        folder = self.folder(name)
        path = folder / "identity.json"
        if path.exists():
            value = json.loads(path.read_text())
            owner = value["owner"]
            if owner != self.owner:
                # A deleted checkout cannot refresh a moved port. Adopt the copy.
                # A checkout that still exists keeps it.
                if not (Path(owner).is_absolute() and not Path(owner).is_dir()):
                    raise ValueError("Environment belongs to another worktree; use your own name")
                value["owner"] = self.owner
                private_write(path, json.dumps(value))
            return value
        if not create:
            raise ValueError("Environment does not exist")
        value = {"owner": self.owner, "password": secrets.token_hex(24), "restoring": False,
                 "stores": list(STORES)}
        private_write(path, json.dumps(value))
        return value

    def stores(self, name: str):
        # Before store selection existed every environment contained six stores.
        selected = self.identity(name).get("stores", list(ALL_STORES))
        if (not isinstance(selected, list) or len(set(selected)) != len(selected)
                or not set(STORES) <= set(selected) <= set(ALL_STORES)):
            raise ValueError("Environment store selection is invalid")
        return [store for store in ALL_STORES if store in selected]

    def owned(self, name: str, identity: dict):
        container = "edgartools-local-" + name
        volume = container + "-data"
        for kind, resource in (("container", container), ("volume", volume)):
            found = self.resource(kind, resource)
            if found:
                labels = found.get("Config", {}).get("Labels", {}) if kind == "container" else found.get("Labels", {})
                label = (labels or {}).get(LABEL)
                if label != identity["owner"]:
                    # The container keeps the label from creation. A gone checkout
                    # no longer matches the adopted identity.
                    if not (isinstance(label, str) and Path(label).is_absolute() and not Path(label).is_dir()):
                        raise ValueError("Resource ownership differs; refusing to change it")
        return container, volume

    def url(self, name: str, database="postgres", user="postgres"):
        identity = self.identity(name)
        container, _ = self.owned(name, identity)
        found = self.resource("container", container)
        if not found or not found["State"]["Running"]:
            raise ValueError("Environment is stopped")
        ports = found["NetworkSettings"]["Ports"]["5432/tcp"]
        if len(ports) != 1 or ports[0]["HostIp"] != "127.0.0.1":
            raise ValueError("Environment must publish PostgreSQL on loopback only")
        return URL.create("postgresql+psycopg2", username=user, password=identity["password"],
                          host="127.0.0.1", port=int(ports[0]["HostPort"]), database=database)

    def engine(self, name: str, database="postgres", user="postgres"):
        return create_engine(self.url(name, database, user), hide_parameters=True,
                             connect_args={"connect_timeout": 3})

    def start(self, name: str, *, empty=False, include_silver=False):
        identity = self.identity(name, create=True)
        if identity["restoring"]:
            raise ValueError("An interrupted restore is retained for diagnosis; choose a fresh copy name")
        if include_silver and "silver" not in self.stores(name):
            identity["stores"] = list(ALL_STORES)
            private_write(self.folder(name) / "identity.json", json.dumps(identity))
        container, volume = self.owned(name, identity)
        if not self.resource("volume", volume):
            self.docker("volume", "create", "--label", f"{LABEL}={self.owner}", volume)
        found = self.resource("container", container)
        if not found:
            # Pass a private env file, not the password in command arguments or reports.
            env = self.folder(name) / "postgres.env"
            private_write(env, "POSTGRES_PASSWORD=" + identity["password"] + "\n")
            self.docker("run", "-d", "--name", container, "--label", f"{LABEL}={self.owner}",
                        "--restart", "unless-stopped", "--env-file", str(env),
                        "-p", "127.0.0.1::5432", "-v", f"{volume}:/var/lib/postgresql/data", IMAGE,
                        *SERVER_SETTINGS)
        elif not found["State"]["Running"]:
            self.docker("start", container)
        deadline = time.monotonic() + 30
        while True:
            engine = self.engine(name)
            try:
                with engine.connect() as conn:
                    version = conn.scalar(text("SHOW server_version_num"))
                    if int(version) // 10000 != 16:
                        raise ValueError("PostgreSQL 16 is required")
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Local PostgreSQL did not become ready") from None
                time.sleep(.2)
            finally:
                engine.dispose()
        self.recover_backup(name)
        self.provision(name, migrate=not empty, include_silver=include_silver)
        self.connections(name, include_silver=include_silver)

    def connections(self, name: str, *, include_silver=False):
        def duty(user: str) -> dict:
            """One URL a database: the file names both, each with its database."""
            return {url_variable(DATABASES[database][0]): self.url(name, database, user).render_as_string(hide_password=False)
                    for database in DATABASES}

        worker = {**duty(LOADER), "MDM_APPLICATION_ROLE": "mdm_runtime",
                  "BOOKKEEPING_MANIFEST_ROOT": (self.folder(name) / "manifests").as_uri()}
        for filename, values in (("owner.env", duty("postgres")), ("worker.env", worker), ("governance.env", duty(GOVERNANCE))):
            # Clear a previous shell's settings before choosing a duty.
            lines = ["unset " + " ".join(sorted({url_variable(store) for store in ALL_STORES}))
                     + " BOOKKEEPING_ADMIN_DATABASE_URL MDM_REGISTRATION_DATABASE_URL"]
            lines += [f"export {key}={shlex.quote(value)}" for key, value in values.items()]
            private_write(self.folder(name) / filename, "\n".join(lines) + "\n")

    def provision(self, name: str, *, migrate=True, include_silver=False):
        from edgar_warehouse.mdm.store import migrate as mdm
        from edgar_warehouse.rdm.database import migrate as rdm
        from edgar_warehouse.silver_writer.database import migrate as silver
        from edgar_warehouse.rules.db import migrate as rules
        from edgar_warehouse.bookkeeping.clean.database import migrate as bookkeeping
        from edgar_warehouse.change_journal.database import migrate as journal
        selected = ALL_STORES if include_silver else STORES
        admin = self.engine(name)
        quote = admin.dialect.identifier_preparer.quote
        try:
            with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                roles = {owner_login(store): False for store in selected}
                roles.update({runtime_login(store): True for store in selected})
                roles.update({role: True for role in (*EXTRA_LOGINS, LOADER, GOVERNANCE)})
                roles.update(bookkeeping_control=False)
                for role, login in roles.items():
                    held = conn.execute(text("SELECT rolsuper,rolcreatedb,rolcreaterole,rolcanlogin,rolbypassrls FROM pg_roles WHERE rolname=:r"), {"r": role}).first()
                    if held:
                        if any((held[0], held[1], held[2], held[4])) or held[3] != login:
                            raise ValueError("Existing role has incompatible privileges")
                    else:
                        suffix = "LOGIN PASSWORD :password" if login else "NOLOGIN"
                        conn.execute(text(f"CREATE ROLE {quote(role)} NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS {suffix}"), {"password": self.identity(name)["password"]})
                for database in databases(selected):
                    owner = conn.scalar(text("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=:d"), {"d": database})
                    if owner and owner != DATABASE_OWNER[database]:
                        raise ValueError("Database has a different owner; refusing adoption")
                    if not owner:
                        conn.exec_driver_sql(f"CREATE DATABASE {quote(database)} OWNER {quote(DATABASE_OWNER[database])}")
                    conn.exec_driver_sql(f"REVOKE CONNECT ON DATABASE {quote(database)} FROM PUBLIC")
                for store in selected:
                    database = quote(database_of(store))
                    conn.exec_driver_sql(f"GRANT CONNECT, CREATE ON DATABASE {database} TO {quote(owner_login(store))}")
                    conn.exec_driver_sql(f"GRANT CONNECT ON DATABASE {database} TO {quote(runtime_login(store))}")
                for store, login in (("mdm", "mdm_governance"), ("rules", "rules_governance")):
                    conn.exec_driver_sql(f"GRANT CONNECT ON DATABASE {quote(database_of(store))} TO {quote(login)}")
                members = [(parent, LOADER) for parent in {runtime_login(store) for store in selected}] + [
                    (parent, GOVERNANCE) for parent in EXTRA_LOGINS]
                for parent, member in (("bookkeeping_control", "bookkeeping_runtime"),
                                       ("rules_runtime", "rules_governance"), *members):
                    if not conn.scalar(text("SELECT pg_has_role(:m,:p,'MEMBER')"), {"m": member, "p": parent}):
                        conn.exec_driver_sql(f"GRANT {quote(parent)} TO {quote(member)}")
            if migrate:
                migrations = {"mdm": mdm, "rdm": rdm, "silver": silver, "rules": rules,
                              "bookkeeping": bookkeeping, "change_journal": journal}
                for store in selected:
                    engine = self.engine(name, database_of(store))
                    @event.listens_for(engine, "connect")
                    def owner_role(connection, _, selected=owner_login(store)):
                        with connection.cursor() as cursor:
                            cursor.execute(f"SET ROLE {quote(selected)}")
                        connection.commit()
                    try:
                        key = "application_role" if store == "mdm" else "agent_role" if store == "rules" else "runtime_role"
                        role = "bookkeeping_control" if store == "bookkeeping" else runtime_login(store)
                        named = {"database_name": database_of(store)} if store in ("rdm", "bookkeeping", "change_journal") else {}
                        migrations[store](engine, **{key: role}, **named)
                    finally:
                        engine.dispose()
                self.execution_access(name)
        finally:
            admin.dispose()

    def execution_access(self, name: str):
        from edgar_warehouse.bookkeeping.clean.database import grant_profile
        from edgar_warehouse.workers import PROFILES

        book = self.engine(name, database_of("bookkeeping"))
        try:
            for profile in PROFILES:
                grant_profile(book, profile=profile, worker="bookkeeping_runtime")
        finally:
            book.dispose()
        mdm = self.engine(name, database_of("mdm"))
        try:
            from edgar_warehouse.mdm.registration import grant_registrar

            grant_registrar(mdm, "mdm_governance")
        finally:
            mdm.dispose()

    def contents(self, name: str):
        """Private checksums, never row values, prove what a restored copy holds."""
        result = {}
        for database in databases(self.stores(name)):
            engine = self.engine(name, database)
            try:
                with engine.connect() as conn:
                    tables = conn.execute(text("SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2")).all()
                    for schema, table in tables:
                        q = conn.dialect.identifier_preparer.quote
                        digest = hashlib.sha256()
                        count = 0
                        rows = conn.execution_options(stream_results=True).execute(text(f"SELECT to_jsonb(t)::text FROM {q(schema)}.{q(table)} t ORDER BY to_jsonb(t)::text COLLATE \"C\""))
                        for row in rows:
                            value = row[0].encode()
                            digest.update(len(value).to_bytes(8, "big") + value)
                            count += 1
                        result[f"{database}.{schema}.{table}"] = {"rows": count, "sha256": digest.hexdigest()}
            finally:
                engine.dispose()
        return result

    def recover_backup(self, name: str):
        marker = self.folder(name) / "backup-paused.json"
        if not marker.exists():
            return
        previous = json.loads(marker.read_text())
        base = {d + "_runtime" for d in self.stores(name)}
        if not base <= set(previous) <= base | set(EXTRA_LOGINS) or any(type(v) is not bool for v in previous.values()):
            raise ValueError("Backup recovery record is invalid; retained for diagnosis")
        engine = self.engine(name)
        try:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                for role, login in previous.items():
                    conn.exec_driver_sql(f'ALTER ROLE "{role}" {"LOGIN" if login else "NOLOGIN"}')
            marker.unlink()
        finally:
            engine.dispose()

    def backup(self, name: str):
        identity = self.identity(name)
        container, _ = self.owned(name, identity)
        self.recover_backup(name)
        admin = self.engine(name)
        target = self.root / "backups" / (name + "-" + uuid4().hex)
        target.mkdir(mode=0o700, parents=True)
        try:
            with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                candidates = [*(d + "_runtime" for d in self.stores(name)), *EXTRA_LOGINS]
                previous = {role: bool(login) for role in candidates
                            if (login := conn.scalar(text("SELECT rolcanlogin FROM pg_roles WHERE rolname=:r"), {"r": role})) is not None}
                private_write(self.folder(name) / "backup-paused.json", json.dumps(previous))
                for role in previous:
                    conn.exec_driver_sql(f'ALTER ROLE "{role}" NOLOGIN')
                if conn.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE backend_type='client backend' AND pid<>pg_backend_pid()")):
                    raise ValueError("Workers or other connections are active; retry the backup after they finish")
            contents = self.contents(name)
            files = {}
            for database in databases(self.stores(name)):
                path = target / (database + ".dump")
                # Owners are kept: each schema belongs to its store's owner, and the restore gives it back.
                with open(path, "wb", opener=lambda p, flags: os.open(p, flags, 0o600)) as out:
                    self.docker("exec", container, "pg_dump", "-U", "postgres", "-Fc", "-d", database, stdout=out)
                files[path.name] = file_hash(path)
            private_write(target / "manifest.json", json.dumps(
                {"files": files, "contents": contents, "stores": self.stores(name)}, sort_keys=True))
            return target
        finally:
            admin.dispose()
            self.recover_backup(name)

    def restore(self, name: str, snapshot: Path):
        manifest = json.loads((snapshot / "manifest.json").read_text())
        selected = set(manifest.get("stores", ()))
        if (not set(STORES) <= selected <= set(ALL_STORES)
                or set(manifest["files"]) != {d + ".dump" for d in databases(selected)}):
            raise ValueError("Backup must contain the five core stores and optionally silver, one file a database")
        for file, sha in manifest["files"].items():
            if file_hash(snapshot / file) != sha:
                raise ValueError("Backup checksum differs")
        if (self.folder(name) / "identity.json").exists():
            raise ValueError("Copy requires a new environment name; existing data is never overwritten")
        self.start(name, empty=True, include_silver="silver" in selected)
        identity = self.identity(name)
        identity["restoring"] = True
        private_write(self.folder(name) / "identity.json", json.dumps(identity))

        container, _ = self.owned(name, identity)
        for database in databases(self.stores(name)):
            with (snapshot / (database + ".dump")).open("rb") as data:
                found = subprocess.run(["docker", "exec", "-i", container, "pg_restore", "-U", "postgres", "--exit-on-error", "-d", database], stdin=data, capture_output=True, timeout=180)
                if found.returncode:
                    raise RuntimeError("Restore failed; retained the incomplete environment for diagnosis")
        if self.contents(name) != manifest["contents"]:
            raise ValueError("Restored contents differ; baseline was not promoted")
        self.provision(name, include_silver="silver" in selected)
        identity["restoring"] = False
        private_write(self.folder(name) / "identity.json", json.dumps(identity))


    def publish_baseline(self, name: str):
        """Serialize one checked dump/restore; replacing a text pointer needs no service."""
        with (self.root / ".baseline.lock").open("a") as lock:
            os.chmod(lock.name, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            snapshot = self.backup(name)
            probe = "baseline-check-" + uuid4().hex[:12]
            try:
                with self.locked(probe):
                    self.restore(probe, snapshot)
            finally:
                if (self.folder(probe) / "identity.json").exists():
                    self.stop(probe)
            temporary = self.root / (".baseline-" + uuid4().hex)
            private_write(temporary, str(snapshot) + "\n")
            temporary.replace(self.root / "baseline")
            return snapshot

    def stop(self, name: str):
        container, _ = self.owned(name, self.identity(name))
        if found := self.resource("container", container):
            if found["State"]["Running"]:
                self.docker("stop", "--time", "5", container)


SERVER_ENV = "EDGARTOOLS_LOCAL_TEST_SERVER"
DEFAULT_SERVER = "local-test-server"


def commits_behind(folder: Path) -> int | None:
    """How many commits `origin/main` (as last fetched) has that this checkout lacks; None when git cannot say."""
    try:
        done = subprocess.run(["git", "-C", str(folder), "rev-list", "--count", "HEAD..origin/main"],
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return int(done.stdout) if done.returncode == 0 and done.stdout.strip().isdigit() else None


def error_text(exc: Exception) -> str:
    """What to print for a failure. A driver or subprocess message may hold source data or a credential, so only
    its class is shown; this script's own errors and the engine's control refusal (`Blocked`) are their own text."""
    if type(exc).__name__ == "Blocked":
        return f"Blocked: {exc}"
    return str(exc) if type(exc) in (ValueError, RuntimeError) else type(exc).__name__


def server_name(argument: str | None, environ=os.environ) -> str:
    """The store a command works on: the name given, else the one the machine's configuration names
    (`EDGARTOOLS_LOCAL_TEST_SERVER`), else `local-test-server`. No other name is built in (ticket 192)."""
    return argument or environ.get(SERVER_ENV) or DEFAULT_SERVER


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home() / ".local/share/edgartools/local-tests")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("up", "stop", "status", "backup", "copy"):
        part = sub.add_parser(command)
        part.add_argument("name", nargs="?", help=f"The store (default: ${SERVER_ENV}, else {DEFAULT_SERVER})")
        if command == "up":
            part.add_argument("--no-silver", action="store_true", help="Leave silver out (a core-only isolated test)")
        if command == "copy":
            part.add_argument("--snapshot", type=Path, help="Omit to copy the latest verified baseline")
        if command == "backup":
            part.add_argument("--baseline", action="store_true", help="Check a restore, then use this baseline for future copies")
    args = parser.parse_args()
    args.name = server_name(args.name)
    behind = commits_behind(Path.cwd())
    if behind:
        print(f"This checkout is {behind} commit(s) behind origin/main: a store migrated by newer code is refused "
              "by older code. Update it first.", file=sys.stderr)
    stores = LocalStores(args.root, Path.cwd())
    try:
        with stores.locked(args.name):
            if args.command == "up":
                stores.start(args.name, include_silver=not args.no_silver)
            elif args.command == "stop":
                stores.stop(args.name)
            elif args.command == "backup":
                snapshot = stores.publish_baseline(args.name) if args.baseline else stores.backup(args.name)
                print(json.dumps({"snapshot": str(snapshot), "baseline": args.baseline}))
                return
            elif args.command == "copy":
                snapshot = args.snapshot or Path((stores.root / "baseline").read_text().strip())
                stores.restore(args.name, snapshot.resolve())
            identity = stores.identity(args.name)
            container, _ = stores.owned(args.name, identity)
            found = stores.resource("container", container)
            print(json.dumps({"name": args.name, "state": found["State"]["Status"] if found else "missing", "stores": len(stores.stores(args.name)), "env_file": str(stores.folder(args.name) / "connection.env")}))
    except Exception as exc:
        # Driver/subprocess exception messages may hold source data or credentials.
        message = error_text(exc)
        parser.exit(1, message + "\n")


if __name__ == "__main__":
    main()
