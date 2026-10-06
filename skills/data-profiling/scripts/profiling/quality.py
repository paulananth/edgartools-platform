"""Quality items found while profiling, handed to the data-quality skill.

Each detector is a plain function over one part's facts and returns items:
`{check, column, rows, examples, args, proposal, fix, fix_evidence, why}`.
`check` names the kind of defect; `args` holds what a check needs (a pattern,
the values of a code list, a check-digit family). Which engine check carries
it is the data-quality skill's choice, not profiling's.

Examples are at most three distinct values; a personal column's are masked to
their shape. Rows are exact counts over what was read (a sampled part counts
its sample).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import identifiers, profile, sensitivity
from .inputs import sql_name, sql_text

EXAMPLES = 3
# Generic stand-ins for "no value", compared after removing everything but letters and digits. "N/A"
# is left out: once folded it equals a real two-letter code or a short name ("NA", "Na").
PLACEHOLDERS = ("NONE", "NULL", "UNKNOWN", "TBD", "NOTAPPLICABLE", "NOTAVAILABLE")
NEAR_SHAPE = 0.95   # a column this close to one shape has outliers, not two formats
GUARDED_CODES = 50  # a code list this small is guarded as a whole


@dataclass
class Facts:
    """What one part's detectors read."""
    con: object
    part: str
    columns: list[dict]
    roles: dict[str, str]
    personal: set[str]
    key: list[str]
    links: list[dict] = field(default_factory=list)
    identifiers: list[dict] = field(default_factory=list)
    code_lists: list[dict] = field(default_factory=list)


def find(facts: Facts) -> list[dict]:
    return [item for detect in DETECTORS for item in detect(facts)]


def item(check: str, column: str | None, rows: int, examples: list, why: str, proposal: str = "flag",
         args: dict | None = None, fix=None, fix_evidence=None) -> dict:
    return {"check": check, "column": column, "rows": rows, "examples": examples, "args": args or {},
            "proposal": proposal, "fix": fix, "fix_evidence": fix_evidence, "why": why}


def _examples(facts: Facts, column: str, where: str) -> list:
    c = sql_name(column)
    found = [r[0] for r in facts.con.execute(
        f"SELECT DISTINCT CAST({c} AS VARCHAR) v FROM {sql_name(facts.part)} WHERE {where} ORDER BY 1 "
        f"LIMIT {EXAMPLES}").fetchall()]
    return [sensitivity.mask(v) for v in found] if column in facts.personal else found


def _count(facts: Facts, where: str) -> int:
    return facts.con.execute(f"SELECT count(*) FROM {sql_name(facts.part)} WHERE {where}").fetchone()[0]


def _text(c: dict) -> bool:
    return profile.is_text(c) and not c["structure"] and c["non_null"] > 0


def missing_key(facts: Facts) -> list[dict]:
    found = []
    for c in facts.columns:
        if c["name"] in facts.key and c["non_null"] < c["rows"]:
            found.append(item("missing", c["name"], c["rows"] - c["non_null"], [],
                              "a record key column is empty: the record cannot be identified",
                              proposal="exception"))
    return found


def placeholders(facts: Facts) -> list[dict]:
    found = []
    for c in facts.columns:
        if not _text(c) or facts.roles.get(c["name"]) in {"measure", "date"}:
            continue
        # Folded as the engine's placeholder test folds: upper case, then only letters and digits of any script.
        plain = f"regexp_replace(upper(CAST({sql_name(c['name'])} AS VARCHAR)), '[^\\pL\\pN]', '', 'g')"
        where = f"{plain} IN ({', '.join(sql_text(p) for p in PLACEHOLDERS)}) OR regexp_full_match({plain}, '0+')"
        rows = _count(facts, where)
        if rows:
            found.append(item("placeholder", c["name"], rows, _examples(facts, c["name"], where),
                              "a stand-in for no value, which must not match or merge",
                              proposal="withhold", args={"values": list(PLACEHOLDERS)}))
    return found


def _regex(shape: str) -> str:
    """The pattern of a shape: A an upper-case letter, a a lower-case one, 9 a digit."""
    return "".join({"A": "[A-Z]", "a": "[a-z]", "9": "[0-9]"}.get(ch, re.escape(ch)) for ch in shape)


def shape_outliers(facts: Facts) -> list[dict]:
    found = []
    # A code column is guarded by its code list: a code of another length is not an outlier.
    guarded = {code["column"] for code in facts.code_lists}
    for c in facts.columns:
        if not _text(c) or not c["shape"] or not NEAR_SHAPE <= c["shape_share"] < 1.0 or c.get("tokens", 0) > 1.0 \
                or facts.roles.get(c["name"]) in {"name", "text", "date", "measure"} or c["name"] in guarded:
            continue
        pattern = _regex(c["shape"])
        where = f"{sql_name(c['name'])} IS NOT NULL AND NOT regexp_full_match(CAST({sql_name(c['name'])} AS VARCHAR), " \
                f"{sql_text(pattern)})"
        rows = _count(facts, where)
        if rows:
            found.append(item("shape_outlier", c["name"], rows, _examples(facts, c["name"], where),
                              f"{c['shape_share']:.2%} of values share one shape; these do not",
                              args={"regex": pattern}))
    return found


def check_digits(facts: Facts) -> list[dict]:
    found = []
    for ident in facts.identifiers:
        family = ident.get("check_digit")
        if not family or ident["pass_rate"] >= 1.0:
            continue
        test = identifiers.FAMILIES[family][0]
        c = sql_name(ident["column"])
        values = [r[0] for r in facts.con.execute(
            f"SELECT DISTINCT CAST({c} AS VARCHAR) FROM {sql_name(facts.part)} WHERE {c} IS NOT NULL").fetchall()]
        failing = [v for v in values if not test(str(v).strip())]
        if not failing:
            continue  # the pass rate came from a sample of distinct values
        where = f"CAST({c} AS VARCHAR) IN (SELECT unnest(?::VARCHAR[]))"
        rows = facts.con.execute(f"SELECT count(*) FROM {sql_name(facts.part)} WHERE {where}", [failing]).fetchone()[0]
        shown = sorted(failing)[:EXAMPLES]
        column = next((c for c in facts.columns if c["name"] == ident["column"]), {})
        length = column.get("min_length") if column.get("min_length") == column.get("max_length") else None
        found.append(item("check_digit", ident["column"], rows,
                          [sensitivity.mask(v) for v in shown] if ident["column"] in facts.personal else shown,
                          f"the {family} check digit fails: a mistyped or invented identifier",
                          proposal="withhold", args={"family": family, "length": length}))
    return found


def code_list_guards(facts: Facts) -> list[dict]:
    """A small code list is guarded as a whole: a code not seen in this delivery is flagged."""
    found = []
    for code in facts.code_lists:
        if code["distinct"] > GUARDED_CODES or code["column"] in facts.personal or code["column"] in facts.key:
            continue
        c = sql_name(code["column"])
        values = [r[0] for r in facts.con.execute(
            f"SELECT DISTINCT CAST({c} AS VARCHAR) FROM {sql_name(facts.part)} WHERE {c} IS NOT NULL ORDER BY 1").fetchall()]
        found.append(item("code_list", code["column"], 0, [],
                          f"{len(values)} codes in this delivery; a new code is flagged until the code set has it",
                          args={"values": values}))
    return found


def unlinked(facts: Facts) -> list[dict]:
    found = []
    for link in facts.links:
        if link["inclusion"] >= 1.0 or len(link["from"]["columns"]) != 1:
            continue
        a, b = sql_name(link["from"]["columns"][0]), sql_name(link["to"]["columns"][0])
        where = f"{a} IS NOT NULL AND CAST({a} AS VARCHAR) NOT IN " \
                f"(SELECT CAST({b} AS VARCHAR) FROM {sql_name(link['to']['part'])} WHERE {b} IS NOT NULL)"
        found.append(item("link_not_found", link["from"]["columns"][0], _count(facts, where),
                          _examples(facts, link["from"]["columns"][0], where),
                          f"values not found in {link['to']['part']}.{link['to']['columns'][0]}",
                          args={"to": link["to"]}))
    return found


DETECTORS = (missing_key, placeholders, shape_outliers, check_digits, code_list_guards, unlinked)


def no_natural_key(record_key: dict) -> list[dict]:
    if record_key["found"]:
        return []
    return [item("no_natural_key", None, 0, [], "no column or combination is unique", fix=record_key["rule"])]


def hierarchy_items(h: dict, marked: list[dict]) -> list[dict]:
    """One item per hierarchy with invalid rows (`marked`, already masked); the rows go to the sidecar file."""
    if not marked:
        return []
    return [item("hierarchy_invalid", h["levels"][0]["column"] if h["levels"] else None, len(marked),
                 list(dict.fromkeys(m["value"] for m in marked))[:EXAMPLES],
                 f"rows that break the rule '{h['rule']}'",
                 args={"hierarchy": h["hierarchy"], "fixed": sum(m["fix"] is not None for m in marked),
                       "needs_steward": sum(m["needs_steward"] for m in marked)})]
