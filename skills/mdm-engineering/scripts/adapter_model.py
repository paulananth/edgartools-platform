"""Logical storage model for prepared effects; no policy interpretation."""

from __future__ import annotations

import re

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    JSON,
    MetaData,
    String,
    Table,
    Uuid,
    UniqueConstraint,
)
from sqlalchemy.dialects.mssql import VARBINARY
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.dialects.postgresql import JSONB


def native_registry_model(dialect: str) -> tuple[MetaData, dict[str, Table]]:
    """The native MDM registry's existing tables, compiled for its connection.

    Governance owns these writes. This model neither creates tables on import
    nor grants a mastering worker permission to register configuration.
    """
    if dialect not in {"postgresql", "mysql", "mssql"}:
        raise ValueError("Unsupported registry database engine")
    metadata = MetaData(schema=None if dialect == "mysql" else "mdm")
    body = JSON().with_variant(JSONB(), "postgresql")
    tables = {
        "policy": Table(
            "policy", metadata,
            Column("digest", String(64), primary_key=True),
            Column("body", body, nullable=False),
        ),
        "dataset": Table(
            "dataset", metadata,
            Column("source_code", String(255), primary_key=True),
            Column("registry_version", Uuid(as_uuid=False), nullable=False),
            Column("body", body, nullable=False),
        ),
        "dataset_mapping": Table(
            "dataset_mapping", metadata,
            Column("source_code", String(255), primary_key=True),
            Column("mapping_version", BigInteger, primary_key=True, autoincrement=False),
            Column("body", body, nullable=False),
            Column("registry_version", Uuid(as_uuid=False), nullable=False),
        ),
    }
    return metadata, tables


def model(prefix: str, schema: str | None = None) -> tuple[MetaData, dict[str, Table]]:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", prefix):
        raise ValueError(
            "Storage prefix must be a lower-case SQL identifier of at most 31 characters"
        )
    metadata = MetaData(schema=schema)
    binary = (
        LargeBinary()
        .with_variant(LONGBLOB(), "mysql")
        .with_variant(VARBINARY(None), "mssql")
    )
    key = String(64)
    tables = {}

    def table(name, *columns, **kwargs):
        found = Table(
            f"{prefix}_{name}",
            metadata,
            *columns,
            mysql_engine="InnoDB",
            mysql_charset="ascii",
            mysql_collate="ascii_bin",
            **kwargs,
        )
        tables[name] = found
        return found

    table(
        "migration",
        Column("version", Integer, primary_key=True, autoincrement=False),
        Column("checksum", key, nullable=False),
        Column("complete", Integer, nullable=False),
    )
    table(
        "gate",
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("generation", BigInteger, nullable=False),
        CheckConstraint("id = 1"),
        CheckConstraint("generation >= 0"),
    )
    table(
        "lease",
        Column("scope_key", key, primary_key=True),
        Column("scope_bytes", binary, nullable=False),
        Column("owner_key", key, nullable=False),
        Column("fence", BigInteger, nullable=False),
        Column("expires", BigInteger, nullable=False),
        CheckConstraint("fence > 0"),
    )
    table(
        "run",
        Column("run_key", key, primary_key=True),
        Column("run_bytes", binary, nullable=False),
        Column("pins", binary, nullable=False),
    )
    table(
        "checkpoint",
        Column("scope_key", key, primary_key=True),
        Column("position", BigInteger, nullable=False),
        CheckConstraint("position >= 0"),
    )
    table(
        "batch",
        Column("batch_key", key, primary_key=True),
        Column("batch_bytes", binary, nullable=False),
        Column("request_hash", key, nullable=False),
        Column("run_key", key, nullable=False),
        Column("scope_key", key, nullable=False),
        Column("lease_owner", key, nullable=False),
        Column("lease_fence", BigInteger, nullable=False),
        Column("generation", BigInteger, nullable=False),
        Column("position", BigInteger, nullable=False),
        Column("intent", binary, nullable=False),
        Column("assessment", binary, nullable=False),
        Column("changed", Integer, nullable=False),
        UniqueConstraint("generation", name=f"{prefix}_generation_unique"),
        ForeignKeyConstraint(
            ["run_key"], [f"{schema + '.' if schema else ''}{prefix}_run.run_key"]
        ),
        CheckConstraint("generation > 0"),
        CheckConstraint("position > 0"),
    )
    for name in ("current", "history", "evidence"):
        cols = [
            Column("type_key", key, primary_key=True),
            Column("id_key", key, primary_key=True),
        ]
        if name == "history":
            cols.append(Column("generation", BigInteger, primary_key=True))
        cols.extend(
            [
                Column("type_bytes", binary, nullable=False),
                Column("id_bytes", binary, nullable=False),
                Column("body", binary, nullable=False),
                Column("body_hash", key, nullable=False),
                Column("batch_key", key, nullable=False),
            ]
        )
        if name in {"current", "history"}:
            cols.append(Column("version", BigInteger, nullable=False))
            if name == "current":
                cols.append(Column("generation", BigInteger, nullable=False))
        cols.append(
            ForeignKeyConstraint(
                ["batch_key"],
                [f"{schema + '.' if schema else ''}{prefix}_batch.batch_key"],
            )
        )
        table(name, *cols)
    table(
        "outbox",
        Column("batch_key", key, primary_key=True),
        Column("consumer_key", key, primary_key=True),
        Column("consumer_bytes", binary, nullable=False),
        Column("payload", binary, nullable=False),
        Column("payload_hash", key, nullable=False),
        Column("fence", BigInteger, nullable=False),
        Column("owner_key", key),
        Column("expires", BigInteger),
        Column("verified", Integer, nullable=False),
        ForeignKeyConstraint(
            ["batch_key"], [f"{schema + '.' if schema else ''}{prefix}_batch.batch_key"]
        ),
        CheckConstraint("fence >= 0"),
        CheckConstraint("verified IN (0, 1)"),
    )
    Index(
        f"{prefix}_outbox_status",
        tables["outbox"].c.consumer_key,
        tables["outbox"].c.verified,
        tables["outbox"].c.batch_key,
    )
    Index(
        f"{prefix}_history_generation",
        tables["history"].c.generation,
        tables["history"].c.type_key,
        tables["history"].c.id_key,
    )
    return metadata, tables
