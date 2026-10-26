"""Logical storage model for prepared effects; no policy interpretation."""

from __future__ import annotations

import re
import json

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
    UnicodeText,
    Uuid,
    UniqueConstraint,
)
from sqlalchemy.dialects.mssql import NVARCHAR, VARBINARY
from sqlalchemy.dialects.mysql import LONGBLOB, LONGTEXT
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator


class ExactJSON(TypeDecorator):
    """Configuration JSON whose numbers retain their original Python values."""
    impl = UnicodeText
    cache_ok = True

    @property
    def python_type(self):
        return dict

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(LONGTEXT(charset="utf8mb4", collation="utf8mb4_0900_bin")
                                       if dialect.name == "mysql" else JSONB()
                                       if dialect.name == "postgresql" else JSON())

    def process_bind_param(self, value, dialect):
        if dialect.name == "mysql":
            return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        return value

    def process_result_value(self, value, dialect):
        return json.loads(value) if dialect.name == "mysql" and value is not None else value


def native_registry_model(dialect: str) -> tuple[MetaData, dict[str, Table]]:
    """The native MDM registry's existing tables, compiled for its connection.

    Governance owns these writes. This model neither creates tables on import
    nor grants a mastering worker permission to register configuration.
    """
    if dialect not in {"postgresql", "mysql", "mssql"}:
        raise ValueError("Unsupported registry database engine")
    metadata = MetaData(schema=None if dialect == "mysql" else "mdm")
    body = ExactJSON()
    source = UnicodeText().with_variant(LONGTEXT(charset="utf8mb4",collation="utf8mb4_0900_bin"), "mysql").with_variant(NVARCHAR(None), "mssql")

    def source_columns():
        columns = [Column("source_code", source, primary_key=dialect == "postgresql", nullable=False)]
        if dialect != "postgresql":
            # Retain unbounded Unicode verbatim; hash its UTF-8 bytes for an
            # exact, source-leading key independent of database collation.
            columns.append(Column("source_key", String(64), primary_key=True, nullable=False))
        return columns

    tables = {
        "policy": Table(
            "policy", metadata,
            Column("digest", String(64), primary_key=True),
            Column("body", body, nullable=False),
        ),
        "dataset": Table(
            "dataset", metadata,
            *source_columns(),
            Column("registry_version", Uuid(as_uuid=False), nullable=False),
            Column("body", body, nullable=False),
        ),
        "dataset_mapping": Table(
            "dataset_mapping", metadata,
            *source_columns(),
            Column("mapping_version", BigInteger, primary_key=True, autoincrement=False),
            Column("body", body, nullable=False),
            Column("registry_version", Uuid(as_uuid=False), nullable=False),
        ),
    }
    return metadata, tables


def model(prefix: str, schema: str | None = None, *, protocol=1) -> tuple[MetaData, dict[str, Table]]:
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
    if protocol >= 3:
        # Rebuildable indexed pointers are not business versions or publication.
        table(
            "lookup",
            Column("type_key", key, primary_key=True),
            Column("id_key", key, primary_key=True),
            Column("type_bytes", binary, nullable=False),
            Column("id_bytes", binary, nullable=False),
            Column("body", binary, nullable=False),
            Column("body_hash", key, nullable=False),
            Column("batch_key", key, nullable=False),
            Column("version", BigInteger, nullable=False),
            Column("generation", BigInteger, nullable=False),
            ForeignKeyConstraint(
                ["batch_key"], [f"{schema + '.' if schema else ''}{prefix}_batch.batch_key"]
            ),
            CheckConstraint("version > 0"),
            CheckConstraint("generation > 0"),
        )
    if protocol >= 4:
        table(
            "authority",
            Column("resource_key", key, primary_key=True),
            Column("resource_bytes", binary, nullable=False),
            Column("token", BigInteger, nullable=False),
            Column("run_bytes", binary, nullable=False),
            Column("attempt_bytes", binary, nullable=False),
            Column("expires", BigInteger, nullable=False),
            CheckConstraint("token > 0"),
            CheckConstraint("expires > 0"),
        )
    if protocol >= 5:
        # Owner-approved opaque references, not copied policy/configuration.
        table(
            "pin",
            Column("name_key", key, primary_key=True),
            Column("value_key", key, primary_key=True),
            Column("name_bytes", binary, nullable=False),
            Column("value_bytes", binary, nullable=False),
            Column("active", Integer, nullable=False),
            CheckConstraint("active IN (0, 1)"),
        )
        # Prepared commands have a destination-owned lifecycle. Bodies and
        # intents are opaque; the store verifies bytes, state and freshness.
        table(
            "proposal",
            Column("proposal_key", key, primary_key=True),
            Column("batch_key", key, nullable=False),
            Column("body", binary, nullable=False),
            Column("intent", binary),
            Column("intent_hash", key),
            Column("observed_generation", BigInteger, nullable=False),
            Column("outcome", String(12), nullable=False),
            Column("state", String(12), nullable=False),
            CheckConstraint("outcome IN ('ready', 'rejected')"),
            CheckConstraint("state IN ('ready', 'rejected', 'applied', 'superseded')"),
            CheckConstraint("observed_generation >= 0"),
        )
        Index(f"{prefix}_proposal_batch", tables["proposal"].c.batch_key,
              tables["proposal"].c.state, tables["proposal"].c.proposal_key)
        table(
            "proposal_event",
            Column("proposal_key", key, primary_key=True),
            Column("observer_key", key, primary_key=True),
            Column("event", String(12), primary_key=True),
            Column("observer_bytes", binary, nullable=False),
            Column("batch_key", key),
            Column("occurred", BigInteger, nullable=False),
            ForeignKeyConstraint(["proposal_key"], [f"{schema + '.' if schema else ''}{prefix}_proposal.proposal_key"]),
            ForeignKeyConstraint(["batch_key"], [f"{schema + '.' if schema else ''}{prefix}_batch.batch_key"]),
            CheckConstraint("event IN ('ready', 'rejected', 'observed', 'applied', 'superseded', 'duplicate')"),
        )
    if protocol >= 6:
        # Opaque execution metadata has its own versions, not business generations.
        table(
            "metadata",
            Column("type_key", key, primary_key=True),
            Column("id_key", key, primary_key=True),
            Column("type_bytes", binary, nullable=False),
            Column("id_bytes", binary, nullable=False),
            Column("body", binary, nullable=False),
            Column("body_hash", key, nullable=False),
            Column("version", BigInteger, nullable=False),
            Column("recorded_at", BigInteger, nullable=False),
            Column("immutable", Integer, nullable=False),
            CheckConstraint("version > 0"),
            CheckConstraint("immutable IN (0, 1)"),
        )
        table(
            "outbox_context",
            Column("batch_key", key, primary_key=True),
            Column("consumer_key", key, primary_key=True),
            Column("body", binary, nullable=False),
            Column("body_hash", key, nullable=False),
            ForeignKeyConstraint(
                ["batch_key", "consumer_key"],
                [f"{schema + '.' if schema else ''}{prefix}_outbox.batch_key",
                 f"{schema + '.' if schema else ''}{prefix}_outbox.consumer_key"],
            ),
        )
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
    if protocol >= 6:
        Index(f"{prefix}_proposal_observer", tables["proposal_event"].c.observer_key,
              tables["proposal_event"].c.batch_key, tables["proposal_event"].c.event)
    return metadata, tables
