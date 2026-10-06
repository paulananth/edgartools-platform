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
from .inputs import sql_name, sql_text

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


def by_dependency(con, part: str, code_columns: list[dict], record_key: list[str] | None = None) -> list[dict]:
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
    marked = [m for a, b in zip(columns, columns[1:]) for m in _off_parent(con, part, a, b, record_key or [a], name)]
    return {"hierarchy": name, "type": None, "part": part,
            "evidence_kind": kind, "levels": levels, "rule": rule, "holds": holds, "depth": len(columns),
            "shape": "balanced", "orphans": 0, "cycles": 0, "invalid_rows": len(marked),
            "valid_dates": {"from": None, "to": None}, "marked": marked}


def _off_parent(con, part: str, child: str, parent: str, record_key: list[str], hierarchy: str) -> list[dict]:
    """Rows whose parent code is not the one most rows with the same code have. The fix is that parent,
    with its share of the code's rows as the evidence."""
    t, c, p = sql_name(part), sql_name(child), sql_name(parent)
    usual = con.execute(
        f"SELECT code, arg_max(up, n), max(n), sum(n) FROM (SELECT CAST({c} AS VARCHAR) code, CAST({p} AS VARCHAR) up, "
        f"count(*) n FROM {t} WHERE {c} IS NOT NULL AND {p} IS NOT NULL GROUP BY 1, 2) GROUP BY code "
        f"HAVING count(*) > 1").fetchall()
    marked = []
    for code, up, top, total in usual:
        where = f"CAST({c} AS VARCHAR) = ? AND {p} IS NOT NULL AND CAST({p} AS VARCHAR) <> ?"
        evidence = f"{top} of {total} rows with {child} {code} have {parent} {up}"
        for m in _rows_of(con, part, where, [code, up], record_key, child, hierarchy, f"{parent} differs",
                          fix=up if top * 2 > total else None, fix_evidence=evidence if top * 2 > total else None):
            marked.append(m)
    return marked


def by_parent_column(con, part: str, child: str, key: str, record_key: list[str] | None = None) -> dict:
    """A column of a part pointing at the same part's key: depth, orphans, cycles, shape; invalid rows marked."""
    t, c, k = sql_name(part), sql_name(child), sql_name(key)
    rows = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    orphan = f"{c} IS NOT NULL AND CAST({c} AS VARCHAR) NOT IN (SELECT CAST({k} AS VARCHAR) FROM {t} WHERE {k} IS NOT NULL)"
    depth, cycles, leaf_depths = _walk(con, f"SELECT CAST({k} AS VARCHAR) node, CAST({c} AS VARCHAR) parent FROM {t}")
    name = f"{part}: {child} → {key}"
    marked = _orphans(con, part, child, key, orphan, record_key or [key], name)
    in_cycle = f"CAST({k} AS VARCHAR) IN (SELECT unnest(?::VARCHAR[]))"
    marked += _rows_of(con, part, f"{in_cycle} AND CAST({c} AS VARCHAR) = CAST({k} AS VARCHAR)", [cycles],
                       record_key or [key], key, name, "names itself as its parent")
    marked += _rows_of(con, part, f"{in_cycle} AND CAST({c} AS VARCHAR) <> CAST({k} AS VARCHAR)", [cycles],
                       record_key or [key], key, name, "on a cycle of parents")
    orphans = sum(1 for m in marked if m["reason"] == "parent not found")
    return {"hierarchy": name, "type": None, "part": part, "evidence_kind": "parent_column",
            "levels": [{"depth": d, "name": None, "column": None, "samples": []} for d in range(1, depth + 1)],
            "rule": f"{child} names the parent row's {key}",
            "holds": round(1 - len(marked) / rows, 6) if rows else 0,
            "depth": depth, "shape": "balanced" if len(leaf_depths) <= 1 else "ragged", "orphans": orphans,
            "cycles": len(cycles), "invalid_rows": len(marked), "valid_dates": {"from": None, "to": None},
            "marked": marked}


def _rows_of(con, part: str, where: str, params: list, record_key: list[str], value: str, hierarchy: str,
             reason: str, fix=None, fix_evidence=None) -> list[dict]:
    """The rows matching `where`, each marked by its record key, with a fix only when there is evidence."""
    columns = ", ".join(f"CAST({sql_name(c)} AS VARCHAR)" for c in [*record_key, value])
    return [{"hierarchy": hierarchy, "part": part, "key": dict(zip(record_key, r[:-1])), "column": value,
             "value": r[-1], "reason": reason, "fix": fix, "fix_evidence": fix_evidence,
             "needs_steward": fix is None}
            for r in con.execute(f"SELECT {columns} FROM {sql_name(part)} WHERE {where} ORDER BY 1", params).fetchall()]


def _orphans(con, part: str, child: str, key: str, orphan: str, record_key: list[str], hierarchy: str) -> list[dict]:
    """A parent value not found as a key. The fix is a key it equals once case, spaces and leading zeros
    are folded, when exactly one key does; otherwise a steward decides."""
    t, c, k = sql_name(part), sql_name(child), sql_name(key)
    folded = "regexp_replace(upper(trim(CAST({x} AS VARCHAR))), '^0+(.)', '\\1')"
    matches = dict(con.execute(
        f"SELECT o, any_value(k) FROM (SELECT DISTINCT CAST({c} AS VARCHAR) o FROM {t} WHERE {orphan}) "
        f"JOIN (SELECT CAST({k} AS VARCHAR) k FROM {t} WHERE {k} IS NOT NULL) "
        f"ON {folded.format(x='o')} = {folded.format(x='k')} GROUP BY o HAVING count(DISTINCT k) = 1").fetchall())
    marked = _rows_of(con, part, orphan, [], record_key, child, hierarchy, "parent not found")
    for m in marked:
        if m["value"] in matches:
            m.update(fix=matches[m["value"]], needs_steward=False,
                     fix_evidence=f"the only key equal to it once case, spaces and leading zeros are folded")
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
        marked = _rows_of(con, link, f"{in_role} AND {node}", [several], record_key, child, name, "several parents")
        looped = [[n for n in cycles if n not in several]]
        itself = f"CAST({sql_name(child)} AS VARCHAR) = CAST({sql_name(parent)} AS VARCHAR)"
        marked += _rows_of(con, link, f"{in_role} AND {node} AND {itself}", looped, record_key, child, name,
                           "names itself as its parent")
        marked += _rows_of(con, link, f"{in_role} AND {node} AND NOT ({itself})", looped, record_key, child, name,
                           "on a cycle of parents")
        found.append({"hierarchy": name, "type": None, "part": link, "evidence_kind": "parent_column", "role": value,
                      "levels": [{"depth": d, "name": None, "column": None, "samples": []} for d in range(1, depth + 1)],
                      "rule": f"{child} has one {parent} per role", "holds": holds, "depth": depth,
                      "shape": "balanced" if len(leaf_depths) <= 1 else "ragged", "orphans": 0, "cycles": len(cycles),
                      "invalid_rows": len(marked), "valid_dates": {"from": None, "to": None}, "marked": marked})
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
