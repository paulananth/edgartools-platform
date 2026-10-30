"""Logical Silver table definitions; source fields come only from a checked spec."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import json
import re

from sqlalchemy import (BigInteger, Boolean, Column, Date, DateTime, Float, Interval,
                        LargeBinary, MetaData, Numeric, String, Table, Text, Time, Uuid)
from sqlalchemy.types import TypeDecorator
from sqlalchemy.dialects.mysql import DATETIME, LONGTEXT, LONGBLOB, TIME

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.database_types import ExactJSON, UTCDateTime
from . import spec as specs


def elapsed_text(value):
    """The existing day/time delivery spelling, with exact microseconds."""
    match = re.fullmatch(r"\s*(?:([+-]?\d+)\s+days?\s+)?([+-]?)(\d+):(\d{2}):(\d{2}(?:\.\d+)?)\s*", value)
    if match is None:
        return value  # Preserve PostgreSQL's other forms; MySQL refuses them.
    from fractions import Fraction
    days, sign, hours, minutes, seconds = match.groups()
    seconds = Fraction(seconds)
    if int(minutes) >= 60 or seconds >= 60:
        raise ValueError("Invalid elapsed duration")
    microseconds = (int(hours) * 3600 + int(minutes) * 60 + seconds) * 1000000
    if microseconds.denominator != 1:
        raise ValueError("Elapsed duration exceeds microsecond precision")
    return timedelta(days=int(days or 0), microseconds=int(microseconds) * (-1 if sign == "-" else 1))


class Duration(TypeDecorator):
    """Exact delivered durations, without a calendar date or session timezone."""
    impl = Interval
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(Numeric(30, 0) if dialect.name == "mysql" else Interval())

    def process_bind_param(self, value, dialect):
        if value is None or dialect.name != "mysql": return value
        if not isinstance(value, timedelta):
            raise Blocked("MySQL Silver supports elapsed durations; calendar intervals remain unsupported")
        return (value.days * 86400 + value.seconds) * 1000000 + value.microseconds

    def process_result_value(self, value, dialect):
        if value is None or dialect.name != "mysql": return value
        from datetime import timedelta
        return timedelta(microseconds=int(value))


class ExactDecimal(TypeDecorator):
    """A DECIMAL(p,s) column that refuses a figure it cannot hold exactly; the
    database would round extra decimal places silently (ticket 46)."""
    impl = Numeric
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None: return None
        exact = Decimal(str(value))
        scale, whole = self.impl.scale, self.impl.precision - self.impl.scale
        # No more decimal places than the scale, no more whole digits than the rest.
        parts = exact.as_tuple()
        digits = len(parts.digits)
        while digits and parts.digits[digits - 1] == 0:
            digits -= 1
        exponent = parts.exponent + len(parts.digits) - digits if exact.is_finite() else 0
        if not exact.is_finite() or (exact != 0 and -exponent > scale) \
                or (exact != 0 and exact.adjusted() >= whole):
            raise Blocked(f"A figure does not fit DECIMAL({self.impl.precision},{scale}) exactly")
        return exact


class RawJSON(str):
    """Validated JSON text: preserve decimal digits before database transport."""


def json_text(value):
    """Encode exact file/Parquet decimals without routing them through float."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise Blocked("Silver JSON requires finite numbers")
        return str(value)
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise Blocked("Silver JSON object keys must be strings")
        return "{" + ",".join(json.dumps(key, ensure_ascii=False) + ":" + json_text(item)
                               for key, item in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(json_text(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class SilverJSON(ExactJSON):
    """JSON equality is structural, including object member order."""
    cache_ok = True

    def bind_processor(self, dialect):
        # Both drivers receive JSON text, never a JSON string containing that
        # text. PostgreSQL's JSONB bind cast and MySQL's LONGTEXT preserve it.
        def bind(value):
            if value is None: return None
            import edgar_control
            raw = str(value) if isinstance(value, RawJSON) else json_text(value)
            return edgar_control.canonicalize_numeric_json(raw)
        return bind

    def column_expression(self, column):
        # Read raw JSON text before the driver's default float decoder loses digits.
        from sqlalchemy import cast, type_coerce
        return type_coerce(cast(column, Text), self)

    def process_result_value(self, value, dialect):
        return json.loads(value, parse_float=Decimal) if isinstance(value, str) else value


def logical_type(logical, dialect):
    physical = specs.postgres_type(logical)
    if physical == "bigint": return BigInteger()
    if physical.startswith("numeric("):
        precision, scale = map(int, physical[8:-1].split(","))
        if dialect == "mysql" and (precision > 65 or scale > 30):
            raise Blocked("Configured decimal exceeds MySQL's supported precision or scale")
        return ExactDecimal(precision, scale)
    return {"boolean": Boolean(), "double precision": Float(53),
        "text": Text().with_variant(LONGTEXT(charset="utf8mb4", collation="utf8mb4_0900_bin"), "mysql"),
        "uuid": Uuid(as_uuid=False), "bytea": LargeBinary().with_variant(LONGBLOB(), "mysql"),
        "date": Date(), "time": Time().with_variant(TIME(fsp=6), "mysql"),
        "timestamp": DateTime().with_variant(DATETIME(fsp=6), "mysql"),
        "timestamp with time zone": UTCDateTime(), "interval": Duration(),
        "jsonb": SilverJSON()}[physical]


def data_table(spec, dialect, *, temporary=None):
    specs.check(spec)
    if dialect not in {"postgresql", "mysql"}:
        raise Blocked("Silver currently supports PostgreSQL and MySQL")
    metadata = MetaData(schema="silver" if dialect == "postgresql" and not temporary else None)
    columns = [Column(c["name"], logical_type(c["type"], dialect), nullable=c["nullable"])
               for c in spec["columns"]]
    columns += [Column(c, logical_type("VARCHAR", dialect)) for c in specs.mdm_id_columns(spec)]
    columns += [Column(c, SilverJSON()) for c in specs.quality_columns(spec)]
    if not temporary:
        columns += [Column(c, UTCDateTime(), nullable=False) for c in specs.added_time(spec)]
    table = Table(temporary or spec["table"], metadata, *columns,
                 prefixes=["TEMPORARY"] if temporary and dialect == "postgresql" else [], mysql_engine="InnoDB",
                 mysql_charset="utf8mb4", mysql_collate="utf8mb4_0900_bin")
    if dialect == "mysql" and not temporary:
        from sqlalchemy import Computed
        q = lambda name: "`" + name.replace("`", "``") + "`"
        types = {c["name"]: specs.postgres_type(c["type"]) for c in spec["columns"]}
        values = ["hex(" + q(k) + ")" if types[k] == "bytea" else
                  "nullif(" + q(k) + ",0)" if types[k] == "double precision" else q(k) for k in spec["key"]]
        expression = "sha2(cast(json_array(" + ",".join(values) + ") as binary),256)"
        table.append_column(Column("_silver_key", String(64, collation="ascii_bin"), Computed(expression, persisted=True)))
    return table


def bound_row(spec, row):
    """Convert input transport forms to driver values; databases enforce types."""
    out = dict(row)
    for column in spec["columns"]:
        name, logical = column["name"], column["type"]
        value = out.get(name)
        if value is None:
            if not column["nullable"]:
                raise Blocked(f"silver.{spec['table']}: column {name} is empty in some rows")
            out[name] = None
            continue
        physical = specs.postgres_type(logical)
        if isinstance(value, (dict, list)) and physical != "jsonb":
            raise Blocked(f"Column {name} is {physical}, not a nested value")
        try:
            if physical == "jsonb":
                if isinstance(value, str):
                    import edgar_control
                    value = RawJSON(edgar_control.canonicalize_numeric_json(value))
            elif physical == "text":
                if isinstance(value, bool): value = "true" if value else "false"
                elif isinstance(value, bytes): value = "\\x" + value.hex()
                elif isinstance(value, (date, time)): value = value.isoformat()
                elif isinstance(value, Decimal): value = format(value, "f")
                elif isinstance(value, float):
                    import math
                    if not math.isfinite(value): raise ValueError()
                    value = repr(value)
                else: value = str(value)
            elif physical == "interval" and isinstance(value, str): value = elapsed_text(value)
            elif physical == "date" and isinstance(value, str): value = date.fromisoformat(value)
            elif physical == "time" and isinstance(value, str): value = time.fromisoformat(value)
            elif physical.startswith("timestamp") and isinstance(value, str): value = datetime.fromisoformat(value)
            elif physical.startswith("numeric"): value = Decimal(str(value))
            elif physical == "bigint":
                converted = int(value)
                if Decimal(str(value)) != converted: raise ValueError()
                value = converted
            elif physical == "double precision":
                import math
                value = float(value)
                if not math.isfinite(value): raise ValueError()
            elif physical == "boolean" and isinstance(value, str):
                if value.lower() not in {"true", "false", "t", "f", "1", "0"}: raise ValueError()
                value = value.lower() in {"true", "t", "1"}
            if physical == "timestamp" and value.tzinfo is not None: raise ValueError()
            if physical == "time" and value.tzinfo is not None: raise ValueError()
        except (ValueError, TypeError, ArithmeticError):
            raise Blocked(f"silver.{spec['table']}: a value is not its column's type ({name})") from None
        out[name] = value
    return out


def staging_name(spec):
    from edgar_warehouse.control_contract import digest
    return "silver_stage_" + digest(spec)[:40]
