"""The Rules Database: which rules each run used, and the rules MDM registered.

The rules themselves are the files under `rules/`. When a run is submitted, the document it froze is
recorded here once, under its digest, so the rules a past run used can be read after the files change.
The registry (`registry.py`) keeps each Mastering Policy under its digest and each reading of a Dataset
Contract under its version, as the merge reads them. Tables made by SQLAlchemy, the same on every database;
rows are only added, never changed (the logins hold SELECT and INSERT only).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import BigInteger, Column, MetaData, String, Table, Text, select
from sqlalchemy.dialects.mysql import LONGTEXT, VARCHAR
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from edgar_warehouse.bookkeeping.clean.config import Blocked, canonical, digest
from edgar_warehouse.database_types import UTCDateTime

TABLE = "rules_used"
DRAFT = "draft"


def get_engine(url=None):
    """The Rules Database, from the sourced duty file unless a URL is given."""
    from edgar_warehouse.database_connections import connect, owner_url

    url = url or owner_url("rules")
    return connect(url, make_url(url).get_backend_name())


def tables(dialect: str) -> dict[str, Table]:
    """`rules_used`: a document's kind, name and digest, its body, and when a run first used it. `policy`: each
    registered Mastering Policy under its digest. `dataset_reading`: each reading of a Dataset Contract, numbered
    from 1 per source code, with the frozen rules version it was registered from. `draft`: one immutable draft
    under the version label the person typed, with the case kept beside it. A draft is not switched on."""
    body = Text().with_variant(LONGTEXT(charset="utf8mb4", collation="utf8mb4_0900_bin"), "mysql")
    metadata = MetaData(schema="rules" if dialect == "postgresql" else None)
    return {
        TABLE: Table(TABLE, metadata,
                     Column("kind", String(16), primary_key=True), Column("name", String(128), primary_key=True),
                     Column("digest", String(64), primary_key=True), Column("body", body, nullable=False),
                     Column("recorded_at", UTCDateTime(), nullable=False)),
        "policy": Table("policy", metadata, Column("digest", String(64), primary_key=True),
                        Column("body", body, nullable=False), Column("registered_at", UTCDateTime(), nullable=False)),
        "dataset_reading": Table("dataset_reading", metadata, Column("source_code", String(128), primary_key=True),
                                 Column("mapping_version", BigInteger(), primary_key=True, autoincrement=False),
                                 Column("registry_version", String(36), nullable=False),
                                 Column("body", body, nullable=False),
                                 Column("registered_at", UTCDateTime(), nullable=False)),
        DRAFT: Table(DRAFT, metadata,
                     Column("kind", _exact(16), primary_key=True),
                     Column("name", _exact(128), primary_key=True),
                     Column("version", _exact(128), primary_key=True),
                     Column("digest", String(64), nullable=False),
                     Column("body", body, nullable=False),
                     Column("case_body", body, nullable=False),
                     Column("status", String(16), nullable=False),
                     Column("saved_at", UTCDateTime(), nullable=False)),
    }


def table(dialect: str) -> Table:
    return tables(dialect)[TABLE]


def _exact(size: int):
    """A label is compared exactly. MySQL's default collation folds case and accents."""
    return String(size).with_variant(VARCHAR(size, charset="utf8mb4", collation="utf8mb4_0900_bin"), "mysql")


def migrate(engine, *, agent_role: str | None = None, registrar_role: str | None = None) -> dict:
    """Create the tables (rerunning changes nothing). On PostgreSQL they sit in the `rules` schema. The agent
    role, when named, may add to `rules_used` and to a draft, and read the registry, which the workers read; the
    registrar role, when named, may add to the registry. Nothing may change or delete a row."""
    made = tables(engine.dialect.name)
    roles = [role for role in (agent_role, registrar_role) if role]
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", role) for role in roles):
        raise Blocked("A role is a plain role name")
    postgres = engine.dialect.name == "postgresql"
    with engine.begin() as conn:
        if postgres:
            conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS rules")
        for target in made.values():
            target.create(conn, checkfirst=True)
        grants = [(agent_role, "SELECT, INSERT", [TABLE, DRAFT]),
                  (agent_role, "SELECT", ["policy", "dataset_reading"]),
                  (registrar_role, "SELECT, INSERT", ["policy", "dataset_reading"])]
        for role, privileges, names in grants:
            if not role:
                continue
            for name in names:
                if postgres:
                    conn.exec_driver_sql(f'GRANT USAGE ON SCHEMA rules TO "{role}"')
                    conn.exec_driver_sql(f'GRANT {privileges} ON rules.{name} TO "{role}"')
                elif engine.dialect.name == "mysql":
                    conn.exec_driver_sql(f"GRANT {privileges} ON {name} TO '{role}'@'%%'")
    return {"tables": sorted(made)}


class Rules:
    def __init__(self, engine):
        self.engine = engine

    def record(self, export: dict) -> dict:
        """Record the frozen rules a run is submitted with. A digest already recorded is left as it is."""
        if digest(export["body"]) != export["digest"]:
            raise Blocked("The frozen rules' digest is not their body's")
        target = table(self.engine.dialect.name)
        key = {name: export[name] for name in ("kind", "name", "digest")}
        try:
            with self.engine.begin() as conn:
                if conn.execute(select(target.c.digest).where(*(target.c[k] == v for k, v in key.items()))).first() is None:
                    conn.execute(target.insert().values(**key, body=canonical(export["body"]),
                                                        recorded_at=datetime.now(UTC)))
        except IntegrityError:  # another submission recorded the same digest first
            pass
        return key

    def history(self, kind: str, name: str) -> list[dict]:
        """The digests runs of this document used, oldest first."""
        target = table(self.engine.dialect.name)
        with self.engine.connect() as conn:
            found = conn.execute(select(target.c.kind, target.c.name, target.c.digest, target.c.recorded_at).where(
                target.c.kind == kind, target.c.name == name).order_by(target.c.recorded_at)).mappings()
            return [dict(row) for row in found]

    def body(self, kind: str, name: str, content: str) -> dict:
        """The document a run used, by its digest."""
        import json

        target = table(self.engine.dialect.name)
        with self.engine.connect() as conn:
            row = conn.execute(select(target.c.body).where(
                target.c.kind == kind, target.c.name == name, target.c.digest == content)).first()
        if row is None:
            raise Blocked("No run recorded these rules")
        return json.loads(row[0])

    def save(self, *, kind: str, name: str, version: str, body: dict, case: dict) -> dict:
        """Store canonical JSON and its SHA-256 as an immutable draft. The case sits beside that draft.
        The same body under the same version is left as it is. A different body is refused. Nothing is
        approved or switched on."""
        if (not isinstance(kind, str) or not kind or len(kind) > 16
                or not isinstance(name, str) or not name or len(name) > 128
                or not isinstance(version, str) or not version.strip() or len(version) > 128
                or not isinstance(body, dict) or not isinstance(case, dict)):
            raise Blocked("A draft names its kind, name and version")
        content = digest(body)
        target = tables(self.engine.dialect.name)[DRAFT]
        key = {"kind": kind, "name": name, "version": version}
        try:
            with self.engine.begin() as conn:
                row = _draft_row(conn, target, key)
                if row is not None:
                    if row.digest != content:
                        raise Blocked("This version is already stored")
                    return {**key, "digest": content, "status": row.status}
                conn.execute(target.insert().values(
                    **key, digest=content, body=canonical(body), case_body=canonical(case),
                    status="draft", saved_at=datetime.now(UTC)))
        except IntegrityError:
            with self.engine.connect() as conn:
                row = _draft_row(conn, target, key)
            if row is None or row.digest != content:
                raise Blocked("This version is already stored")
            return {**key, "digest": content, "status": row.status}
        return {**key, "digest": content, "status": "draft"}

    def draft(self, kind: str, name: str, version: str) -> dict:
        """The stored draft and the case beside it."""
        import json

        target = tables(self.engine.dialect.name)[DRAFT]
        with self.engine.connect() as conn:
            row = _draft_row(conn, target, {"kind": kind, "name": name, "version": version})
        if row is None:
            raise Blocked("No draft is stored under this version")
        return {"kind": kind, "name": name, "version": version, "digest": row.digest, "status": row.status,
                "body": json.loads(row.body), "case": json.loads(row.case_body)}


def _draft_row(conn, target, key: dict):
    return conn.execute(select(target.c.digest, target.c.status, target.c.body, target.c.case_body).where(
        *(target.c[column] == value for column, value in key.items()))).first()
