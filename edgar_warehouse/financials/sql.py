"""SQL text shared by the line items and the measures: literals, inline rows, and
a query run as counted steps."""

from __future__ import annotations


def lit(text: str | None) -> str:
    return "NULL" if text is None else "'" + text.replace("'", "''") + "'"


def values(columns: str, rows: list[tuple], empty: str) -> str:
    if not rows:
        return f"SELECT * FROM (SELECT {empty}) AS v({columns}) WHERE false"
    return f"SELECT * FROM (VALUES {', '.join('(' + ', '.join(r) + ')' for r in rows)}) AS v({columns})"


def query(steps: list[tuple[str, str]], final: str) -> str:
    """The steps as one statement (PostgreSQL), for dbt."""
    return "WITH " + ",\n".join(f"{name} AS ({body})" for name, body in steps) + "\n" + final


def counted(steps: list[tuple[str, str]], final: str) -> list[str]:
    """The same query as steps, each a temporary table its planner has counted:
    run as one statement, PostgreSQL guesses each step's rows and picks nested
    loops over millions of facts (ticket 46: 30 minutes, not finished)."""
    out = []
    for name, body in steps:
        table = name.split("(")[0]
        out += [f"CREATE TEMPORARY TABLE {name} ON COMMIT DROP AS {body}", f"ANALYZE {table}"]
    return out + [final]
