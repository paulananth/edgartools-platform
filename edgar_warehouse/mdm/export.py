"""Incremental export from PostgreSQL -> Snowflake EDGARTOOLS_GOLD.

Reads unexported rows from mdm_change_log, materializes the current golden
record for each entity, upserts to the matching Snowflake MDM_* table, and
stamps exported_at = NOW(). No CDC or Kafka — just a drain table.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
import uuid
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from edgar_warehouse.mdm import database as db


DOMAIN_TO_TABLE = {
    "company": ("mdm_company", "MDM_COMPANY", db.MdmCompany),
    "adviser": ("mdm_adviser", "MDM_ADVISER", db.MdmAdviser),
    "person": ("mdm_person", "MDM_PERSON", db.MdmPerson),
    "security": ("mdm_security", "MDM_SECURITY", db.MdmSecurity),
    "fund": ("mdm_fund", "MDM_FUND", db.MdmFund),
}


class SnowflakeWriter:
    """Interface for write targets. Concrete impl uses snowflake-connector-python."""

    def upsert(self, table: str, rows: list[dict], key: str = "entity_id") -> int:
        raise NotImplementedError


@dataclass(frozen=True)
class SnowflakeConnectionSettings:
    """Reusable Snowflake connector settings for MDM export and graph sync."""

    account: str
    user: str
    password: str
    database: str
    schema: str
    warehouse: str
    role: str | None = None

    @classmethod
    def from_env(cls) -> "SnowflakeConnectionSettings":
        secret = _snowflake_secret_payload()
        account = _snowflake_setting(secret, "ACCOUNT")
        user = _snowflake_setting(secret, "USER")
        password = _snowflake_setting(secret, "PASSWORD")
        database = _snowflake_setting(secret, "DATABASE")
        schema = _snowflake_setting(secret, "SCHEMA") or "EDGARTOOLS_GOLD"
        warehouse = _snowflake_setting(secret, "WAREHOUSE")
        role = _snowflake_setting(secret, "ROLE")
        missing = [
            name
            for name, value in {
                "MDM_SNOWFLAKE_ACCOUNT or DBT_SNOWFLAKE_ACCOUNT": account,
                "MDM_SNOWFLAKE_USER or DBT_SNOWFLAKE_USER": user,
                "MDM_SNOWFLAKE_PASSWORD or DBT_SNOWFLAKE_PASSWORD": password,
                "MDM_SNOWFLAKE_DATABASE or DBT_SNOWFLAKE_DATABASE": database,
                "MDM_SNOWFLAKE_WAREHOUSE or DBT_SNOWFLAKE_WAREHOUSE": warehouse,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError("Missing Snowflake export setting(s): " + ", ".join(missing))

        return cls(
            account=str(account),
            user=str(user),
            password=str(password),
            database=str(database),
            schema=str(schema),
            warehouse=str(warehouse),
            role=str(role) if role else None,
        )

    def connection_kwargs(self) -> dict[str, str]:
        kwargs = {
            "account": self.account,
            "user": self.user,
            "password": self.password,
            "database": self.database,
            "schema": self.schema,
            "warehouse": self.warehouse,
        }
        if self.role:
            kwargs["role"] = self.role
        return kwargs

    def connect(self) -> Any:
        try:
            import snowflake.connector  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "snowflake-connector-python is not installed. Run with the snowflake extra, "
                "for example: uv run --extra snowflake edgar-warehouse mdm export ..."
            ) from exc

        return snowflake.connector.connect(**self.connection_kwargs())


def _snowflake_secret_payload() -> dict[str, Any]:
    source_name = "MDM_SNOWFLAKE_SECRET_JSON"
    raw = os.environ.get(source_name)
    if not raw:
        source_name = "DBT_SNOWFLAKE_SECRET_JSON"
        raw = os.environ.get(source_name)
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid Snowflake secret JSON in {source_name}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"Invalid Snowflake secret JSON in {source_name}")
        return payload

    return _snowflake_cli_config_payload()


def _snowflake_cli_config_payload() -> dict[str, Any]:
    """Read credentials from ~/.snowflake/connections.toml (Snowflake CLI config).

    The connection name is resolved in order:
      1. SNOWFLAKE_CONNECTION env var
      2. default_connection_name in ~/.snowflake/config.toml
      3. "snowconn"

    The returned dict uses lowercase keys (account, user, password, warehouse,
    role, database) which _snowflake_setting() already handles via secret.get(lower).
    Returns {} silently when the config file is absent.
    """
    import pathlib

    connections_path = pathlib.Path.home() / ".snowflake" / "connections.toml"
    if not connections_path.exists():
        return {}

    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return {}

    try:
        with connections_path.open("rb") as f:
            all_connections: dict[str, Any] = tomllib.load(f)
    except Exception:
        return {}

    # Resolve connection name
    connection_name = os.environ.get("SNOWFLAKE_CONNECTION", "")
    if not connection_name:
        config_path = pathlib.Path.home() / ".snowflake" / "config.toml"
        if config_path.exists():
            try:
                with config_path.open("rb") as f:
                    cfg = tomllib.load(f)
                connection_name = cfg.get("default_connection_name", "")
            except Exception:
                pass
    if not connection_name:
        connection_name = "snowconn"

    conn = all_connections.get(connection_name, {})
    if not conn:
        return {}

    # Normalise to lowercase keys so _snowflake_setting()'s secret.get(lower) picks them up
    return {k.lower(): v for k, v in conn.items()}


def _snowflake_setting(secret: dict[str, Any], key: str) -> Any:
    lower = key.lower()
    return (
        os.environ.get(f"MDM_SNOWFLAKE_{key}")
        or os.environ.get(f"DBT_SNOWFLAKE_{key}")
        or secret.get(f"MDM_SNOWFLAKE_{key}")
        or secret.get(f"DBT_SNOWFLAKE_{key}")
        or secret.get(f"snowflake_{lower}")
        or secret.get(lower)
    )


class SnowflakeConnectorWriter(SnowflakeWriter):
    """Snowflake upsert writer backed by snowflake-connector-python.

    Target MDM tables are expected to already exist. The writer creates a
    temporary table shaped from the current batch, inserts batch rows, then
    MERGEs by the configured key.
    """

    def __init__(self, connection: Any, *, database: str | None = None, schema: str | None = None) -> None:
        self.connection = connection
        self.database = database
        self.schema = schema

    @classmethod
    def from_env(cls) -> "SnowflakeConnectorWriter":
        settings = SnowflakeConnectionSettings.from_env()
        return cls(settings.connect(), database=settings.database, schema=settings.schema)

    def upsert(self, table: str, rows: list[dict], key: str = "entity_id") -> int:
        if not rows:
            return 0
        columns = sorted({str(column) for row in rows for column in row})
        if key not in columns:
            raise ValueError(f"Upsert key {key!r} is not present in rows for {table}")
        target = self._table_name(table)
        temp_table = f"TEMP_{_safe_identifier(table)}_{uuid.uuid4().hex[:12]}"
        column_defs = ", ".join(f"{_quote_identifier(column)} VARIANT" for column in columns)
        insert_columns = ", ".join(_quote_identifier(column) for column in columns)
        # Snowflake rejects non-constant expressions in a multi-row VALUES list
        # (002014: "Invalid expression [PARSE_JSON(...)] in VALUES clause"),
        # and executemany rewrites this INSERT into exactly that. Keep the
        # placeholders bare and apply PARSE_JSON in a SELECT over FROM VALUES.
        placeholders = ", ".join(["%s"] * len(columns))
        select_exprs = ", ".join(f"PARSE_JSON(column{i + 1})" for i in range(len(columns)))
        updates = ", ".join(
            f"target.{_quote_identifier(column)} = source.{_quote_identifier(column)}"
            for column in columns
            if column != key
        )
        values = [
            tuple(_json_text(row.get(column)) for column in columns)
            for row in rows
        ]
        cursor = self.connection.cursor()
        try:
            cursor.execute(f"CREATE TEMPORARY TABLE {_quote_identifier(temp_table)} ({column_defs})")
            cursor.executemany(
                f"INSERT INTO {_quote_identifier(temp_table)} ({insert_columns}) "
                f"SELECT {select_exprs} FROM VALUES ({placeholders})",
                values,
            )
            merge_sql = (
                f"MERGE INTO {target} AS target "
                f"USING {_quote_identifier(temp_table)} AS source "
                f"ON target.{_quote_identifier(key)} = source.{_quote_identifier(key)} "
                f"WHEN MATCHED THEN UPDATE SET {updates} "
                f"WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES "
                f"({', '.join(f'source.{_quote_identifier(column)}' for column in columns)})"
            )
            cursor.execute(merge_sql)
        finally:
            cursor.close()
        return len(rows)

    def _table_name(self, table: str) -> str:
        parts = [part for part in (self.database, self.schema, table) if part]
        return ".".join(_quote_identifier(part) for part in parts)


@dataclass
class MDMExporter:
    """Exports MDM domain golden records to EDGARTOOLS_GOLD, and (when
    ``mirror_writer`` is supplied) also keeps the EDGARTOOLS_*.MDM graph-source
    mirror fresh -- the tables sync-graph's render_graph_tables() actually
    reads (MDM_ENTITY, MDM_CHANGE_LOG, and the domain tables). Before this,
    nothing kept that mirror current after its one-time bootstrap load, so
    sync-graph silently read a frozen snapshot forever (see
    docs/prod-mdm-snowflake-graph-first-load.md and the mdm_relationship_type/
    mdm_entity_type_definition reference-table sync below).
    """

    session: Session
    writer: SnowflakeWriter
    mirror_writer: Optional[SnowflakeWriter] = None

    def export_pending(self, since: Optional[datetime] = None, entity_type: Optional[str] = None,
                       batch_size: int = 500) -> int:
        stmt = select(db.MdmChangeLog).where(db.MdmChangeLog.exported_at.is_(None))
        if since:
            stmt = stmt.where(db.MdmChangeLog.changed_at >= since)
        if entity_type:
            stmt = stmt.where(db.MdmChangeLog.entity_type == entity_type)
        stmt = stmt.limit(batch_size)

        pending = list(self.session.scalars(stmt))
        if not pending:
            return 0

        by_type: dict[str, list[str]] = {}
        for row in pending:
            by_type.setdefault(row.entity_type, []).append(row.entity_id)

        total = 0
        for et, entity_ids in by_type.items():
            target = DOMAIN_TO_TABLE.get(et)
            if target is None:
                continue
            _pg_table, sf_table, model = target
            domain_rows = list(
                self.session.scalars(select(model).where(model.entity_id.in_(entity_ids)))
            )
            payload = [self._serialize(r) for r in domain_rows]
            total += self.writer.upsert(sf_table, payload)

        if self.mirror_writer is not None:
            self._export_mirror(pending)

        now = datetime.now(timezone.utc)
        change_ids = [r.change_id for r in pending]
        self.session.execute(
            update(db.MdmChangeLog)
            .where(db.MdmChangeLog.change_id.in_(change_ids))
            .values(exported_at=now)
        )
        self.session.commit()
        return total

    def _export_mirror(self, pending: list) -> None:
        """Keep the sync-graph-source mirror current for this batch of changes.

        Mirrors MDM_ENTITY (every entity touched by a pending change) and
        MDM_CHANGE_LOG (the change rows themselves -- render_graph_tables'
        GRAPH_ENTITY_MERGE_LINEAGE view reads CHANGED_FIELDS:merged_from from
        this table) into the mirror_writer's schema. Domain tables are
        upserted separately in export_pending's per-type loop above, using
        the same mirror_writer target when the caller wires the domain writer
        and mirror_writer to the same schema.
        """
        assert self.mirror_writer is not None
        entity_ids = sorted({row.entity_id for row in pending})
        entities = list(
            self.session.scalars(select(db.MdmEntity).where(db.MdmEntity.entity_id.in_(entity_ids)))
        )
        self.mirror_writer.upsert("MDM_ENTITY", [self._serialize(r) for r in entities], key="entity_id")
        self.mirror_writer.upsert(
            "MDM_CHANGE_LOG", [self._serialize(r) for r in pending], key="change_id"
        )

    def export_pending_relationships(self, batch_size: int = 500) -> int:
        """Mirror relationship instances sync-graph needs, using their own
        existing graph_synced_at pending-tracking column (separate from
        mdm_change_log, which never tracked relationships -- see graph.py).
        """
        if self.mirror_writer is None:
            return 0
        stmt = (
            select(db.MdmRelationshipInstance)
            .where(db.MdmRelationshipInstance.graph_synced_at.is_(None))
            .limit(batch_size)
        )
        pending = list(self.session.scalars(stmt))
        if not pending:
            return 0

        payload = [self._serialize(r) for r in pending]
        total = self.mirror_writer.upsert("MDM_RELATIONSHIP_INSTANCE", payload, key="instance_id")

        now = datetime.now(timezone.utc)
        instance_ids = [r.instance_id for r in pending]
        self.session.execute(
            update(db.MdmRelationshipInstance)
            .where(db.MdmRelationshipInstance.instance_id.in_(instance_ids))
            .values(graph_synced_at=now)
        )
        self.session.commit()
        return total

    def sync_reference_tables(self) -> int:
        """Full-refresh the small, rarely-changing graph reference tables
        sync-graph joins against (MDM_ENTITY_TYPE_DEFINITION, MDM_RELATIONSHIP_TYPE).
        No per-row change tracking exists for these -- they are seed/config
        data, not operational writes -- so a full upsert-all each export run
        is the correct (and cheap: single-digit to low-tens of rows) strategy.
        """
        if self.mirror_writer is None:
            return 0
        total = 0
        entity_types = list(self.session.scalars(select(db.MdmEntityTypeDefinition)))
        total += self.mirror_writer.upsert(
            "MDM_ENTITY_TYPE_DEFINITION", [self._serialize(r) for r in entity_types], key="entity_type"
        )
        relationship_types = list(self.session.scalars(select(db.MdmRelationshipType)))
        total += self.mirror_writer.upsert(
            "MDM_RELATIONSHIP_TYPE", [self._serialize(r) for r in relationship_types], key="rel_type_id"
        )
        return total

    @staticmethod
    def _serialize(row: Any) -> dict:
        out: dict = {}
        for col in row.__table__.columns:
            val = getattr(row, col.name)
            if hasattr(val, "isoformat"):
                out[col.name] = val.isoformat()
            else:
                out[col.name] = val
        return out


def _safe_identifier(value: str) -> str:
    cleaned = str(value).upper()
    if not cleaned.replace("_", "").isalnum() or not cleaned[0].isalpha():
        raise ValueError(f"Unsafe Snowflake identifier: {value!r}")
    return cleaned


def _quote_identifier(value: str) -> str:
    return f'"{_safe_identifier(value)}"'


def _json_text(value: Any) -> str:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Snowflake export cannot serialize a non-finite Decimal")
        return str(value)
    return json.dumps(value)
