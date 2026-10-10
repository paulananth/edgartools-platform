"""Hierarchies inferred for each source on its own (plan decision 11).

Evidence kinds:
- functional_dependency: code columns where each value has one parent value;
- code_nesting: a parent code is the leading part of its child codes;
- parent_column: a column pointing at its own part's key (a self-link), or a
  link part whose two ends point at the same part;
- level_tables: lists of codes kept in separate parts, each pointing at the
  next coarser list (a subcategory list naming its category).

A near-exact hierarchy (holds ≥ 0.99) is accepted; rows that break it are
counted as invalid for data quality.

A dependency can hold by coincidence. Two tests, on the data alone, tell it
from a hierarchy:
- beyond chance: a parent level nearly constant (a flag set on almost every
  row) is "determined" by anything; the dependency must explain at least half
  of what always guessing the parent's commonest value gets wrong (lift ≥ 0.5;
  a real but skewed level with a few dirty rows still passes, so its dirty
  rows are marked);
- support: a child value seen on one row only determines its parent
  trivially; at least half the rows must carry a child value seen on two or
  more. A list of codes (one row per code) is exempt: there each code has one
  row by design;
- minority: a parent level whose values other than the commonest sit on
  fewer than 10 rows shows nothing (two rows with values of their own
  "determine" it perfectly).
A dependency failing either is reported as coincidental, with its evidence,
never as a hierarchy, and the child gets no coarser parent in its place (that
would skip a level).

A yes/no flag is never a level (operator, 2026-10-08: "Flag is not a level
(Recommended)"): a code that determines a flag is reported as a flag
dependency, and the code's search goes on to a real parent. A flag may be
written several ways in one column (0, false, 1, true). A two-valued category
with names of its own (domestic and foreign) is still a level.

Two columns that each determine the other (on at least 99% of rows: an id and
its name, with a stray spelling) name one thing; one of them stands for both,
never one as the other's level.
"""

from __future__ import annotations

from .codes import determines
from .inputs import PARENT, sql_name, sql_text

HOLDS = 0.99
MAX_DEPTH = 50
LIFT = 0.5  # the share of guessing's misses the dependency explains
SUPPORT = 0.5  # share of rows whose child value is seen on two or more rows
MINORITY = 10  # rows a parent level needs outside its commonest value to show a dependency
FLAG_VALUES = {"0", "1", "TRUE", "FALSE", "T", "F", "Y", "N", "YES", "NO"}


def is_flag(profile: dict) -> bool:
    """A yes/no column: boolean, or values that all read as yes or no (one column may spell them several ways)."""
    if profile["type"] == "BOOLEAN":
        return True
    values = {str(t["value"]).strip().upper() for t in profile["top"]}
    return 2 <= profile["distinct"] <= len(profile["top"]) and values <= FLAG_VALUES


def _hierarchy(name: str, part: str, kind: str, levels: list[dict], rule: str, holds: float, marked: list[dict], *,
               depth: int, shape: str = "balanced", orphans: int = 0, cycles: int = 0, type: str | None = None,
               **extra) -> dict:
    """One hierarchy record, as every finder writes it (findings §5)."""
    return {"hierarchy": name, "type": type, "part": part, "evidence_kind": kind, **extra, "levels": levels,
            "rule": rule, "holds": holds, "depth": depth, "shape": shape, "orphans": orphans, "cycles": cycles,
            "invalid_rows": len(marked), "valid_dates": {"from": None, "to": None}, "marked": marked}


def _equivalent(con, part: str, columns: list[dict]) -> list[dict]:
    """Keep one column of each set that names the same thing one to one (a code and its labels, an id and
    its name), each determining the other on at least HOLDS of rows."""
    kept: list[dict] = []
    for col in columns:
        if not any(determines(con, part, k["name"], col["name"]) >= HOLDS
                   and determines(con, part, col["name"], k["name"]) >= HOLDS for k in kept):
            kept.append(col)
    return kept


def chance(con, part: str, child: str, parent: str, held: float) -> dict:
    """How far a dependency child → parent is from coincidence: the share of rows the parent's commonest
    value covers (guessing it is right that often), the lift of the dependency over that guess, the
    share of rows whose child value is seen on two or more rows, and the rows outside the commonest value."""
    t, c, p = sql_name(part), sql_name(child), sql_name(parent)
    top, total, supported = con.execute(f"""
        WITH b AS (SELECT {c} AS child, {p} AS parent FROM {t} WHERE {c} IS NOT NULL AND {p} IS NOT NULL),
             n AS (SELECT count(*) AS total FROM b)
        SELECT (SELECT max(k) FROM (SELECT count(*) k FROM b GROUP BY parent)), any_value(n.total),
               (SELECT sum(k) FROM (SELECT count(*) k FROM b GROUP BY child HAVING count(*) >= 2)) / any_value(n.total)
        FROM n""").fetchone()
    top, total, supported = int(top or 0), int(total or 0), float(supported or 0)
    baseline = top / total if total else 0.0
    lift = (held - baseline) / (1 - baseline) if baseline < 1 else 0.0
    return {"held": held, "baseline": round(baseline, 6), "lift": round(lift, 6), "supported": round(supported, 6),
            "minority_rows": total - top}


def coincidental(evidence: dict, list_of_codes: bool = False) -> bool:
    return (evidence["lift"] < LIFT or (not list_of_codes and evidence["supported"] < SUPPORT)
            or evidence["minority_rows"] < MINORITY)


def by_dependency(con, part: str, code_columns: list[dict], record_key: list[str] | None = None,
                  rejected: list[dict] | None = None, list_of_codes: bool = False) -> list[dict]:
    """Chains of code columns, each level determining the next coarser one. A dependency that holds by
    coincidence is not a level; it is appended to `rejected`, with its evidence. `list_of_codes`: the
    part holds one row per code (reference data), so a code seen once is no sign of coincidence."""
    levels = sorted(_equivalent(con, part, code_columns), key=lambda c: -c["distinct"])
    parent: dict[str, tuple[str, float]] = {}
    for i, child in enumerate(levels):
        for candidate in levels[i + 1:]:
            if candidate["distinct"] >= child["distinct"]:
                continue
            held = determines(con, part, child["name"], candidate["name"])
            if held >= HOLDS:
                evidence = chance(con, part, child["name"], candidate["name"], held)
                if is_flag(candidate):
                    if rejected is not None:
                        rejected.append({"part": part, "child": child["name"], "parent": candidate["name"],
                                         "reason": "flag", **evidence})
                    continue  # a flag is not a level: the code's real parent may be coarser
                if coincidental(evidence, list_of_codes):
                    if rejected is not None:
                        rejected.append({"part": part, "child": child["name"], "parent": candidate["name"],
                                         "reason": "coincidence", **evidence})
                    break  # no coarser parent in its place: that would skip this level
                parent[child["name"]] = (candidate["name"], held)
                break  # the closest coarser level
    chains, used = [], set()
    for col in levels:
        if col["name"] in used or col["name"] in {p for p, _ in parent.values()}:
            continue
        chain, holds = [col["name"]], 1.0
        while chain[-1] in parent:
            nxt, held = parent[chain[-1]]
            chain.append(nxt)
            holds = min(holds, held)
        if len(chain) >= 2:
            used.update(chain)
            chains.append({"columns": chain, "holds": holds})
    return [_record(con, part, c["columns"], c["holds"], "functional_dependency", record_key) for c in chains]


def nesting(con, part: str, child: str, parent: str) -> float:
    """Share of distinct child codes that start with their parent code."""
    t = sql_name(part)
    total, nested = con.execute(
        f"SELECT count(*), count(*) FILTER (WHERE starts_with(CAST(c AS VARCHAR), CAST(p AS VARCHAR)) "
        f"AND length(CAST(c AS VARCHAR)) > length(CAST(p AS VARCHAR))) "
        f"FROM (SELECT DISTINCT {sql_name(child)} c, {sql_name(parent)} p FROM {t} "
        f"WHERE {sql_name(child)} IS NOT NULL AND {sql_name(parent)} IS NOT NULL)").fetchone()
    return round(nested / total, 6) if total else 0.0


def _record(con, part: str, columns: list[str], holds: float, kind: str, record_key: list[str] | None = None) -> dict:
    """The hierarchy record: levels finest first, with sample codes, and how well the rule holds."""
    if kind == "functional_dependency" and all(nesting(con, part, a, b) >= HOLDS for a, b in zip(columns, columns[1:])):
        kind, rule = "code_nesting", "each code starts with its parent's code"
    else:
        rule = "each value of a level has one value at the next coarser level"
    t = sql_name(part)
    levels = []
    for depth, column in enumerate(reversed(columns), 1):
        samples = [r[0] for r in con.execute(f"SELECT DISTINCT CAST({sql_name(column)} AS VARCHAR) FROM {t} "
                                             f"WHERE {sql_name(column)} IS NOT NULL ORDER BY 1 LIMIT 3").fetchall()]
        levels.append({"depth": depth, "name": None, "column": column, "samples": samples})
    name = f"{part}: {' > '.join(reversed(columns))}"
    marking = _Marking(con, part, name, record_key or [columns[0]])
    marked, seen = [], set()
    for a, b in zip(columns, columns[1:]):
        for m in _off_parent(marking, a, b):
            if tuple(m["key"].values()) not in seen:  # a row breaking two levels is one invalid row
                seen.add(tuple(m["key"].values()))
                marked.append(m)
    return _hierarchy(name, part, kind, levels, rule, holds, marked, depth=len(columns))


def _off_parent(marking: "_Marking", child: str, parent: str) -> list[dict]:
    """Rows whose parent code is not the one most rows with the same code have. The fix is that parent
    when more than half the code's rows have it; the counts are the evidence."""
    t, c, p = sql_name(marking.part), sql_name(child), sql_name(parent)
    keys = ", ".join(f"CAST(t.{sql_name(k)} AS VARCHAR)" for k in marking.record_key)
    rows = marking.con.execute(f"""
        WITH pairs AS (SELECT CAST({c} AS VARCHAR) code, CAST({p} AS VARCHAR) up, count(*) n FROM {t}
                       WHERE {c} IS NOT NULL AND {p} IS NOT NULL GROUP BY 1, 2),
        usual AS (SELECT code, arg_max(up, n) up, max(n) top, sum(n) total FROM pairs GROUP BY code HAVING count(*) > 1)
        SELECT {keys}, CAST(t.{c} AS VARCHAR), u.up, u.top, u.total FROM {t} t JOIN usual u ON CAST(t.{c} AS VARCHAR) = u.code
        WHERE t.{p} IS NOT NULL AND CAST(t.{p} AS VARCHAR) <> u.up ORDER BY 1""").fetchall()
    n = len(marking.record_key)
    return [marking.row(r[:n], r[n], child, parent, f"{parent} differs",
                        fix=r[n + 1] if r[n + 2] * 2 > r[n + 3] else None,
                        support={"rows": r[n + 2], "of": r[n + 3]} if r[n + 2] * 2 > r[n + 3] else None)
            for r in rows]


def by_parent_column(con, part: str, child: str, key: str, record_key: list[str] | None = None) -> dict:
    """A column of a part pointing at the same part's key: depth, orphans, cycles, shape; invalid rows marked."""
    t, c, k = sql_name(part), sql_name(child), sql_name(key)
    rows = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    orphan = f"{c} IS NOT NULL AND CAST({c} AS VARCHAR) NOT IN (SELECT CAST({k} AS VARCHAR) FROM {t} WHERE {k} IS NOT NULL)"
    depth, cycles, leaf_depths = _walk(con, f"SELECT CAST({k} AS VARCHAR) node, CAST({c} AS VARCHAR) parent FROM {t}")
    name = f"{part}: {child} → {key}"
    marking = _Marking(con, part, name, record_key or [key])
    marked = _orphans(marking, child, key, orphan)
    in_cycle = f"CAST({k} AS VARCHAR) IN (SELECT unnest(?::VARCHAR[]))"
    marked += marking.rows(f"{in_cycle} AND CAST({c} AS VARCHAR) = CAST({k} AS VARCHAR)", [cycles], key, child,
                           "names itself as its parent")
    marked += marking.rows(f"{in_cycle} AND CAST({c} AS VARCHAR) <> CAST({k} AS VARCHAR)", [cycles], key, child,
                           "on a cycle of parents")
    orphans = sum(1 for m in marked if m["reason"] == "parent not found")
    return _hierarchy(name, part, "parent_column",
                      [{"depth": d, "name": None, "column": None, "samples": []} for d in range(1, depth + 1)],
                      f"{child} names the parent row's {key}", round(1 - len(marked) / rows, 6) if rows else 0,
                      marked, depth=depth, shape="balanced" if len(leaf_depths) <= 1 else "ragged",
                      orphans=orphans, cycles=len(cycles))


class _Marking:
    """Where marked rows come from: one hierarchy of one part, each row named by the part's record key."""

    def __init__(self, con, part: str, hierarchy: str, record_key: list[str]):
        self.con, self.part, self.hierarchy = con, part, hierarchy
        # A child part's key starts with its parent's key, which its table holds as the parent's row number.
        present = {r[0] for r in con.execute(f"DESCRIBE {sql_name(part)}").fetchall()}
        own = [k for k in record_key if k in present]
        self.record_key = own if len(own) == len(record_key) or PARENT not in present else [PARENT, *own]

    def row(self, key: tuple, value, column: str, parent_column: str, reason: str, fix=None, support=None,
            fix_evidence=None) -> dict:
        """One marked row. `support` ({rows, of}) or `fix_evidence` says why the fix; without a fix, a steward
        decides. The evidence text is written once values are masked (run.py)."""
        return {"hierarchy": self.hierarchy, "part": self.part, "key": dict(zip(self.record_key, key)),
                "column": column, "value": value, "parent_column": parent_column, "reason": reason, "fix": fix,
                "support": support, "fix_evidence": fix_evidence, "needs_steward": fix is None}

    def rows(self, where: str, params: list, column: str, parent_column: str, reason: str) -> list[dict]:
        """The rows matching `where`, none with a fix."""
        cols = ", ".join(f"CAST({sql_name(c)} AS VARCHAR)" for c in [*self.record_key, column])
        return [self.row(r[:-1], r[-1], column, parent_column, reason)
                for r in self.con.execute(f"SELECT {cols} FROM {sql_name(self.part)} WHERE {where} ORDER BY 1",
                                          params).fetchall()]


def by_level_tables(con, parts: dict, links: list[dict]) -> list[dict]:
    """Chains of reference parts, each naming one row of the next coarser part by a single column.
    A chain of two or more parts is a hierarchy; its rows naming no row above are marked."""
    up = {}
    for l in links:
        a, b = l["from"], l["to"]
        if (a["part"] != b["part"] and len(a["columns"]) == 1 and l["cardinality"] == "N:1"
                and parts[a["part"]]["class"] == "reference" and parts[b["part"]]["class"] == "reference"
                and a["columns"] != parts[a["part"]]["record_key"]["columns"]):
            up.setdefault(a["part"], []).append(l)
    found = []
    pointed_at = {l["to"]["part"] for ls in up.values() for l in ls}
    for leaf in sorted(p for p in up if p not in pointed_at):
        chain, steps = [leaf], []
        # One parent per level: a list naming two lists (or one list twice) is not a chain of levels.
        while chain[-1] in up and len(up[chain[-1]]) == 1 and up[chain[-1]][0]["to"]["part"] not in chain:
            step = up[chain[-1]][0]
            steps.append(step)
            chain.append(step["to"]["part"])
        if len(chain) < 2:
            continue
        record = _level_record(con, parts, chain, steps)
        if record["holds"] >= HOLDS:  # near-exact, as every hierarchy
            found.append(record)
    return found


def _level_record(con, parts: dict, chain: list[str], steps: list[dict]) -> dict:
    """The hierarchy record of a chain of level tables, finest first."""
    name = " > ".join(reversed(chain))
    # Each level's key: the column the finer level names (the top's from its step), else the record key.
    named = {s["to"]["part"]: s["to"]["columns"][0] for s in steps}
    levels = []
    for depth, part in enumerate(reversed(chain), 1):
        key = named.get(part) or parts[part]["record_key"]["columns"][0]
        samples = [r[0] for r in con.execute(f"SELECT DISTINCT CAST({sql_name(key)} AS VARCHAR) FROM {sql_name(part)} "
                                             f"WHERE {sql_name(key)} IS NOT NULL ORDER BY 1 LIMIT 3").fetchall()]
        levels.append({"depth": depth, "name": None, "column": f"{part}.{key}", "samples": samples})
    marked = []
    for step in steps:
        child, parent = step["from"], step["to"]
        marking = _Marking(con, child["part"], name, parts[child["part"]]["record_key"]["columns"])
        marked += _orphans(marking, child["columns"][0], parent["columns"][0], parent_part=parent["part"],
                           as_number=_numeric(con, child["part"], child["columns"][0])
                           != _numeric(con, parent["part"], parent["columns"][0]))
    unparented = sum(con.execute(f"SELECT count(*) FROM {sql_name(s['from']['part'])} "
                                 f"WHERE {sql_name(s['from']['columns'][0])} IS NULL").fetchone()[0] for s in steps)
    rows = sum(con.execute(f"SELECT count(*) FROM {sql_name(s['from']['part'])}").fetchone()[0] for s in steps)
    return _hierarchy(name, chain[0], "level_tables", levels,
                      "; ".join(f"each {s['from']['part']} row names one {s['to']['part']} row by "
                                f"{s['from']['columns'][0]}" for s in steps),
                      round(1 - len(marked) / rows, 6) if rows else 0.0, marked, depth=len(chain),
                      shape="balanced" if not unparented else "ragged", orphans=len(marked), type="reference",
                      via=[{"part": s["from"]["part"], "column": s["from"]["columns"][0]} for s in steps])


def _numeric(con, part: str, column: str) -> bool:
    kind = {r[0]: r[1] for r in con.execute(f"DESCRIBE {sql_name(part)}").fetchall()}[column]
    return kind in {"TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "DOUBLE", "FLOAT"} or kind.startswith("DECIMAL")


def _orphans(marking: _Marking, child: str, key: str, orphan: str | None = None,
             parent_part: str | None = None, as_number: bool = False) -> list[dict]:
    """A parent value not found as a key. The fix is a key it equals once case, spaces and leading zeros
    are folded, when exactly one key does; otherwise a steward decides."""
    t, c, k = sql_name(marking.part), sql_name(child), sql_name(key)
    above = sql_name(parent_part) if parent_part else t  # the part whose key the value names
    # Codes compared as the link compared them: as numbers when one side is a number ("0012" is 12).
    cast = "TRY_CAST({x} AS DOUBLE)" if as_number else "CAST({x} AS VARCHAR)"
    orphan = orphan or (f"{c} IS NOT NULL AND {cast.format(x=c)} NOT IN "
                        f"(SELECT {cast.format(x=k)} FROM {above} WHERE {k} IS NOT NULL)")
    folded = "regexp_replace(upper(trim(CAST({x} AS VARCHAR))), '^0+(.)', '\\1')"
    matches = dict(marking.con.execute(
        f"SELECT o, any_value(k) FROM (SELECT DISTINCT CAST({c} AS VARCHAR) o FROM {t} WHERE {orphan}) "
        f"JOIN (SELECT CAST({k} AS VARCHAR) k FROM {above} WHERE {k} IS NOT NULL) "
        f"ON {folded.format(x='o')} = {folded.format(x='k')} GROUP BY o HAVING count(DISTINCT k) = 1").fetchall())
    marked = marking.rows(orphan, [], child, key, "parent not found")
    for m in marked:
        if m["value"] in matches:
            m.update(fix=matches[m["value"]], needs_steward=False,
                     fix_evidence="the only key equal to it once case, spaces and leading zeros are folded")
    return marked


def by_link_part(con, link: str, child: str, parent: str, role: str | None,
                 record_key: list[str] | None = None) -> list[dict]:
    """A link part whose two ends name rows of one part: one hierarchy per role value; invalid rows marked."""
    t = sql_name(link)
    roles = [None] if role is None else [r[0] for r in con.execute(
        f"SELECT DISTINCT CAST({sql_name(role)} AS VARCHAR) FROM {t} ORDER BY 1").fetchall()]
    record_key = record_key or [child, parent]
    found = []
    for value in roles:
        where = "" if value is None else f"WHERE CAST({sql_name(role)} AS VARCHAR) = {sql_text(value)}"
        edges = f"SELECT CAST({sql_name(child)} AS VARCHAR) node, CAST({sql_name(parent)} AS VARCHAR) parent FROM {t} {where}"
        nodes, single = con.execute(f"SELECT count(DISTINCT node), count(*) FILTER (WHERE n = 1) FROM "
                                    f"(SELECT node, count(DISTINCT parent) n FROM ({edges}) GROUP BY node)").fetchone()
        holds = round(single / nodes, 6) if nodes else 0.0
        if holds < HOLDS:
            continue  # several parents per node: a network, not a hierarchy
        depth, cycles, leaf_depths = _walk(con, edges)
        name = f"{link}: {child} → {parent}" + (f" ({value})" if value else "")
        in_role = "TRUE" if value is None else f"CAST({sql_name(role)} AS VARCHAR) = {sql_text(value)}"
        several = [r[0] for r in con.execute(f"SELECT node FROM ({edges}) GROUP BY node "
                                             f"HAVING count(DISTINCT parent) > 1").fetchall()]
        node = f"CAST({sql_name(child)} AS VARCHAR) IN (SELECT unnest(?::VARCHAR[]))"
        marking = _Marking(con, link, name, record_key)
        marked = marking.rows(f"{in_role} AND {node}", [several], child, parent, "several parents")
        looped = [[n for n in cycles if n not in several]]
        itself = f"CAST({sql_name(child)} AS VARCHAR) = CAST({sql_name(parent)} AS VARCHAR)"
        marked += marking.rows(f"{in_role} AND {node} AND {itself}", looped, child, parent, "names itself as its parent")
        marked += marking.rows(f"{in_role} AND {node} AND NOT ({itself})", looped, child, parent, "on a cycle of parents")
        found.append(_hierarchy(name, link, "parent_column",
                                [{"depth": d, "name": None, "column": None, "samples": []} for d in range(1, depth + 1)],
                                f"{child} has one {parent} per role", holds, marked, depth=depth,
                                shape="balanced" if len(leaf_depths) <= 1 else "ragged", cycles=len(cycles),
                                role=value))
    return found


def _walk(con, edges: str) -> tuple[int, list[str], set]:
    """Levels of a parent graph, the nodes on a cycle, and the set of leaf depths (one = balanced)."""
    ancestors = dict(con.execute(f"""
        WITH RECURSIVE e AS (SELECT DISTINCT node, parent FROM ({edges}) WHERE node IS NOT NULL AND parent IS NOT NULL),
        up(start, node, steps, path) AS (
            SELECT node, parent, 1, [node] FROM e
            UNION ALL
            SELECT up.start, e.parent, steps + 1, list_append(path, up.node) FROM up JOIN e ON e.node = up.node
            WHERE NOT list_contains(path, e.parent) AND steps < {MAX_DEPTH})
        SELECT start, max(steps) FROM up GROUP BY start""").fetchall())
    cycles = con.execute(f"""
        WITH RECURSIVE e AS (SELECT DISTINCT node, parent FROM ({edges}) WHERE node IS NOT NULL AND parent IS NOT NULL),
        up(start, node, steps) AS (SELECT node, parent, 1 FROM e
            UNION SELECT up.start, e.parent, steps + 1 FROM up JOIN e ON e.node = up.node WHERE steps < {MAX_DEPTH})
        SELECT DISTINCT start FROM up WHERE node = start ORDER BY 1""").fetchall()
    cycles = [r[0] for r in cycles]
    leaves = [r[0] for r in con.execute(
        f"SELECT DISTINCT node FROM ({edges}) WHERE node IS NOT NULL AND node NOT IN "
        f"(SELECT parent FROM ({edges}) WHERE parent IS NOT NULL)").fetchall()]
    leaf_depths = {ancestors.get(leaf, 0) + 1 for leaf in leaves}
    return (max(ancestors.values()) + 1 if ancestors else 1), cycles, leaf_depths
