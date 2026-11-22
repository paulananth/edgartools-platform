"""SQL text shared by the line items and the measures: literals, inline rows, and
a query run as counted steps."""

from __future__ import annotations


def lit(text: str | None) -> str:
    return "NULL" if text is None else "'" + text.replace("'", "''") + "'"


def annual(start: str, end: str) -> str:
    """A period of 364-371 days, counting its first and last day: a year (ticket 35)."""
    return f"{end} - {start} + 1 BETWEEN 364 AND 371"


def fiscal_year(end: str) -> str:
    """Compustat FYEAR of a period's end: an end in January to May is the previous year's (ticket 35)."""
    return (f"CAST(CASE WHEN extract(month FROM {end}) >= 6 THEN extract(year FROM {end})\n"
            f"                         ELSE extract(year FROM {end}) - 1 END AS bigint)")


def values(columns: str, rows: list[tuple], empty: str) -> str:
    if not rows:
        return f"SELECT * FROM (SELECT {empty}) AS v({columns}) WHERE false"
    return f"SELECT * FROM (VALUES {', '.join('(' + ', '.join(r) + ')' for r in rows)}) AS v({columns})"


def query(steps: list[tuple[str, str]], final: str) -> str:
    """The steps as one statement (PostgreSQL), for dbt."""
    return "WITH " + ",\n".join(f"{name} AS ({body})" for name, body in steps) + "\n" + final


def steered(steps: list[tuple[str, str]], final: str) -> list[str]:
    """The query as one statement, with the planner kept off nested loops for its transaction: left to guess each
    step's rows, PostgreSQL picks nested loops over millions of facts (30 minutes, not finished). A session setting,
    not a temporary table: run-time code issues no DDL. On the company-facts cohort it gives the same rows as the
    counted steps did, faster (line items 28 s against 98 s, measures 12 s against 13 s, on one local store)."""
    return ["SET LOCAL enable_nestloop = off", query(steps, final)]
