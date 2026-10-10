"""Masters held inside another part: an identifier that repeats, with the columns that follow it.

A part may carry another entity's identifier and its attributes on every row
(the party named by each document, the supplier on each order line). Where an
identifier-shaped column repeats (at most half as many values as rows) and at
least one name-like column of the same object follows it (for each identifier
value, its most common value holds on at least 95% of rows), the group is
proposed as its own part: one row per identifier value, each following column
at its most common value. The part it came from then links to it by the
identifier, and both are classified by their own tests.

The columns that follow are those beside the identifier in the same nested
object (`party.id` with `party.name`), or, for a top-level identifier, the
other top-level columns: an attribute recorded elsewhere in the row (a role,
an amount) belongs to the row, not to the entity.
"""

from __future__ import annotations

from .codes import determines, name_like
from .identifiers import identifier_shaped
from .inputs import sql_name

FOLLOWS = 0.95  # share of rows where each identifier value has its most common value
REPEATS = 0.5   # at most this many distinct identifier values per row


def _group(column: str) -> str:
    return column.rsplit(".", 1)[0] if "." in column else ""


def find(con, part: str, columns: list[dict], taken: set[str]) -> list[dict]:
    """The embedded entities of one part: its identifier, the columns that follow it, the new part's name."""
    plain = [c for c in columns if not c["structure"] and not c["name"].startswith("_")]
    found = []
    for x in plain:
        if not identifier_shaped(x) or x["distinct"] > REPEATS * x["non_null"]:
            continue
        group = _group(x["name"])
        beside = [c for c in plain if c["name"] != x["name"] and _group(c["name"]) == group and c["distinct"] > 1]
        follows = [c for c in beside if determines(con, part, x["name"], c["name"]) >= FOLLOWS]
        if not any(name_like(c, set()) for c in follows):
            continue
        name = f"{part}.{group or x['name']}"
        if name in taken:
            continue
        taken.add(name)
        found.append({"part": name, "from": part, "column": x["name"], "follows": [c["name"] for c in follows]})
    return found


def register(con, entity: dict) -> None:
    """The embedded entity as a table: one row per identifier value, each column at its most common value."""
    x = sql_name(entity["column"])
    rest = "".join(f", mode({sql_name(c)}) AS {sql_name(c)}" for c in entity["follows"])
    con.execute(f"CREATE TABLE {sql_name(entity['part'])} AS SELECT {x}{rest} "
                f"FROM {sql_name(entity['from'])} WHERE {x} IS NOT NULL GROUP BY {x}")
