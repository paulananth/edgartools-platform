"""Code lists inside a part, their label columns, and functional dependencies.

A code list is a column whose few values give other rows their meaning: few
distinct values compared with the rows, short, not a measure, not a date.
"""

from __future__ import annotations

from .identifiers import identifier_shaped
from .inputs import sql_name
from .profile import FLOATS, is_numeric, is_temporal, is_text

MAX_CODES = 10_000  # the RDM bound for a code set embedded in a contract


def code_like(profile: dict) -> bool:
    if profile["structure"] or not profile["non_null"] or is_temporal(profile):
        return False
    if profile["type"] in FLOATS or profile["type"].startswith("DECIMAL"):
        return False  # a measure
    few = profile["distinct"] <= min(MAX_CODES, max(50, profile["non_null"] // 20))
    return few and profile["distinct"] >= 2 and (is_text(profile) or is_numeric(profile)) \
        and profile.get("tokens", 0) <= 4


def determines(con, part: str, a: str, b: str) -> float:
    """Share of rows that follow A → B: for each A value, its most common B value."""
    t, ca, cb = sql_name(part), sql_name(a), sql_name(b)
    held, rows = con.execute(
        f"SELECT sum(top_rows), (SELECT count(*) FROM {t} WHERE {ca} IS NOT NULL AND {cb} IS NOT NULL) FROM ("
        f"SELECT max(pair_rows) top_rows FROM (SELECT {ca} AS code_a, count(*) pair_rows FROM {t} "
        f"WHERE {ca} IS NOT NULL AND {cb} IS NOT NULL GROUP BY {ca}, {cb}) GROUP BY code_a)").fetchone()
    return round(held / rows, 6) if rows else 0.0


def code_lists(con, part: str, columns: list[dict], key: list[str], skip: set[str] = frozenset()) -> list[dict]:
    """Each code column with its label column (a column that names it one to one), if any.

    A single-column key counts too when it has a label: the part is then itself a
    list of codes. Columns in `skip` (values that identify a person) are never code lists.
    """
    keyed = [c for c in columns if key == [c["name"]]]
    # Members of a composite key may be codes; a single-column key is the part's own identity.
    codes = keyed + [c for c in columns if code_like(c) and [c["name"]] != key and c["name"] not in skip]
    found, labels = [], set()
    for code in codes:
        if code["name"] in labels:
            continue
        label = None
        for other in columns:
            if other is code or other["structure"] or not is_text(other) or other["distinct"] != code["distinct"]:
                continue
            if (other.get("tokens", 0), other["max_length"] or 0) <= (code.get("tokens", 0), code["max_length"] or 0):
                continue
            if determines(con, part, code["name"], other["name"]) == 1.0 and \
                    determines(con, part, other["name"], code["name"]) == 1.0:
                label = other["name"]
                break
        if label:
            labels.add(label)
        elif code in keyed:
            continue
        found.append({"column": code["name"], "distinct": code["distinct"], "label_column": label,
                      "code_set": None, "proposed_code_set": None})
    return [c for c in found if c["column"] not in labels]


def name_like(profile: dict, code_columns: set[str]) -> bool:
    """Text that names a thing: many different values, letters, not a code and not an identifier."""
    return (is_text(profile) and not profile["structure"] and profile["name"] not in code_columns
            and not identifier_shaped(profile) and not is_temporal(profile)
            and profile["distinct"] > 50 and any(ch.isalpha() for ch in (profile["shape"] or "")))


def code_set_name(part: dict, code: dict) -> str:
    """A code list's code set: the existing one, else the proposed name, else the part's column."""
    return code["code_set"] or code["proposed_code_set"] or f"{part['part']}.{code['column']}"


def code_sets(parts: list[dict]) -> list[dict]:
    """The RDM code sets the data set needs: one per existing or proposed code set, naming
    every column that uses it (findings spec section 2). Counts and names only: the codes
    themselves go to RDM as a draft (data-profiling, "Reference data")."""
    sets: dict[str, dict] = {}
    for f in parts:
        for code in f["code_lists"]:
            name = code_set_name(f, code)
            entry = sets.setdefault(name, {"code_set": name, "existing": bool(code["code_set"]),
                                           "columns": [], "codes": 0, "label_columns": []})
            entry["columns"].append(f"{f['part']}.{code['column']}")
            entry["codes"] = max(entry["codes"], code["distinct"])
            entry["existing"] = entry["existing"] or bool(code["code_set"])
            if code["label_column"]:
                entry["label_columns"].append(f"{f['part']}.{code['label_column']}")
    return sorted(sets.values(), key=lambda s: s["code_set"])
