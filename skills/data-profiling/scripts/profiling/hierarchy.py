"""Hierarchies inferred for each source on its own (plan decision 11).

Evidence kinds:
- functional_dependency: code columns where each value has one parent value;
- code_nesting: a parent code is the leading part of its child codes;
- parent_column: a column pointing at its own part's key (a self-link), or a
  link part whose two ends point at the same part.

A near-exact hierarchy (holds ≥ 0.99) is accepted; rows that break it are
counted as invalid for data quality.
"""

from __future__ import annotations

from .codes import determines
from .inputs import _sqlname

HOLDS = 0.99
MAX_DEPTH = 50


def _equivalent(con, part: str, columns: list[dict]) -> list[dict]:
    """Keep one column of each set that names the same thing one to one (code and its labels)."""
    kept: list[dict] = []
    for col in columns:
        if not any(k["distinct"] == col["distinct"] and determines(con, part, k["name"], col["name"]) == 1.0
                   and determines(con, part, col["name"], k["name"]) == 1.0 for k in kept):
            kept.append(col)
    return kept


def by_dependency(con, part: str, code_columns: list[dict]) -> list[dict]:
    """Chains of code columns, each level determining the next coarser one."""
    levels = sorted(_equivalent(con, part, code_columns), key=lambda c: -c["distinct"])
    parent: dict[str, tuple[str, float]] = {}
    for i, child in enumerate(levels):
        for candidate in levels[i + 1:]:
            if candidate["distinct"] >= child["distinct"]:
                continue
            held = determines(con, part, child["name"], candidate["name"])
            if held >= HOLDS:
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
    return [_record(con, part, c["columns"], c["holds"], "functional_dependency") for c in chains]


def nesting(con, part: str, child: str, parent: str) -> float:
    """Share of distinct child codes that start with their parent code."""
    t = _sqlname(part)
    total, nested = con.execute(
        f"SELECT count(*), count(*) FILTER (WHERE starts_with(CAST(c AS VARCHAR), CAST(p AS VARCHAR)) "
        f"AND length(CAST(c AS VARCHAR)) > length(CAST(p AS VARCHAR))) "
        f"FROM (SELECT DISTINCT {_sqlname(child)} c, {_sqlname(parent)} p FROM {t} "
        f"WHERE {_sqlname(child)} IS NOT NULL AND {_sqlname(parent)} IS NOT NULL)").fetchone()
    return round(nested / total, 6) if total else 0.0


def _record(con, part: str, columns: list[str], holds: float, kind: str) -> dict:
    """The hierarchy record: levels finest first, with sample codes, and how well the rule holds."""
    if kind == "functional_dependency" and all(nesting(con, part, a, b) >= HOLDS for a, b in zip(columns, columns[1:])):
        kind, rule = "code_nesting", "each code starts with its parent's code"
    else:
        rule = "each value of a level has one value at the next coarser level"
    t = _sqlname(part)
    levels = []
    for depth, column in enumerate(reversed(columns), 1):
        samples = [r[0] for r in con.execute(f"SELECT DISTINCT CAST({_sqlname(column)} AS VARCHAR) FROM {t} "
                                             f"WHERE {_sqlname(column)} IS NOT NULL ORDER BY 1 LIMIT 3").fetchall()]
        levels.append({"depth": depth, "name": None, "column": column, "samples": samples})
    rows = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    return {"hierarchy": f"{part}: {' > '.join(reversed(columns))}", "type": None, "part": part,
            "evidence_kind": kind, "levels": levels, "rule": rule, "holds": holds, "depth": len(columns),
            "shape": "balanced", "orphans": 0, "cycles": 0, "invalid_rows": round(rows * (1 - holds)),
            "valid_dates": {"from": None, "to": None}}


def by_parent_column(con, part: str, child: str, key: str) -> dict:
    """A column of a part pointing at the same part's key: depth, orphans, cycles, shape."""
    t, c, k = _sqlname(part), _sqlname(child), _sqlname(key)
    rows, orphans = con.execute(
        f"SELECT count(*), count(*) FILTER (WHERE {c} IS NOT NULL AND CAST({c} AS VARCHAR) NOT IN "
        f"(SELECT CAST({k} AS VARCHAR) FROM {t} WHERE {k} IS NOT NULL)) FROM {t}").fetchone()
    depth, cycles, leaf_depths = _walk(con, f"SELECT CAST({k} AS VARCHAR) node, CAST({c} AS VARCHAR) parent FROM {t}")
    return {"hierarchy": f"{part}: {child} → {key}", "type": None, "part": part, "evidence_kind": "parent_column",
            "levels": [{"depth": d, "name": None, "column": None, "samples": []} for d in range(1, depth + 1)],
            "rule": f"{child} names the parent row's {key}", "holds": round(1 - (orphans + cycles) / rows, 6) if rows else 0,
            "depth": depth, "shape": "balanced" if len(leaf_depths) <= 1 else "ragged", "orphans": orphans,
            "cycles": cycles, "invalid_rows": orphans + cycles, "valid_dates": {"from": None, "to": None}}


def by_link_part(con, link: str, child: str, parent: str, role: str | None) -> list[dict]:
    """A link part whose two ends name rows of one part: one hierarchy per role value."""
    t = _sqlname(link)
    roles = [None] if role is None else [r[0] for r in con.execute(
        f"SELECT DISTINCT CAST({_sqlname(role)} AS VARCHAR) FROM {t} ORDER BY 1").fetchall()]
    found = []
    for value in roles:
        where = "" if value is None else f"WHERE CAST({_sqlname(role)} AS VARCHAR) = '{value.replace(chr(39), chr(39) * 2)}'"
        edges = f"SELECT CAST({_sqlname(child)} AS VARCHAR) node, CAST({_sqlname(parent)} AS VARCHAR) parent FROM {t} {where}"
        nodes, single = con.execute(f"SELECT count(DISTINCT node), count(*) FILTER (WHERE n = 1) FROM "
                                    f"(SELECT node, count(DISTINCT parent) n FROM ({edges}) GROUP BY node)").fetchone()
        holds = round(single / nodes, 6) if nodes else 0.0
        if holds < HOLDS:
            continue  # several parents per node: a network, not a hierarchy
        depth, cycles, leaf_depths = _walk(con, edges)
        found.append({"hierarchy": f"{link}: {child} → {parent}" + (f" ({value})" if value else ""), "type": None,
                      "part": link, "evidence_kind": "parent_column", "role": value,
                      "levels": [{"depth": d, "name": None, "column": None, "samples": []} for d in range(1, depth + 1)],
                      "rule": f"{child} has one {parent} per role", "holds": holds, "depth": depth,
                      "shape": "balanced" if len(leaf_depths) <= 1 else "ragged", "orphans": 0, "cycles": cycles,
                      "invalid_rows": nodes - single + cycles, "valid_dates": {"from": None, "to": None}})
    return found


def _walk(con, edges: str) -> tuple[int, int, set]:
    """Levels of a parent graph, nodes caught in a cycle, and the set of leaf depths (one = balanced)."""
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
        SELECT count(DISTINCT start) FROM up WHERE node = start""").fetchone()[0]
    leaves = [r[0] for r in con.execute(
        f"SELECT DISTINCT node FROM ({edges}) WHERE node IS NOT NULL AND node NOT IN "
        f"(SELECT parent FROM ({edges}) WHERE parent IS NOT NULL)").fetchall()]
    leaf_depths = {ancestors.get(leaf, 0) + 1 for leaf in leaves}
    return (max(ancestors.values()) + 1 if ancestors else 1), cycles, leaf_depths
