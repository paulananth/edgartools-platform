"""Masters held inside another part: an identifier that repeats, with the columns that follow it.

A part may carry another entity's identifier and its attributes on every row
(the party named by each document, the supplier on each order line). Where an
identifier-shaped column repeats (at least `MIN_REPEATED` of its values on more
than one row) and at least one name-like column of the same object follows it
(over the rows whose identifier value repeats, each value's most common name holds
on at least 95% of them), the group is proposed as its own part: one row per
identifier value, each following column at its most common value (ties broken by
the smallest value, so every run gives the same row). The part it came from then
links to it by the identifier, and both are classified by their own tests.

An identifier that passes a check-digit family is issued by an authority: it names
its entity by itself, so it becomes a part even when the rows write its name in
different ways; it carries its most common name, and the rows that differ go to
quality. Two identifiers that determine each other (each follows the other) name
one entity: it is proposed once, by the better-filled one, carrying the other.

Stand-ins for "no value" in the identifier ("N/A", "000000000") are no entity and
never evidence. The columns that follow are those beside the identifier in the
same nested object (`party.id` with `party.name`), or, for a top-level identifier,
the other top-level columns: an attribute recorded elsewhere in the row (a role,
an amount) belongs to the row, not to the entity. A column that follows only
because one value fills nearly every row, or that is filled on fewer than half
the identifier's rows, is a coincidence and is not carried. Rows whose value
differs from the one kept are counted and reported to quality, never dropped
silently.
"""

from __future__ import annotations

from .codes import code_like, determines, name_like
from .identifiers import check_digits, identifier_shaped, stand_in_sql
from .inputs import sql_name
from .quality import item

FOLLOWS = 0.95     # share of repeated rows where each identifier value has its most common value
MIN_REPEATED = 20  # at least this many identifier values on more than one row: evidence, not chance
FILLED = 0.5       # a carried column is filled on at least this share of the identifier's rows


def _group(column: str) -> str:
    return column.rsplit(".", 1)[0] if "." in column else ""


def _near_constant(c: dict) -> bool:
    """One value on nearly every row: it 'follows' any identifier by coincidence."""
    return bool(c["top"]) and c["top"][0]["rows"] >= FOLLOWS * c["non_null"]


def _real(x: str) -> str:
    """Rows whose identifier holds a value, not a stand-in for none."""
    return f"{x} IS NOT NULL AND NOT {stand_in_sql(f'CAST({x} AS VARCHAR)')}"


def repeated_values(con, part: str, column: str) -> int:
    t, x = sql_name(part), sql_name(column)
    return con.execute(f"SELECT count(*) FROM (SELECT {x} FROM {t} WHERE {_real(x)} GROUP BY 1 HAVING count(*) > 1)").fetchone()[0]


def follows_on_repeats(con, part: str, a: str, b: str) -> float:
    """Share of the rows whose A value repeats where B is A's most common B: a column that follows
    an identifier on rows seen once proves nothing, so only repeated values are evidence."""
    t, ca, cb = sql_name(part), sql_name(a), sql_name(b)
    held, rows = con.execute(
        f"WITH r AS (SELECT {ca} a, {cb} b FROM {t} WHERE {_real(ca)} AND {cb} IS NOT NULL), "
        "rep AS (SELECT a FROM r GROUP BY a HAVING count(*) > 1), "
        "p AS (SELECT r.a, r.b, count(*) n FROM r JOIN rep USING (a) GROUP BY 1, 2) "
        "SELECT (SELECT sum(m) FROM (SELECT max(n) m FROM p GROUP BY a)), (SELECT sum(n) FROM p)").fetchone()
    return round(held / rows, 6) if rows else 0.0


def _issued(con, part: str, column: str) -> str | None:
    values = [r[0] for r in con.execute(
        f"SELECT DISTINCT CAST({sql_name(column)} AS VARCHAR) FROM {sql_name(part)} WHERE {_real(sql_name(column))}").fetchall()]
    return check_digits(values)["family"]


def _names_another_part(con, part: str, x: dict, keys_elsewhere: dict[str, list[dict]]) -> str | None:
    """The other part whose own identifier holds this column's values (at least 90% of them, of
    the same shape): the column links to that part's records; it carries no entity of its own."""
    t, cx = sql_name(part), sql_name(x["name"])
    for other, cols in keys_elsewhere.items():
        for k in cols:
            if other == part or k["shape"] != x["shape"]:
                continue
            held, total = con.execute(
                f"SELECT count(*) FILTER (WHERE o.v IS NOT NULL), count(*) FROM (SELECT DISTINCT CAST({cx} AS VARCHAR) v "
                f"FROM {t} WHERE {_real(cx)}) s LEFT JOIN (SELECT DISTINCT CAST({sql_name(k['name'])} AS VARCHAR) v "
                f"FROM {sql_name(other)}) o USING (v)").fetchone()
            if total and held >= 0.9 * total:
                return other
    return None


def find(con, part: str, columns: list[dict], existing: set[str],
         keys_elsewhere: dict[str, list[dict]] | None = None) -> tuple[list[dict], list[str]]:
    """The entities carried inside one part, with their evidence; and the names left out
    because a part of that name already exists. `keys_elsewhere`: each other part's unique
    identifier columns, so a column that names their records is left to the links step."""
    plain = [c for c in columns if not c["structure"] and not c["name"].startswith("_")]
    candidates = []
    for x in plain:
        if not identifier_shaped(x) or repeated_values(con, part, x["name"]) < MIN_REPEATED:
            continue
        if keys_elsewhere and _names_another_part(con, part, x, keys_elsewhere):
            continue
        group = _group(x["name"])
        beside = [c for c in plain if c["name"] != x["name"] and _group(c["name"]) == group and c["distinct"] > 1
                  and c["non_null"] >= FILLED * x["non_null"] and not _near_constant(c)]
        shares = {c["name"]: follows_on_repeats(con, part, x["name"], c["name"]) for c in beside}
        follows = {c["name"]: shares[c["name"]] for c in beside if shares[c["name"]] >= FOLLOWS}
        # A short code (a country, a currency) is no name, however many values it has.
        named = [c for c in beside if name_like(c, set()) and not code_like(c)]
        issued = _issued(con, part, x["name"])
        if not issued and not any(c["name"] in follows for c in named):
            continue
        if issued and named and not any(c["name"] in follows for c in named):
            # Its name as the rows write it most often; the rows that differ go to quality.
            best = max(named, key=lambda c: (shares[c["name"]], -plain.index(c)))
            follows[best["name"]] = shares[best["name"]]
        candidates.append((x, group, follows, issued))
    # Identifiers that determine each other name one entity: keep the better-filled one.
    kept = []
    for x, group, follows, issued in sorted(candidates, key=lambda e: (-e[0]["non_null"], plain.index(e[0]))):
        if any(x["name"] in f and k["name"] in follows for k, _, f, _ in kept):
            continue
        kept.append((x, group, follows, issued))
    found, clashes, names = [], [], set()
    for x, group, follows, issued in sorted(kept, key=lambda e: plain.index(e[0])):
        name = f"{part}.{group or x['name']}"
        if name in existing or name in names:
            clashes.append(name)
            continue
        names.add(name)
        entity = _entity(name, part, x, follows)
        entity["evidence"]["issued"] = issued
        found.append(entity)
    return found, clashes


def known(con, part: str, columns: list[dict], approved: tuple[dict, ...], existing: set[str]) -> list[dict]:
    """The entities approved findings carry inside `part`, taken by their approved identifier and columns.

    A new delivery may repeat an entity less than the discovery bar asks (each party on one
    document), yet the approved findings already say it is an entity: `compare` keeps it a part,
    with its evidence measured the same way, so its drift is reported against the approved one."""
    by_name = {c["name"]: c for c in columns}
    found = []
    for e in approved:
        x = by_name.get(e["column"])
        # Its identifier gone: drift reports the part missing. Found already: discovery's evidence stands.
        if e["from"] != part or x is None or not x["non_null"] or e["part"] in existing:
            continue
        follows = [c for c in e["follows"] if c in by_name and by_name[c]["non_null"]]
        found.append(_entity(e["part"], part, x, {c: determines(con, part, x["name"], c) for c in follows}))
    return found


def from_findings(findings: dict) -> list[dict]:
    """The entities approved findings carry inside a part, as `known` takes them."""
    found = []
    for p in findings["parts"]:
        evidence = p.get("derived_evidence") or {}
        # Findings from before the identifier was recorded: a one-column record key is it.
        column = evidence.get("column") or (p["record_key"]["columns"][0] if len(p["record_key"]["columns"]) == 1 else None)
        if p.get("derived_from") and column:
            found.append({"part": p["part"], "from": p["derived_from"], "column": column,
                          "follows": list(evidence.get("follows") or {})})
    return found


def _entity(name: str, part: str, x: dict, follows: dict[str, float]) -> dict:
    return {"part": name, "from": part, "column": x["name"], "follows": list(follows),
            "evidence": {"column": x["name"], "rows": x["non_null"], "values": x["distinct"],
                         "repeats": round(x["distinct"] / x["non_null"], 6), "follows": follows}}


def register(con, entity: dict) -> dict[str, int]:
    """The entity as a table: one row per identifier value, each column at its most common value.
    Returns, per carried column, the rows of the source part whose value differs from the one kept."""
    t, target, x = sql_name(entity["from"]), sql_name(entity["part"]), sql_name(entity["column"])
    con.execute(f"CREATE TABLE {target} AS SELECT DISTINCT {x} FROM {t} WHERE {_real(x)}")
    disagree = {}
    for column in entity["follows"]:
        c = sql_name(column)
        kind = con.execute(f"SELECT typeof({c}) FROM {t} WHERE {c} IS NOT NULL LIMIT 1").fetchone()[0]
        con.execute(f"ALTER TABLE {target} ADD COLUMN {c} {kind}")
        con.execute(f"""UPDATE {target} SET {c} = kept.v FROM (
            SELECT k, first(v ORDER BY n DESC, CAST(v AS VARCHAR)) v FROM (
                SELECT {x} k, {c} v, count(*) n FROM {t} WHERE {_real(x)} AND {c} IS NOT NULL GROUP BY 1, 2)
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
