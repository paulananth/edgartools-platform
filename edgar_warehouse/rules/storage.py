"""Typed Rules persistence; approval decisions stay in the normal Rules facade."""
from contextlib import contextmanager
import hashlib

from sqlalchemy import (Column, LargeBinary, MetaData, String, Table,
                        Text, and_, cast, func, literal, literal_column, select, text)
from sqlalchemy.dialects.mysql import LONGTEXT

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.database_types import ExactJSON, UTCDateTime

APPROVAL = ("approved_by", "approved_at", "approved_words", "approval_overrule",
            "approval_evidence", "approval_recorded_by")
PROOF = ("status", "proof", "batch_hash", "clean_mdm")
IDENTITY = ("kind", "name", "version", "body", "digest")


def versions(dialect):
    if dialect not in {"postgresql", "mysql"}:
        raise Blocked("Rules currently supports PostgreSQL and MySQL; SQL Server follows last")
    words = Text().with_variant(LONGTEXT(charset="utf8mb4", collation="utf8mb4_0900_bin"), "mysql")
    columns = [Column(name, words) for name in ("kind", "name", "version", "body", "digest", "status",
        "created_by", "batch_hash", "approved_by", "approved_words", "approval_overrule",
        "approval_evidence", "approval_recorded_by")]
    columns += [Column(name, UTCDateTime()) for name in ("created_at", "proved_at", "approved_at", "activated_at", "retired_at")]
    columns += [Column(name, ExactJSON(none_as_null=True)) for name in ("proof", "clean_mdm")]
    table = Table("rule_version", MetaData(schema="rules" if dialect == "postgresql" else None), *columns)
    if dialect == "mysql":
        for name in ("_version_key", "_document_key", "_active_key"):
            table.append_column(Column(name, String(64)))
    return table


def identity(table, dialect, kind, name, version=None, *, active=False):
    conditions = [table.c.kind == kind, table.c.name == name]
    if version is not None:
        conditions.append(table.c.version == version)
    if active:
        conditions.append(table.c.status == "active")
    if dialect == "mysql":
        values = [literal(kind), literal(name)] + ([literal(version)] if version is not None else [])
        column = table.c._version_key if version is not None else table.c._active_key if active else table.c._document_key
        conditions.append(column == func.sha2(cast(func.json_array(*values), LargeBinary), 256))
    return and_(*conditions)


def evidence(table, dialect):
    if dialect == "postgresql":
        return func.encode(func.sha256(func.convert_to(cast(table.c.proof, Text), "UTF8")), "hex")
    return func.sha2(table.c.proof, 256)


def rows(conn, statement):
    # Internal lookup columns are storage details, never Rules content.
    return [{key: value for key, value in row.items() if not key.startswith("_")}
            for row in conn.execute(statement).mappings()]


def version(conn, kind, name, label):
    table = versions(conn.dialect.name)
    # Upgrade fixtures and retained pre-approval history have fewer metadata
    # columns. PostgreSQL's native values retain their existing wire types.
    query = select(literal_column("*")).select_from(table) if conn.dialect.name == "postgresql" else select(table)
    found = rows(conn, query.where(identity(table, conn.dialect.name, kind, name, label)))
    return found[0] if found else None


@contextmanager
def transaction(engine, kind, name):
    """Hold the document lock through commit, including an activation handoff."""
    with engine.connect() as conn:
        if conn.dialect.name == "postgresql":
            with conn.begin():
                conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k,0))"), {"k": f"{kind}:{name}"})
                yield conn
        elif conn.dialect.name == "mysql":
            key = "rules:" + hashlib.sha256((str(engine.url.database) + "\0" + kind + "\0" + name).encode()).hexdigest()[:56]
            locked = conn.scalar(text("SELECT GET_LOCK(:k,30)"), {"k": key}) == 1
            conn.commit()  # GET_LOCK is connection-owned, not transaction-owned.
            if not locked:
                raise Blocked("Rules document lock unavailable")
            try:
                with conn.begin():
                    yield conn
            finally:
                conn.execute(text("SELECT RELEASE_LOCK(:k)"), {"k": key})
                conn.commit()
        else:
            raise Blocked("Rules currently supports PostgreSQL and MySQL")


def save(conn, table, values):
    if conn.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
        statement = insert(table).values(**values).on_conflict_do_nothing()
    else:
        from sqlalchemy.dialects.mysql import insert
        statement = insert(table).values(**values).on_duplicate_key_update(status=table.c.status)
    conn.execute(statement)
