"""Column profile of one part: exact counts, shapes, lengths and top values.

Queries group and order by position, never by an alias a data column could shadow.

Uniqueness and distinct counts are exact (`count(DISTINCT ...)`), never the
approximate counts of DuckDB's SUMMARIZE.
"""

from __future__ import annotations

import duckdb

from .inputs import PARENT, POSITION, ROW, sql_name

STRUCTURE = (ROW, PARENT, POSITION)  # columns the input step adds
INTEGERS = {"TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UBIGINT", "UINTEGER", "USMALLINT", "UTINYINT"}
FLOATS = {"DOUBLE", "FLOAT"}
TEMPORAL = {"DATE", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE"}
TOP = 5
QUANTILES = 20  # a number's or date's distribution: 21 points, 0%, 5%, ..., 100%
CATEGORIES = 200  # a code's distribution: the shares of its 200 commonest values, the rest as "other"


def shape(expression: str) -> str:
    """SQL for a value's character-class shape: A upper, a lower, 9 digit, others kept."""
    return (f"regexp_replace(regexp_replace(regexp_replace({expression}, '[A-Z]', 'A', 'g'), "
            "'[a-z]', 'a', 'g'), '[0-9]', '9', 'g')")


def columns(con: duckdb.DuckDBPyConnection, part: str) -> list[dict]:
    """One profile per column of `part`, in table order."""
    described = con.execute(f"DESCRIBE {sql_name(part)}").fetchall()
    rows = con.execute(f"SELECT count(*) FROM {sql_name(part)}").fetchone()[0]
    return [column(con, part, name, kind, rows) for name, kind, *_ in described]


def column(con, part: str, name: str, kind: str, rows: int) -> dict:
    c, t = sql_name(name), sql_name(part)
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
    if kind == "VARCHAR" and (modal_shape or "").startswith("9999-99-99"):
        # Dates written in more than one format: count what reads as a timestamp at all.
        converts = con.execute(f"SELECT count(TRY_CAST({c} AS TIMESTAMP)) FROM {t}").fetchone()[0]
        profile["temporal_share"] = round(converts / non_null, 6)
    if kind in INTEGERS | FLOATS | TEMPORAL or kind.startswith("DECIMAL"):
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
    return profile["type"] in INTEGERS


def is_temporal(profile: dict) -> bool:
    return profile["type"] in TEMPORAL or profile.get("temporal_share", 0) >= 0.99


def is_numeric(profile: dict) -> bool:
    return is_integer(profile) or profile["type"] in FLOATS or profile["type"].startswith("DECIMAL")


def is_text(profile: dict) -> bool:
    return profile["type"] == "VARCHAR"


def distribution(con, part: str, profile: dict, code: bool) -> dict | None:
    """What a column's values look like, for compare to measure drift against:
    a code's value shares (its commonest CATEGORIES values, the rest as other),
    or a number's or date's quantiles (dates as epoch seconds). None for any other column."""
    c, t = sql_name(profile["name"]), sql_name(part)
    if not profile["non_null"] or profile["structure"]:
        return None
    if code:
        text = f"CAST({c} AS VARCHAR)"
        rows = con.execute(f"SELECT {text}, count(*) FROM {t} WHERE {c} IS NOT NULL "
                           f"GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT {CATEGORIES}").fetchall()
        shares = {v: round(n / profile["non_null"], 6) for v, n in rows}
        return {"kind": "categories", "shares": shares,
                "other": round(max(0.0, 1 - sum(n for _, n in rows) / profile["non_null"]), 6)}
    if is_numeric(profile):
        value = f"CAST({c} AS DOUBLE)"
    elif is_temporal(profile):
        value = f"epoch(TRY_CAST({c} AS TIMESTAMP))"
    else:
        return None
    points = [i / QUANTILES for i in range(QUANTILES + 1)]
    found = con.execute(f"SELECT quantile_cont({value}, {points}) FROM {t} WHERE {value} IS NOT NULL").fetchone()[0]
    return {"kind": "quantiles", "points": [round(float(q), 6) for q in found]} if found else None
