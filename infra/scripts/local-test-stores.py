#!/usr/bin/env python3
"""Persistent shared PostgreSQL 16, with optional silver for isolated tests.

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
import time
from uuid import uuid4

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL


STORES = {
    "mdm": ("MDM_DATABASE_URL", "mdm"),
    "rdm": ("RDM_DATABASE_URL", "rdm"),
    "rules": ("RULES_DATABASE_URL", "rules"),
    "bookkeeping_clean": ("BOOKKEEPING_CLEAN_DATABASE_URL", "bookkeeping"),
    "change_journal": ("CHANGE_JOURNAL_DATABASE_URL", "journal"),
}
ALL_STORES = {**STORES, "silver": ("SILVER_DATABASE_URL", "silver")}


def physical_database(store: str) -> str:
    return "bookkeeping" if store == "bookkeeping_clean" else store


def runtime_login(store: str) -> str:
    return "bookkeeping_runtime" if store == "bookkeeping_clean" else store + "_runtime"
EXTRA_LOGINS = ("bookkeeping_verifier", "mdm_verifier", "mdm_governance", "rules_governance")
IMAGE = "postgres:16-alpine"
LABEL = "org.edgartools.local-tests.owner"


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
            if value["owner"] != self.owner:
                raise ValueError("Environment belongs to another worktree; use your own name")
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
        return {database: ALL_STORES[database] for database in selected}

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
        database = physical_database(database)
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
        self.recover_backup(name)
        self.provision(name, migrate=not empty, include_silver=include_silver)
        self.connections(name, include_silver=include_silver)

    def connections(self, name: str, *, include_silver=False):
        selected = ALL_STORES if include_silver else STORES
        common = {variable: self.url(name, database, database + "_runtime").render_as_string(hide_password=False)
                  for database, (variable, _) in selected.items()}
        common.update(MDM_APPLICATION_ROLE="mdm_runtime",
                      BOOKKEEPING_MANIFEST_ROOT=(self.folder(name) / "manifests").as_uri())
        migration = {variable.replace("_DATABASE_URL", "_MIGRATION_DATABASE_URL"):
                     self.url(name, database).render_as_string(hide_password=False)
                     for database, (variable, _) in selected.items()}
        verifier = {"BOOKKEEPING_CLEAN_DATABASE_URL": self.url(name, "bookkeeping_clean", "bookkeeping_verifier").render_as_string(hide_password=False),
                    "MDM_DATABASE_URL": self.url(name, "mdm", "mdm_verifier").render_as_string(hide_password=False)}
        governance = {"RULES_DATABASE_URL": self.url(name, "rules", "rules_governance").render_as_string(hide_password=False),
                      "RULES_MDM_ACTIVATION_DATABASE_URL": self.url(name, "mdm", "mdm_governance").render_as_string(hide_password=False)}
        for filename, extra in (("connection.env", migration), ("worker.env", {}),
                                ("verifier.env", verifier), ("governance.env", governance)):
            # Clear a previous shell's owner/silver settings before choosing a duty.
            unset = [*migration, "RULES_MDM_ACTIVATION_DATABASE_URL", "DESTINATION_MIGRATION_DATABASE_URL"]
            if not include_silver:
                unset += ["SILVER_DATABASE_URL", "SILVER_MIGRATION_DATABASE_URL"]
            lines = ["unset " + " ".join(unset)]
            lines += [f"export {key}={shlex.quote(value)}" for key, value in {**common, **extra}.items()]
            private_write(self.folder(name) / filename, "\n".join(lines) + "\n")

    def provision(self, name: str, *, migrate=True, include_silver=False):
        from edgar_warehouse.mdm.clean.store import migrate as mdm
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
                roles = {store + "_owner": False for store in selected}
                roles.update({runtime_login(store): True for store in selected})
                roles.update({role: True for role in EXTRA_LOGINS})
                roles.update(bookkeeping_clean_control=False, rules_approver=False)
                for role, login in roles.items():
                    held = conn.execute(text("SELECT rolsuper,rolcreatedb,rolcreaterole,rolcanlogin,rolbypassrls FROM pg_roles WHERE rolname=:r"), {"r": role}).first()
                    if held:
                        if any((held[0], held[1], held[2], held[4])) or held[3] != login:
                            raise ValueError("Existing role has incompatible privileges")
                    else:
                        suffix = "LOGIN PASSWORD :password" if login else "NOLOGIN"
                        conn.execute(text(f"CREATE ROLE {quote(role)} NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS {suffix}"), {"password": self.identity(name)["password"]})
                for store in selected:
                    database = physical_database(store)
                    owner = conn.scalar(text("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=:d"), {"d": database})
                    if owner and owner != store + "_owner":
                        raise ValueError("Database has a different owner; refusing adoption")
                    if not owner:
                        conn.exec_driver_sql(f"CREATE DATABASE {quote(database)} OWNER {quote(store + '_owner')}")
                    conn.exec_driver_sql(f"REVOKE CONNECT ON DATABASE {quote(database)} FROM PUBLIC")
                    conn.exec_driver_sql(f"GRANT CONNECT ON DATABASE {quote(database)} TO {quote(runtime_login(store))}")
                for database, login in (("bookkeeping", "bookkeeping_verifier"), ("mdm", "mdm_verifier"),
                                        ("mdm", "mdm_governance"), ("rules", "rules_governance")):
                    conn.exec_driver_sql(f"GRANT CONNECT ON DATABASE {quote(database)} TO {quote(login)}")
                for parent, member in (("bookkeeping_clean_control", "bookkeeping_runtime"),
                                       ("bookkeeping_clean_control", "bookkeeping_verifier"),
                                       ("rules_runtime", "rules_governance"), ("rules_approver", "rules_governance")):
                    if not conn.scalar(text("SELECT pg_has_role(:m,:p,'MEMBER')"), {"m": member, "p": parent}):
                        conn.exec_driver_sql(f"GRANT {quote(parent)} TO {quote(member)}")
            if migrate:
                migrations = {"mdm": mdm, "rdm": rdm, "silver": silver, "rules": rules,
                              "bookkeeping_clean": bookkeeping, "change_journal": journal}
                for database in selected:
                    engine = self.engine(name, database)
                    @event.listens_for(engine, "connect")
                    def owner_role(connection, _, selected=database + "_owner"):
                        with connection.cursor() as cursor:
                            cursor.execute(f"SET ROLE {quote(selected)}")
                        connection.commit()
                    try:
                        key = "application_role" if database == "mdm" else "agent_role" if database == "rules" else "runtime_role"
                        role = "bookkeeping_clean_control" if database == "bookkeeping_clean" else database + "_runtime"
                        migrations[database](engine, **{key: role})
                        if database == "mdm":
                            from edgar_warehouse.bookkeeping.clean.destinations import migrate_guard
                            migrate_guard(engine, runtime_role="mdm_runtime")
                    finally:
                        engine.dispose()
                self.execution_access(name)
        finally:
            admin.dispose()

    def execution_access(self, name: str):
        from edgar_warehouse.bookkeeping.clean.database import grant_profile
        from edgar_warehouse.workers import PROFILES

        book = self.engine(name, "bookkeeping_clean")
        try:
            for profile in PROFILES:
                grant_profile(book, profile=profile, worker="bookkeeping_runtime", verifier="bookkeeping_verifier")
            with book.connect() as conn:
                for profile in PROFILES:
                    for login, duty in (("bookkeeping_runtime", "verifier"), ("bookkeeping_verifier", "worker")):
                        if conn.scalar(text("SELECT pg_has_role(:l,bookkeeping.profile_role(:p,:d),'MEMBER')"),
                                       {"l": login, "p": profile, "d": duty}):
                            raise ValueError("Worker and verifier duties overlap; refusing initialization")
        finally:
            book.dispose()
        mdm = self.engine(name, "mdm")
        try:
            with mdm.begin() as conn:
                conn.exec_driver_sql("GRANT USAGE ON SCHEMA mdm TO mdm_verifier,mdm_governance")
                conn.exec_driver_sql("GRANT SELECT ON ALL TABLES IN SCHEMA mdm TO mdm_verifier,mdm_governance")
                conn.exec_driver_sql("GRANT INSERT ON mdm.policy,mdm.dataset,mdm.dataset_mapping TO mdm_governance")
        finally:
            mdm.dispose()

    def contents(self, name: str):
        """Private checksums, never row values, prove what a restored copy holds."""
        result = {}
        for database in self.stores(name):
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
            for database in self.stores(name):
                path = target / (database + ".dump")
                with open(path, "wb", opener=lambda p, flags: os.open(p, flags, 0o600)) as out:
                    self.docker("exec", container, "pg_dump", "-U", "postgres", "-Fc", "--no-owner", "-d", database, stdout=out)
                files[path.name] = file_hash(path)
            private_write(target / "manifest.json", json.dumps({"files": files, "contents": contents}, sort_keys=True))
            return target
        finally:
            admin.dispose()
            self.recover_backup(name)

    def restore(self, name: str, snapshot: Path):
        manifest = json.loads((snapshot / "manifest.json").read_text())
        selected = {database for database in ALL_STORES if database + ".dump" in manifest["files"]}
        if not set(STORES) <= selected or set(manifest["files"]) != {d + ".dump" for d in selected}:
            raise ValueError("Backup must contain the five core stores and optionally silver")
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
        for database in self.stores(name):
            with (snapshot / (database + ".dump")).open("rb") as data:
                found = subprocess.run(["docker", "exec", "-i", container, "pg_restore", "-U", "postgres", "--exit-on-error", "--no-owner", "--role", database + "_owner", "-d", database], stdin=data, capture_output=True, timeout=180)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home() / ".local/share/edgartools/local-tests")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("up", "stop", "status", "backup", "copy"):
        part = sub.add_parser(command)
        part.add_argument("name")
        if command == "up":
            part.add_argument("--include-silver", action="store_true", help="Also initialize silver (isolated tests only)")
        if command == "copy":
            part.add_argument("--snapshot", type=Path, help="Omit to copy the latest verified baseline")
        if command == "backup":
            part.add_argument("--baseline", action="store_true", help="Check a restore, then use this baseline for future copies")
    args = parser.parse_args()
    stores = LocalStores(args.root, Path.cwd())
    try:
        with stores.locked(args.name):
            if args.command == "up":
                stores.start(args.name, include_silver=args.include_silver)
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
        message = str(exc) if type(exc) in (ValueError, RuntimeError) else type(exc).__name__
        parser.exit(1, message + "\n")


if __name__ == "__main__":
    main()
