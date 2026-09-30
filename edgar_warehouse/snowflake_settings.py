"""Snowflake connection settings, resolved from the environment.

Used by `edgar-warehouse resolve-snowflake-env`. Moved out of the legacy MDM
export module, which is deleted (platform validation slice 2a).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from typing import Any, Optional


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
                "for example: uv run --extra snowflake edgar-warehouse mdm publish ..."
            ) from exc

        return snowflake.connector.connect(**self.connection_kwargs())


def silver_connection_settings() -> SnowflakeConnectionSettings:
    """Snowflake connection settings scoped to the EDGARTOOLS_SILVER schema.

    Reuses SnowflakeConnectionSettings.from_env()'s env/secret resolution
    (MDM_SNOWFLAKE_* / DBT_SNOWFLAKE_* / ~/.snowflake/connections.toml) --
    that dataclass's own default schema is EDGARTOOLS_GOLD (the MDM export
    target), so this overrides just the schema to the silver landing zone's
    dbt target (DBT_SILVER_SCHEMA, matching dbt_project.yml's own default).
    Shared by mdm_entity_backfill.py's sweep and source_dimensional_export.py's Snowflake-
    silver-reading builders (dbt-gold-silver-rewiring map, Ticket 06) -- both
    need the identical "read EDGARTOOLS_SILVER directly" connection.
    """
    settings = SnowflakeConnectionSettings.from_env()
    silver_schema = os.environ.get("DBT_SILVER_SCHEMA", "EDGARTOOLS_SILVER")
    return replace(settings, schema=silver_schema)


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
