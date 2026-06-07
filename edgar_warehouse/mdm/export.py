"""Incremental export from PostgreSQL -> Snowflake EDGARTOOLS_GOLD.

Reads unexported rows from mdm_change_log, materializes the current golden
record for each entity, upserts to the matching Snowflake MDM_* table, and
stamps exported_at = NOW(). No CDC or Kafka — just a drain table.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
        placeholders = ", ".join(["PARSE_JSON(%s)"] * len(columns))
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
                f"INSERT INTO {_quote_identifier(temp_table)} ({insert_columns}) VALUES ({placeholders})",
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
    session: Session
    writer: SnowflakeWriter

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

        now = datetime.now(timezone.utc)
        change_ids = [r.change_id for r in pending]
        self.session.execute(
            update(db.MdmChangeLog)
            .where(db.MdmChangeLog.change_id.in_(change_ids))
            .values(exported_at=now)
        )
        self.session.commit()
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
    import json

    return json.dumps(value)
