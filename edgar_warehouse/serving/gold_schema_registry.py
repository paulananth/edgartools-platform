"""Gold schema YAML loader and validator."""

from __future__ import annotations

from importlib.resources import files
from typing import Any

import pyarrow as pa
import yaml

EXPECTED_SCHEMA_VERSION = 1
_CONFIG_RESOURCE = "gold_schemas.yaml"


class GoldSchemaConfigError(ValueError):
    """Raised when the packaged gold schema YAML is invalid."""


def load_gold_schema_config() -> dict[str, Any]:
    payload = files("edgar_warehouse.config").joinpath(_CONFIG_RESOURCE).read_text()
    config = yaml.safe_load(payload)
    if not isinstance(config, dict):
        raise GoldSchemaConfigError("gold_schemas.yaml must contain a mapping")
    return config


def load_gold_schemas() -> dict[str, pa.Schema]:
    return load_gold_schemas_from_config(load_gold_schema_config())


def load_gold_schemas_from_config(config: dict[str, Any]) -> dict[str, pa.Schema]:
    version = config.get("SCHEMA_VERSION")
    if version != EXPECTED_SCHEMA_VERSION:
        raise GoldSchemaConfigError(
            f"SCHEMA_VERSION must be {EXPECTED_SCHEMA_VERSION}; got {version!r}"
        )

    raw_schemas = config.get("schemas")
    if not isinstance(raw_schemas, dict) or not raw_schemas:
        raise GoldSchemaConfigError("schemas must be a non-empty mapping")

    schemas: dict[str, pa.Schema] = {}
    for schema_name, fields in raw_schemas.items():
        if not isinstance(schema_name, str) or not schema_name.endswith("_SCHEMA"):
            raise GoldSchemaConfigError(f"Invalid schema name: {schema_name!r}")
        if not isinstance(fields, list) or not fields:
            raise GoldSchemaConfigError(f"{schema_name} must define at least one field")
        schemas[schema_name] = pa.schema(
            [_field_from_config(schema_name, index, field) for index, field in enumerate(fields)]
        )
    return schemas


def _field_from_config(schema_name: str, index: int, field: Any) -> pa.Field:
    if not isinstance(field, dict):
        raise GoldSchemaConfigError(f"{schema_name}[{index}] must be a mapping")
    name = field.get("name")
    type_name = field.get("type")
    nullable = field.get("nullable", True)
    if not isinstance(name, str) or not name:
        raise GoldSchemaConfigError(f"{schema_name}[{index}].name must be a non-empty string")
    if not isinstance(type_name, str) or not type_name:
        raise GoldSchemaConfigError(f"{schema_name}.{name}.type must be a non-empty string")
    if not isinstance(nullable, bool):
        raise GoldSchemaConfigError(f"{schema_name}.{name}.nullable must be boolean")
    return pa.field(name, _arrow_type(type_name), nullable=nullable)


def _arrow_type(type_name: str) -> pa.DataType:
    type_factories = {
        "int64": pa.int64,
        "int32": pa.int32,
        "int16": pa.int16,
        "string": pa.string,
        "date32": pa.date32,
        "bool": pa.bool_,
        "bool_": pa.bool_,
        "float64": pa.float64,
        "timestamp_us_utc": lambda: pa.timestamp("us", tz="UTC"),
    }
    factory = type_factories.get(type_name)
    if factory is None:
        raise GoldSchemaConfigError(f"Unsupported gold schema field type: {type_name!r}")
    return factory()


_CONFIG = load_gold_schema_config()
GOLD_SCHEMAS = load_gold_schemas_from_config(_CONFIG)
SCHEMA_VERSION = EXPECTED_SCHEMA_VERSION
