#!/usr/bin/env python3
"""Independent persistent PostgreSQL 16 copies for local agent work.

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
import subprocess
import time
from uuid import uuid4

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL


STORES = {
    "mdm": ("MDM_DATABASE_URL", "mdm"),
    "rdm": ("RDM_DATABASE_URL", "rdm"),
    "silver": ("SILVER_DATABASE_URL", "silver"),
    "rules": ("RULES_DATABASE_URL", "rules"),
    "bookkeeping_clean": ("BOOKKEEPING_CLEAN_DATABASE_URL", "bookkeeping"),
    "change_journal_clean": ("CHANGE_JOURNAL_DATABASE_URL", "journal"),
}
IMAGE = "postgres:16-alpine"
LABEL = "org.edgartools.local-tests.owner"


def private_write(path: Path, value: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(path, "w", opener=lambda p, flags: os.open(p, flags, 0o600)) as out:
        out.write(value)
    path.chmod(0o600)


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
            if value["owner"] != self.owner:
                raise ValueError("Environment belongs to another worktree; use your own name")
            return value
        if not create:
            raise ValueError("Environment does not exist")
        value = {"owner": self.owner, "password": secrets.token_hex(24), "restoring": False}
        private_write(path, json.dumps(value))
        return value

    def owned(self, name: str, identity: dict):
        container = "edgartools-local-" + name
        volume = container + "-data"
        for kind, resource in (("container", container), ("volume", volume)):
            found = self.resource(kind, resource)
            if found:
                labels = found.get("Config", {}).get("Labels", {}) if kind == "container" else found.get("Labels", {})
                if (labels or {}).get(LABEL) != identity["owner"]:
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

    def start(self, name: str, *, empty=False):
        identity = self.identity(name, create=True)
        if identity["restoring"]:
            raise ValueError("An interrupted restore is retained for diagnosis; choose a fresh copy name")
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
                        "-p", "127.0.0.1::5432", "-v", f"{volume}:/var/lib/postgresql/data", IMAGE)
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
        self.provision(name, migrate=not empty)
        env_lines = []
        for database, (variable, _) in STORES.items():
            runtime = database + "_runtime"
            env_lines.append(f"export {variable}='{self.url(name, database, runtime).render_as_string(hide_password=False)}'")
            migration = variable.replace("_DATABASE_URL", "_MIGRATION_DATABASE_URL")
            env_lines.append(f"export {migration}='{self.url(name, database).render_as_string(hide_password=False)}'")
        private_write(self.folder(name) / "connection.env", "\n".join(env_lines) + "\n")

    def provision(self, name: str, *, migrate=True):
        from edgar_warehouse.mdm.clean.store import migrate as mdm
        from edgar_warehouse.rdm.database import migrate as rdm
        from edgar_warehouse.silver_writer.database import migrate as silver
        from edgar_warehouse.rules.db import migrate as rules
        from edgar_warehouse.bookkeeping.clean.database import migrate as bookkeeping
        from edgar_warehouse.change_journal.database import migrate as journal
        admin = self.engine(name)
        quote = admin.dialect.identifier_preparer.quote
        try:
            with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                for database in STORES:
                    for role, login in ((database + "_owner", False), (database + "_runtime", True)):
                        held = conn.execute(text("SELECT rolsuper,rolcreatedb,rolcreaterole,rolcanlogin,rolbypassrls FROM pg_roles WHERE rolname=:r"), {"r": role}).first()
                        if held:
                            if any((held[0], held[1], held[2], held[4])) or held[3] != login:
                                raise ValueError("Existing role has incompatible privileges")
                        else:
                            suffix = "LOGIN PASSWORD :password" if login else "NOLOGIN"
                            conn.execute(text(f"CREATE ROLE {quote(role)} NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS {suffix}"), {"password": self.identity(name)["password"]})
                    owner = conn.scalar(text("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=:d"), {"d": database})
                    if owner and owner != database + "_owner":
                        raise ValueError("Database has a different owner; refusing adoption")
                    if not owner:
                        conn.exec_driver_sql(f"CREATE DATABASE {quote(database)} OWNER {quote(database + '_owner')}")
                    conn.exec_driver_sql(f"REVOKE CONNECT ON DATABASE {quote(database)} FROM PUBLIC")
                    conn.exec_driver_sql(f"GRANT CONNECT ON DATABASE {quote(database)} TO {quote(database + '_runtime')}")
                if not conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname='rules_approver'")):
                    conn.exec_driver_sql("CREATE ROLE rules_approver NOLOGIN")
            if migrate:
                migrations = (mdm, rdm, silver, rules, bookkeeping, journal)
                for database, migration in zip(STORES, migrations):
                    engine = self.engine(name, database)
                    @event.listens_for(engine, "connect")
                    def owner_role(connection, _, selected=database + "_owner"):
                        with connection.cursor() as cursor:
                            cursor.execute(f"SET ROLE {quote(selected)}")
                        connection.commit()
                    try:
                        key = "application_role" if database == "mdm" else "agent_role" if database == "rules" else "runtime_role"
                        migration(engine, **{key: database + "_runtime"})
                    finally:
                        engine.dispose()
        finally:
            admin.dispose()

    def contents(self, name: str):
        """Private checksums, never row values, prove what a restored copy holds."""
        result = {}
        for database in STORES:
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

    def backup(self, name: str):
        identity = self.identity(name)
        container, _ = self.owned(name, identity)
        admin = self.engine(name)
        target = self.root / "backups" / (name + "-" + uuid4().hex)
        target.mkdir(mode=0o700, parents=True)
        try:
            with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                for database in STORES:
                    conn.exec_driver_sql(f'ALTER ROLE "{database}_runtime" NOLOGIN')
                if conn.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE backend_type='client backend' AND pid<>pg_backend_pid()")):
                    raise ValueError("Workers or other connections are active; retry the backup after they finish")
            contents = self.contents(name)
            files = {}
            for database in STORES:
                path = target / (database + ".dump")
                with open(path, "wb", opener=lambda p, flags: os.open(p, flags, 0o600)) as out:
                    self.docker("exec", container, "pg_dump", "-U", "postgres", "-Fc", "--no-owner", "--no-acl", "-d", database, stdout=out)
                files[path.name] = file_hash(path)
            private_write(target / "manifest.json", json.dumps({"files": files, "contents": contents}, sort_keys=True))
            return target
        finally:
            with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                for database in STORES:
                    conn.exec_driver_sql(f'ALTER ROLE "{database}_runtime" LOGIN')
            admin.dispose()

    def restore(self, name: str, snapshot: Path):
        manifest = json.loads((snapshot / "manifest.json").read_text())
        if set(manifest["files"]) != {d + ".dump" for d in STORES}:
            raise ValueError("Backup does not contain exactly the six stores")
        for file, sha in manifest["files"].items():
            if file_hash(snapshot / file) != sha:
                raise ValueError("Backup checksum differs")
        if (self.folder(name) / "identity.json").exists():
            raise ValueError("Copy requires a new environment name; existing data is never overwritten")
        self.start(name, empty=True)
        identity = self.identity(name)
        identity["restoring"] = True
        private_write(self.folder(name) / "identity.json", json.dumps(identity))

        container, _ = self.owned(name, identity)
        for database in STORES:
            with (snapshot / (database + ".dump")).open("rb") as data:
                found = subprocess.run(["docker", "exec", "-i", container, "pg_restore", "-U", "postgres", "--exit-on-error", "--no-owner", "--no-acl", "--role", database + "_owner", "-d", database], stdin=data, capture_output=True, timeout=180)
                if found.returncode:
                    raise RuntimeError("Restore failed; retained the incomplete environment for diagnosis")
        self.provision(name)
        if self.contents(name) != manifest["contents"]:
            raise ValueError("Restored contents differ; baseline was not promoted")
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home() / ".local/share/edgartools/local-tests")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("up", "stop", "status", "backup", "copy"):
        part = sub.add_parser(command)
        part.add_argument("name")
        if command == "copy":
            part.add_argument("--snapshot", type=Path, help="Omit to copy the latest verified baseline")
        if command == "backup":
            part.add_argument("--baseline", action="store_true", help="Check a restore, then use this baseline for future copies")
    args = parser.parse_args()
    stores = LocalStores(args.root, Path.cwd())
    try:
        with stores.locked(args.name):
            if args.command == "up":
                stores.start(args.name)
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
            print(json.dumps({"name": args.name, "state": found["State"]["Status"] if found else "missing", "stores": len(STORES), "env_file": str(stores.folder(args.name) / "connection.env")}))
    except Exception as exc:
        # Driver/subprocess exception messages may hold source data or credentials.
        message = str(exc) if type(exc) in (ValueError, RuntimeError) else type(exc).__name__
        parser.exit(1, message + "\n")


if __name__ == "__main__":
    main()
