"""Keys and links between parts.

- Unique keys are exact: one column, else the smallest combination of up to
  three columns, never an approximate count.
- A link (inclusion dependency) from column F to a key column P holds when
  sigma = |F ∩ P| / |F| ≥ 0.9 over distinct values (Zhang et al. 2010). Each kept
  link is scored with the Rostin rules that need no training (coverage, value
  length, name similarity) and Zhang's randomness: a real foreign key's values
  are spread evenly over the key's ordered values, a coincidence is not.
- A part read as a sample has its key candidates read again in full.
"""

from __future__ import annotations

import itertools
from difflib import SequenceMatcher

from .identifiers import dense_sequence, identifier_shaped
from .inputs import PARENT, POSITION, ROW, Part, sql_name, full_values
from .profile import FLOATS, is_integer, is_temporal, is_text
from .sensitivity import words

THETA = 0.9
MAX_KEY_COLUMNS = 3
MAX_COMBINATION_COLUMNS = 12
RANDOMNESS = 0.7  # 1 - KS distance; below this a link must also be named alike


def _candidates(columns: list[dict]) -> list[dict]:
    """Columns that may be part of a key: never empty, not free text, not a float measure."""
    return [c for c in columns if not c["structure"] and c["fill"] == 1.0 and c["distinct"] > 1
            and c.get("tokens", 0) <= 2.0 and c["type"] not in FLOATS]


def unique_keys(con, part: str, columns: list[dict]) -> list[list[str]]:
    """Every unique single column; else the smallest unique combinations (up to three columns)."""
    rows = columns[0]["rows"] if columns else 0
    candidates = _candidates(columns)
    single = [[c["name"]] for c in candidates if c["distinct"] == rows]
    if single or not rows:
        return single
    order = {c["name"]: i for i, c in enumerate(columns)}
    pool = sorted(sorted(candidates, key=lambda c: -c["distinct"])[:MAX_COMBINATION_COLUMNS],
                  key=lambda c: order[c["name"]])
    for size in range(2, MAX_KEY_COLUMNS + 1):
        found = []
        for combo in itertools.combinations(pool, size):
            if any(set(k) <= {c["name"] for c in combo} for k in found):
                continue
            names = [c["name"] for c in combo]
            distinct = con.execute(f"SELECT count(*) FROM (SELECT DISTINCT {', '.join(map(sql_name, names))} "
                                   f"FROM {sql_name(part)})").fetchone()[0]
            if distinct == rows:
                found.append(names)
        if found:
            return found
    return []


def confirm_sampled(con, part: Part, keys: list[list[str]], columns: list[dict]) -> dict:
    """For a sampled part: read its identifier-like single-column keys in full, in one pass.

    Only identifier-shaped or integer columns are read (a unique name in a sample
    is not a key). The full values are kept as a table `<part>#<column>` so links
    are tested against every value, not only the sample.
    """
    profiles = {c["name"]: c for c in columns}
    wanted = [k[0] for k in keys if len(k) == 1 and (identifier_shaped(profiles[k[0]]) or is_integer(profiles[k[0]]))]
    if not wanted:
        return {}
    evidence = {}
    for column, (values, rows, nulls) in full_values(part, wanted, con).items():
        table = sql_name(f"{part.name}#{column}")
        con.execute(f"CREATE TABLE {table} (v VARCHAR)")
        con.executemany(f"INSERT INTO {table} VALUES (?)", [[str(v)] for v in values])
        evidence[column] = {"rows": rows, "null_rows": nulls, "distinct": len(values),
                            "unique": len(values) == rows and nulls == 0, "scan": "full"}
    return evidence


def _compatible(f: dict, p: dict) -> bool:
    if is_integer(f) and is_integer(p):
        return True
    if is_temporal(f) and is_temporal(p):
        return True
    if is_text(f) and is_text(p):
        return f["shape"] == p["shape"] or (
            f["min_length"] >= p["min_length"] and f["max_length"] <= p["max_length"]
            and f["shape_share"] >= 0.9 and p["shape_share"] >= 0.9)
    # A number stored as text in one part and as a number in the other.
    return (is_integer(f) and is_text(p) and (p["shape"] or "").strip("9") == "") or \
        (is_integer(p) and is_text(f) and (f["shape"] or "").strip("9") == "")


def name_similarity(f_part: str, f: str, p_part: str, p: str) -> float:
    """Rostin rule 7: similar column names (or the key's part named in the column)."""
    fw, pw = set(words(f)), set(words(p)) | set(words(p_part.rsplit(".", 1)[-1]))
    overlap = len(fw & pw) / len(fw | set(words(p))) if fw else 0.0
    return round(max(overlap, SequenceMatcher(None, f.lower(), p.lower()).ratio()), 3)


def _source(part: str, column: str, confirmed: dict) -> str:
    """The values of a key column: all of them for a sampled part, else the view."""
    if column in confirmed.get(part, {}):
        return f"SELECT v FROM {sql_name(part + '#' + column)}"
    return f"SELECT CAST({sql_name(column)} AS VARCHAR) v FROM {sql_name(part)}"


def inclusion(con, f_part: str, f: str, p_part: str, p: str, confirmed: dict) -> dict:
    """sigma, coverage and randomness of F's distinct values within P's."""
    sql = f"""
        WITH fv AS (SELECT DISTINCT CAST({sql_name(f)} AS VARCHAR) v FROM {sql_name(f_part)} WHERE {sql_name(f)} IS NOT NULL),
             pv AS (SELECT DISTINCT v FROM ({_source(p_part, p, confirmed)}) WHERE v IS NOT NULL),
             ranked AS (SELECT v, (row_number() OVER (ORDER BY TRY_CAST(v AS DOUBLE) NULLS LAST, v) - 0.5)
                               / count(*) OVER () r FROM pv),
             hit AS (SELECT ranked.r FROM fv JOIN ranked USING (v)),
             cdf AS (SELECT r, row_number() OVER (ORDER BY r) / count(*) OVER () c FROM hit),
             ks AS (SELECT max(abs(c - r)) d FROM cdf)
        SELECT (SELECT count(*) FROM fv), (SELECT count(*) FROM pv), (SELECT count(*) FROM hit), (SELECT d FROM ks)"""
    f_distinct, p_distinct, hits, ks = con.execute(sql).fetchone()
    return {"sigma": round(hits / f_distinct, 6) if f_distinct else 0.0,
            "coverage": round(hits / p_distinct, 6) if p_distinct else 0.0,
            "randomness": round(1 - float(ks), 3) if ks is not None else 0.0,
            "from_distinct": f_distinct, "to_distinct": p_distinct}


def links(con, profiles: dict[str, list[dict]], keys: dict[str, list[list[str]]], parts: dict[str, Part],
          confirmed: dict) -> list[dict]:
    """Every column F that points at a single-column key P of another (or the same) part."""
    found = []
    targets = [(p_part, k[0]) for p_part, ks in keys.items() for k in ks if len(k) == 1]
    for f_part, columns in profiles.items():
        for f in columns:
            if f["structure"] or f["distinct"] < 2 or f["type"] in FLOATS | {"BOOLEAN"} \
                    or f.get("tokens", 0) > 2.0:
                continue
            for p_part, p_name in targets:
                if (f_part, f["name"]) == (p_part, p_name):
                    continue
                p = next(c for c in profiles[p_part] if c["name"] == p_name)
                if not _compatible(f, p):
                    continue
                if parts[p_part].scan == "full" and f["distinct"] > p["distinct"] / THETA:
                    continue
                measured = inclusion(con, f_part, f["name"], p_part, p_name, confirmed)
                if measured["sigma"] < THETA:
                    continue
                named = name_similarity(f_part, f["name"], p_part, p_name)
                # A dense counter (1..n) contains every small number: such a link must be named alike.
                if measured["randomness"] < RANDOMNESS and named < 0.6:
                    continue
                if dense_sequence(p) and named < 0.6 and measured["randomness"] < 0.9:
                    continue
                f_unique = f["unique"] == 1.0 and f["fill"] == 1.0
                found.append({
                    "from": {"part": f_part, "columns": [f["name"]]},
                    "to": {"part": p_part, "columns": [p_name]},
                    "inclusion": measured["sigma"],
                    "cardinality": "1:1" if f_unique else "N:1",
                    "evidence": {"test": "inclusion+rostin+zhang", "coverage": measured["coverage"],
                                 "randomness": measured["randomness"], "name_similarity": named,
                                 "score": round((measured["sigma"] + measured["randomness"] + named) / 3, 3),
                                 "scan": "full" if parts[p_part].scan == "full" or p_name in confirmed.get(p_part, {})
                                 else "sampled"},
                })
    return _best_per_column(found)


def _best_per_column(found: list[dict]) -> list[dict]:
    """A column that points at several keys keeps the best-scored one, plus any equally named."""
    best: dict[tuple, dict] = {}
    for link in found:
        source = (link["from"]["part"], link["from"]["columns"][0])
        if source not in best or link["evidence"]["score"] > best[source]["evidence"]["score"]:
            best[source] = link
    return sorted(best.values(), key=lambda l: (l["from"]["part"], l["from"]["columns"]))


def composite_links(con, profiles: dict[str, list[dict]], keys: dict[str, list[list[str]]]) -> list[dict]:
    """A part holding every column of another part's composite key, by name."""
    found = []
    for p_part, ks in keys.items():
        for key in [k for k in ks if len(k) > 1]:
            for f_part, columns in profiles.items():
                if f_part == p_part or not set(key) <= {c["name"] for c in columns}:
                    continue
                cols = ", ".join(map(sql_name, key))
                f_rows, hits = con.execute(
                    f"SELECT count(*), count(*) FILTER (WHERE ({cols}) IN (SELECT ({cols}) FROM {sql_name(p_part)})) "
                    f"FROM (SELECT DISTINCT {cols} FROM {sql_name(f_part)})").fetchone()
                sigma = hits / f_rows if f_rows else 0.0
                if sigma < THETA:
                    continue
                unique = con.execute(f"SELECT count(*) = count(DISTINCT ({cols})) FROM {sql_name(f_part)}").fetchone()[0]
                found.append({"from": {"part": f_part, "columns": key}, "to": {"part": p_part, "columns": key},
                              "inclusion": round(sigma, 6), "cardinality": "1:1" if unique else "N:1",
                              "evidence": {"test": "composite inclusion, same names", "scan": "full"}})
    return found


def child_links(parts: dict[str, Part]) -> list[dict]:
    """A child part made from a list points at its parent row: always N:1, always complete."""
    return [{"from": {"part": name, "columns": [PARENT]}, "to": {"part": part.parent, "columns": [ROW]},
             "inclusion": 1.0, "cardinality": "N:1",
             "evidence": {"test": "nested list in the parent record", "scan": part.scan}}
            for name, part in sorted(parts.items()) if part.parent]


def choose_record_key(part: str, keys: list[list[str]], columns: list[dict], incoming: list[dict],
                      parent_key: list[str] | None) -> dict:
    """The record key: a found key the other parts point at, else a designed one."""
    pointed = {tuple(l["to"]["columns"]) for l in incoming if l["to"]["part"] == part}
    order = {c["name"]: i for i, c in enumerate(columns)}

    def rank(key):
        named = any(w in {"id", "key", "code", "number", "no"} for c in key for w in words(c))
        return (len(key), -(tuple(key) in pointed), -named, [order.get(c, 0) for c in key])

    if keys:
        best = min(keys, key=rank)
        return {"columns": best, "found": True, "design": None, "rule": None,
                "alternatives": [k for k in keys if k != best]}
    if parent_key is not None:
        return {"columns": [*parent_key, POSITION], "found": False, "design": "natural_composite",
                "rule": "the parent's record key plus the place in its list", "alternatives": []}
    usable = [c["name"] for c in _candidates(columns)]
    return {"columns": ["record_id"], "found": False, "design": "surrogate",
            "rule": "a durable id given when a record first appears and kept in a key map, so it never changes; "
                    f"the operator chooses which columns identify a record (candidates: {', '.join(usable) or 'none'})",
            "alternatives": []}
