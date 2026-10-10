"""Masters held inside another part: an identifier that repeats, with the columns that follow it.

A part may carry another entity's identifier and its attributes on every row
(the party named by each document, the supplier on each order line). Where an
identifier-shaped column repeats (at most half as many values as rows) and at
least one name-like column of the same object follows it (for each identifier
value, its most common value holds on at least 95% of rows), the group is
proposed as its own part: one row per identifier value, each following column
at its most common value (ties broken by the smallest value, so every run gives
the same row). The part it came from then links to it by the identifier, and
both are classified by their own tests.

The columns that follow are those beside the identifier in the same nested
object (`party.id` with `party.name`), or, for a top-level identifier, the
other top-level columns: an attribute recorded elsewhere in the row (a role,
an amount) belongs to the row, not to the entity. A column that follows only
because one value fills nearly every row, or that is filled on fewer than half
the identifier's rows, is a coincidence and is not carried. Rows whose value
differs from the one kept are counted and reported to quality, never dropped
silently.
"""

from __future__ import annotations

from .codes import determines, name_like
from .identifiers import identifier_shaped
from .inputs import sql_name
from .quality import item

FOLLOWS = 0.95  # share of rows where each identifier value has its most common value
REPEATS = 0.5   # at most this many distinct identifier values per row
FILLED = 0.5    # a carried column is filled on at least this share of the identifier's rows


def _group(column: str) -> str:
    return column.rsplit(".", 1)[0] if "." in column else ""


def _near_constant(c: dict) -> bool:
    """One value on nearly every row: it 'follows' any identifier by coincidence."""
    return bool(c["top"]) and c["top"][0]["rows"] >= FOLLOWS * c["non_null"]


def find(con, part: str, columns: list[dict], existing: set[str]) -> tuple[list[dict], list[str]]:
    """The entities carried inside one part, with their evidence; and the names left out
    because a part of that name already exists."""
    plain = [c for c in columns if not c["structure"] and not c["name"].startswith("_")]
    found, clashes, named = [], [], set()
    for x in plain:
        if not identifier_shaped(x) or x["distinct"] > REPEATS * x["non_null"]:
            continue
        group = _group(x["name"])
        beside = [c for c in plain if c["name"] != x["name"] and _group(c["name"]) == group and c["distinct"] > 1
                  and c["non_null"] >= FILLED * x["non_null"] and not _near_constant(c)]
        shares = {c["name"]: determines(con, part, x["name"], c["name"]) for c in beside}
        follows = [c for c in beside if shares[c["name"]] >= FOLLOWS]
        if not any(name_like(c, set()) for c in follows):
            continue
        name = f"{part}.{group or x['name']}"
        if name in existing or name in named:
            clashes.append(name)
            continue
        named.add(name)
        found.append({"part": name, "from": part, "column": x["name"], "follows": [c["name"] for c in follows],
                      "evidence": {"rows": x["non_null"], "values": x["distinct"],
                                   "repeats": round(x["distinct"] / x["non_null"], 6),
                                   "follows": {c["name"]: shares[c["name"]] for c in follows}}})
    return found, clashes


def register(con, entity: dict) -> dict[str, int]:
    """The entity as a table: one row per identifier value, each column at its most common value.
    Returns, per carried column, the rows of the source part whose value differs from the one kept."""
    t, target, x = sql_name(entity["from"]), sql_name(entity["part"]), sql_name(entity["column"])
    con.execute(f"CREATE TABLE {target} AS SELECT DISTINCT {x} FROM {t} WHERE {x} IS NOT NULL")
    disagree = {}
    for column in entity["follows"]:
        c = sql_name(column)
        kind = con.execute(f"SELECT typeof({c}) FROM {t} WHERE {c} IS NOT NULL LIMIT 1").fetchone()[0]
        con.execute(f"ALTER TABLE {target} ADD COLUMN {c} {kind}")
        con.execute(f"""UPDATE {target} SET {c} = kept.v FROM (
            SELECT k, first(v ORDER BY n DESC, CAST(v AS VARCHAR)) v FROM (
                SELECT {x} k, {c} v, count(*) n FROM {t} WHERE {x} IS NOT NULL AND {c} IS NOT NULL GROUP BY 1, 2)
            GROUP BY k) kept WHERE {target}.{x} = kept.k""")
        disagree[column] = con.execute(
            f"SELECT count(*) FROM {t} JOIN {target} e ON {t}.{x} = e.{x} "
            f"WHERE {t}.{c} IS NOT NULL AND {t}.{c} IS DISTINCT FROM e.{c}").fetchone()[0]
    return disagree


def disagreements(entity: dict) -> list[dict]:
    """A quality finding for each carried column whose rows disagree with the value kept."""
    found = []
    for column, rows in entity["evidence"]["disagreeing_rows"].items():
        if rows:
            found.append(item(
                "carried_value_disagrees", column, rows, [],
                f"{rows} rows of {entity['from']} give {column} another value than the one kept for their "
                f"{entity['column']} (the most common); the entity holds one value, so these rows need a steward",
                proposal="flag"))
    return found
