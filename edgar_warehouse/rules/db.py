"""The Rules Database: which rules each run used.

The rules themselves are the files under `rules/`. When a run is submitted, the document it froze is
recorded here once, under its digest, so the rules a past run used can be read after the files change.
One table, made by SQLAlchemy, the same on every database.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime

from sqlalchemy import Column, MetaData, String, Table, Text, create_engine, select
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from edgar_warehouse.bookkeeping.clean.config import Blocked, canonical, digest
from edgar_warehouse.database_types import UTCDateTime

TABLE = "rules_used"


def get_engine(url=None):
    target = make_url(url or os.environ["RULES_DATABASE_URL"])
    drivers = {"postgresql": "postgresql+psycopg2", "mysql": "mysql+pymysql"}
    if target.drivername in drivers:
        target = target.set(drivername=drivers[target.drivername])
    return create_engine(target, pool_pre_ping=True, hide_parameters=True)


def table(dialect: str) -> Table:
    """The one table: a document's kind, name and digest, its body, and when a run first used it."""
    body = Text().with_variant(LONGTEXT(charset="utf8mb4", collation="utf8mb4_0900_bin"), "mysql")
    return Table(TABLE, MetaData(schema="rules" if dialect == "postgresql" else None),
                 Column("kind", String(16), primary_key=True), Column("name", String(128), primary_key=True),
                 Column("digest", String(64), primary_key=True), Column("body", body, nullable=False),
                 Column("recorded_at", UTCDateTime(), nullable=False))


def migrate(engine, *, agent_role: str | None = None) -> dict:
    """Create the table (rerunning changes nothing). On PostgreSQL it sits in the `rules` schema and the
    agent role, when named, may read the table and add to it, on PostgreSQL and MySQL."""
    target = table(engine.dialect.name)
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS rules")
        target.create(conn, checkfirst=True)
        if agent_role and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", agent_role):
            raise Blocked("The agent role is a plain role name")
        if engine.dialect.name == "postgresql" and agent_role:
            conn.exec_driver_sql(f'GRANT USAGE ON SCHEMA rules TO "{agent_role}"')
            conn.exec_driver_sql(f'GRANT SELECT, INSERT ON rules.{TABLE} TO "{agent_role}"')
        elif engine.dialect.name == "mysql" and agent_role:
            conn.exec_driver_sql(f"GRANT SELECT, INSERT ON {TABLE} TO '{agent_role}'@'%%'")
    return {"table": TABLE}


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
