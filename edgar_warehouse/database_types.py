"""Lossless SQL value transport shared by storage boundaries."""
import json
from datetime import UTC

from sqlalchemy import Text, DateTime
from sqlalchemy.dialects.mysql import LONGTEXT, DATETIME
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator


class ExactJSON(TypeDecorator):
    """Preserve JSON integers and text; do not coerce through MySQL JSON numbers."""

    impl = Text
    cache_ok = True

    def __init__(self, *, none_as_null: bool = False):
        """`none_as_null`: Python None is SQL NULL, not the JSON value null."""
        super().__init__()
        self.none_as_null = none_as_null

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB(none_as_null=self.none_as_null))
        if dialect.name == "mysql":
            return dialect.type_descriptor(LONGTEXT(charset="utf8mb4", collation="utf8mb4_0900_bin"))
        raise ValueError("Exact JSON storage currently supports PostgreSQL and MySQL")

    def process_bind_param(self, value, dialect):
        if dialect.name == "postgresql" or (value is None and self.none_as_null):
            return value
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))

    def process_result_value(self, value, dialect):
        return json.loads(value) if isinstance(value, str) else value


class UTCDateTime(TypeDecorator):
    """UTC instants: MySQL DATETIME stores UTC, PostgreSQL keeps its native zone."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(DATETIME(fsp=6) if dialect.name == "mysql" else DateTime(timezone=True))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("An instant requires an explicit timezone")
        value = value.astimezone(UTC)
        return value.replace(tzinfo=None) if dialect.name == "mysql" else value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
