"""Typed Silver registry reads, independent of another store's catalog."""
from sqlalchemy import Column, MetaData, String, Table, Text, select

from edgar_warehouse.control_contract import Blocked, digest
from edgar_warehouse.database_types import ExactJSON, UTCDateTime

from . import spec as specs


def registry(dialect):
    if dialect not in {"postgresql", "mysql"}:
        raise Blocked("Silver registry currently supports PostgreSQL and MySQL")
    return Table("table_spec", MetaData(schema="silver" if dialect == "postgresql" else None),
                 Column("table_name", Text), Column("spec", ExactJSON()),
                 Column("sha256", String(64)), Column("registered_at", UTCDateTime()))


def registered(engine, name=None):
    """Read and verify immutable registration; registry size follows table count."""
    table = registry(engine.dialect.name)
    query = select(table)
    if name is not None:
        query = query.where(table.c.table_name == name)
    with engine.connect() as conn:
        rows = [dict(row) for row in conn.execute(query).mappings()]
    for row in rows:
        if digest(row["spec"]) != row["sha256"]:
            raise Blocked("Silver registered spec does not match its sha256")
        specs.check(row["spec"])
    return sorted(rows, key=lambda row: row["table_name"])


def registered_spec(engine, name):
    rows = registered(engine, name)
    if not rows:
        raise Blocked(f"silver.{name} is not registered: the schema owner registers its spec first")
    return rows[0]["spec"]
