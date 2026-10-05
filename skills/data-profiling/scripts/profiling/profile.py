"""Column profile of one part: exact counts, shapes, lengths and top values.

Queries group and order by position, never by an alias a data column could shadow.

Uniqueness and distinct counts are exact (`count(DISTINCT ...)`), never the
approximate counts of DuckDB's SUMMARIZE.
"""

from __future__ import annotations

import duckdb

from .inputs import PARENT, POSITION, ROW, _sqlname

STRUCTURE = (ROW, PARENT, POSITION)  # columns the input step adds
TOP = 5


def shape(expression: str) -> str:
    """SQL for a value's character-class shape: A upper, a lower, 9 digit, others kept."""
    return (f"regexp_replace(regexp_replace(regexp_replace({expression}, '[A-Z]', 'A', 'g'), "
            "'[a-z]', 'a', 'g'), '[0-9]', '9', 'g')")


def columns(con: duckdb.DuckDBPyConnection, part: str) -> list[dict]:
    """One profile per column of `part`, in table order."""
    described = con.execute(f"DESCRIBE {_sqlname(part)}").fetchall()
    rows = con.execute(f"SELECT count(*) FROM {_sqlname(part)}").fetchone()[0]
    return [column(con, part, name, kind, rows) for name, kind, *_ in described]


def column(con, part: str, name: str, kind: str, rows: int) -> dict:
    c, t = _sqlname(name), _sqlname(part)
    text = f"CAST({c} AS VARCHAR)"
    nested = kind.endswith("]") or kind.startswith(("STRUCT", "MAP", "JSON"))
    if nested:
        text = f"CAST(to_json({c}) AS VARCHAR)"
    non_null, distinct, min_len, max_len = con.execute(
        f"SELECT count({c}), count(DISTINCT {text}), min(length({text})), max(length({text})) FROM {t}").fetchone()
    profile = {
        "name": name, "type": kind, "rows": rows, "non_null": non_null,
        "fill": round(non_null / rows, 6) if rows else 0.0,
        "distinct": distinct,
        "unique": round(distinct / non_null, 6) if non_null else 0.0,
        "min_length": min_len, "max_length": max_len,
        "structure": name in STRUCTURE,
    }
    if not non_null:
        return {**profile, "top": [], "shape": None, "shape_share": 0.0, "length_share": 0.0, "tokens": 0.0}
    modal_shape, shape_count = con.execute(
        f"SELECT {shape(text)}, count(*) FROM {t} WHERE {c} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 1").fetchone()
    length_count = con.execute(
        f"SELECT count(*) FROM {t} WHERE {c} IS NOT NULL GROUP BY length({text}) ORDER BY 1 DESC LIMIT 1").fetchone()[0]
    tokens = con.execute(
        f"SELECT avg(len(string_split(trim({text}), ' '))) FROM {t} WHERE {c} IS NOT NULL").fetchone()[0]
    top = con.execute(
        f"SELECT {text}, count(*) FROM {t} WHERE {c} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT {TOP}").fetchall()
    profile.update({
        "shape": modal_shape, "shape_share": round(shape_count / non_null, 6),
        "length_share": round(length_count / non_null, 6),
        "tokens": round(float(tokens), 3),
        "top": [{"value": v, "rows": n} for v, n in top],
    })
    if kind in {"TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UBIGINT", "UINTEGER", "DOUBLE", "FLOAT"} \
            or kind.startswith("DECIMAL") or kind in {"DATE", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE"}:
        low, high = con.execute(f"SELECT CAST(min({c}) AS VARCHAR), CAST(max({c}) AS VARCHAR) FROM {t}").fetchone()
        profile.update({"min": low, "max": high})
    return profile


def logical_type(profile: dict) -> str:
    """The type a full read proves: text whose every value is a date (or a timestamp) is a date."""
    if profile["type"] == "VARCHAR" and profile["shape_share"] == 1.0 and profile["fill"] > 0:
        if profile["shape"] == "9999-99-99":
            return "DATE"
        if profile["shape"] in {"9999-99-99A99:99:99", "9999-99-99 99:99:99"}:
            return "TIMESTAMP"
    return profile["type"]


def is_integer(profile: dict) -> bool:
    return profile["type"] in {"TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UBIGINT", "UINTEGER"}


def is_temporal(profile: dict) -> bool:
    return profile["type"] in {"DATE", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE"} or (
        profile["shape"] in {"9999-99-99", "9999-99-99A99:99:99", "9999-99-99 99:99:99", "9999-99-99A99:99:99.999A"}
        and profile["shape_share"] >= 0.99)


def is_numeric(profile: dict) -> bool:
    return is_integer(profile) or profile["type"] in {"DOUBLE", "FLOAT"} or profile["type"].startswith("DECIMAL")


def is_text(profile: dict) -> bool:
    return profile["type"] == "VARCHAR"
