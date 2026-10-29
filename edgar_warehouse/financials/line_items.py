"""The standard line items (ticket 46): `rules/sources/sec.company-facts/line-items.yaml`
read once, and the one SQL query that builds silver's `company_line_item` from the
facts in silver's `company_fact` (operator, 2026-10-28: "SQL over silver").

For each company and fiscal year (Compustat FYEAR of the annual period's end), each
line item takes the first entry of its list, in the year's taxonomy, that has a
value; an entry reads a concept's latest-filed copy for exactly that period. A
missing line item is a row with an empty value and its reason. The rulings are
`skills/company-financials/SKILL.md`; the answer key (ticket 44) checks the result.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from edgar_warehouse.control_contract import Blocked

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "rules" / "sources" / "sec.company-facts" / "line-items.yaml"
PUBLISHED = ROOT / "rules" / "reference" / "published"
TAXONOMIES = ("us-gaap", "ifrs-full")
ANNUAL_REPORTS = ("10-K", "20-F", "40-F")
NO_CONCEPT = "no concept filed"

# How a flagged concept relates to its line item, as SKOS mapping relations:
# broad when it holds more than the line item, narrow when less, close when it
# is the same figure read another way. A new flag needs its line here.
FLAG_MATCH = {
    "includes NCI": "broad", "includes software and intangibles": "broad",
    "includes intangibles and other assets": "broad", "includes restricted cash": "broad",
    "includes other finance costs": "broad", "includes impairment": "broad",
    "continuing operations": "narrow", "excludes amortization": "narrow",
    "excludes amortisation": "narrow", "cash only": "narrow", "cover-page date": "close",
}
_CONCEPT = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,199}")
_WORDS = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ,:.()-]{0,99}")


@dataclass(frozen=True)
class Term:
    """One term of a computed value: the first present of `concepts` (taxonomy,
    concept), or another line item's value; `optional` counts as nothing when absent."""
    concepts: tuple[tuple[str, str], ...] = ()
    line_item: str | None = None
    optional: bool = False


@dataclass(frozen=True)
class Entry:
    """One entry of a line item's list: a concept, or a computed sum or difference."""
    flags: tuple[str, ...]
    concept: tuple[str, str] | None = None
    match: str = "close"
    computed: str | None = None
    terms: tuple[Term, ...] = ()


@dataclass(frozen=True)
class LineItems:
    version: str
    code_set: dict
    period: dict[str, str]  # each code's period: duration or instant (the code set's property)
    lists: dict[str, dict[str, tuple[Entry, ...]]]
    larger_total_check: dict[str, str]  # line item -> the flag when another entry is larger

    def stages(self) -> list[list[str]]:
        """The line items in order of what they read: a stage reads line items of earlier stages only."""
        reads = {code: {t.line_item for lst in lists.values() for e in lst for t in e.terms if t.line_item}
                 for code, lists in self.lists.items()}
        done: list[str] = []
        out = []
        while len(done) < len(reads):
            ready = [c for c in reads if c not in done and reads[c] <= set(done)]
            if not ready:
                raise Blocked(f"line items read each other in a cycle: {sorted(set(reads) - set(done))}")
            out.append(ready)
            done += ready
        return out


def _published(code_set: str, version: str) -> list[dict]:
    folder = PUBLISHED / code_set / version
    data = (folder / "canonical.jsonl").read_bytes()
    if hashlib.sha256(data).hexdigest() != json.loads((folder / "pin.json").read_text())["sha256"]:
        raise Blocked(f"{code_set} {version} differs from its pin")
    return [json.loads(line) for line in data.decode().splitlines()]


def _concept(name, taxonomy: str) -> tuple[str, str]:
    """A concept's taxonomy and name; `dei:` names a cover-page concept."""
    taxonomy, name = ("dei", name[4:]) if isinstance(name, str) and name.startswith("dei:") else (taxonomy, name)
    if not isinstance(name, str) or not _CONCEPT.fullmatch(name):
        raise Blocked(f"not a concept name: {name!r}")
    return taxonomy, name


def _words(text) -> str:
    if not isinstance(text, str) or not _WORDS.fullmatch(text):
        raise Blocked(f"a flag is plain words: {text!r}")
    return text


def _term(raw, taxonomy: str, codes: set[str]) -> Term:
    if isinstance(raw, str):
        return Term(concepts=(_concept(raw, taxonomy),))
    if isinstance(raw, dict) and set(raw) == {"optional"}:
        inner = _term(raw["optional"], taxonomy, codes)
        if inner.optional:
            raise Blocked("an optional term is not optional twice")
        return Term(inner.concepts, inner.line_item, optional=True)
    if isinstance(raw, dict) and set(raw) == {"first_of"} and isinstance(raw["first_of"], list) and raw["first_of"]:
        return Term(concepts=tuple(_concept(c, taxonomy) for c in raw["first_of"]))
    if isinstance(raw, dict) and set(raw) == {"line_item"}:
        if raw["line_item"] not in codes:
            raise Blocked(f"a term names an unknown line item: {raw['line_item']!r}")
        return Term(line_item=raw["line_item"])
    raise Blocked(f"a term is a concept, first_of, line_item or optional: {raw!r}")


def _entry(raw, taxonomy: str, codes: set[str]) -> Entry:
    if isinstance(raw, str):
        return Entry(flags=(), concept=_concept(raw, taxonomy))
    if not isinstance(raw, dict):
        raise Blocked(f"an entry is a concept or a mapping: {raw!r}")
    if "concept" in raw and set(raw) in ({"concept", "flag"}, {"concept", "kind"}):
        if "flag" in raw:
            flag = _words(raw["flag"])
            if flag not in FLAG_MATCH:
                raise Blocked(f"a flag with no match type: {flag!r}")
            return Entry(flags=(flag,), concept=_concept(raw["concept"], taxonomy), match=FLAG_MATCH[flag])
        return Entry(flags=(f"kind: {_words(raw['kind'])}",), concept=_concept(raw["concept"], taxonomy))
    if "computed" in raw and set(raw) <= {"computed", "terms", "flag"}:
        if raw["computed"] not in ("sum", "difference") or not isinstance(raw.get("terms"), list) or not raw["terms"]:
            raise Blocked(f"a computed entry is a sum or a difference of terms: {raw!r}")
        terms = tuple(_term(t, taxonomy, codes) for t in raw["terms"])
        if terms[0].optional:
            raise Blocked("a computed entry's first term is required: a sum of optional terms alone is never a value")
        if all(t.line_item for t in terms):
            raise Blocked("a computed entry reads at least one fact: it names that fact's filing")
        return Entry(flags=("computed",) + ((_words(raw["flag"]),) if "flag" in raw else ()),
                     computed=raw["computed"], terms=terms)
    raise Blocked(f"an entry is a concept, {{concept, flag}}, {{concept, kind}} or {{computed, terms, flag}}: {raw!r}")


def parse(body: dict) -> LineItems:
    """The map, checked whole: every code is the pinned code set's, in both taxonomies."""
    pin = body["code_set"]
    period = {row["code"]: row["properties"]["period"] for row in _published(pin["code_set"], pin["version"])}
    if set(body["line_items"]) != set(period):
        raise Blocked("the map names exactly the code set's codes")
    codes = set(period)
    lists = {}
    for code, raw in body["line_items"].items():
        if set(raw) != set(TAXONOMIES):
            raise Blocked(f"{code} lists {TAXONOMIES} both")
        lists[code] = {t: tuple(_entry(e, t, codes) for e in raw[t]) for t in TAXONOMIES}
    checks = body.get("larger_total_check") or {}
    if not set(checks) <= codes:
        raise Blocked("larger_total_check names line items")
    items = LineItems(body["version"], pin, period, lists, {c: _words(f) for c, f in checks.items()})
    items.stages()
    return items


def load(path: Path = MAP) -> LineItems:
    import yaml

    return parse(yaml.safe_load(path.read_text()))


def crosswalk_of(items: LineItems) -> dict[tuple[str, str, str], str]:
    """Each (line item, taxonomy, concept) the map tries as the line item itself,
    with its match type. A computed value's terms are inputs, not mappings, so
    they stay in the map only."""
    return {(code, *e.concept): e.match for code, lists in items.lists.items()
            for t in TAXONOMIES for e in lists[t] if e.concept}


# --- the query ---------------------------------------------------------------------

def _lit(text: str | None) -> str:
    return "NULL" if text is None else "'" + text.replace("'", "''") + "'"


def _flags(flags) -> str:
    return "ARRAY[" + ", ".join(_lit(f) for f in flags) + "]::text[]" if flags else "ARRAY[]::text[]"


def _values(columns: str, rows: list[tuple], empty: str) -> str:
    if not rows:
        return f"SELECT {empty} WHERE false"
    return f"SELECT * FROM (VALUES {', '.join('(' + ', '.join(r) + ')' for r in rows)}) AS v({columns})"


def query(items: LineItems, source: str = "silver.company_fact") -> str:
    """One SQL statement (PostgreSQL) over `source`, giving every row of
    `company_line_item`: one per company, line item and fiscal year."""
    kind = {code: "instant" if p == "instant" else "annual" for code, p in items.period.items()}
    direct, terms, computed = [], [], []
    for code, lists in items.lists.items():
        for taxonomy in TAXONOMIES:
            for position, entry in enumerate(lists[taxonomy], 1):
                key = [_lit(code), _lit(taxonomy), str(position)]
                if entry.concept:
                    direct.append((*key, _lit(entry.concept[0]), _lit(entry.concept[1]), _lit(kind[code]),
                                   _flags(entry.flags)))
                    continue
                computed.append((*key, _flags(entry.flags)))
                for number, term in enumerate(entry.terms, 1):
                    sign = "-1" if entry.computed == "difference" and number > 1 else "1"
                    for choice, (term_taxonomy, concept) in enumerate(term.concepts or [(None, None)], 1):
                        terms.append((*key, str(number), str(choice), sign, "true" if term.optional else "false",
                                      _lit(term_taxonomy), _lit(concept), _lit(term.line_item), _lit(kind[code])))
    named = sorted({(r[3], r[4]) for r in direct} | {(r[7], r[8]) for r in terms if r[8] != "NULL"})
    entry_columns = "line_item, taxonomy, position"
    ctes = [
        f"""entry AS ({_values(entry_columns + ", concept_taxonomy, concept, kind, flags", direct,
                                "NULL::text, NULL::text, 0, NULL::text, NULL::text, NULL::text, NULL::text[]")})""",
        f"""computed_entry AS ({_values(entry_columns + ", flags", computed,
                                         "NULL::text, NULL::text, 0, NULL::text[]")})""",
        f"""term AS ({_values(entry_columns + ", term, choice, sign, optional, concept_taxonomy, concept, line_item_ref, kind",
                              terms, "NULL::text, NULL::text, 0, 0, 0, 0, false, NULL::text, NULL::text, NULL::text, NULL::text")})""",
        f"""named(taxonomy, concept) AS (VALUES {", ".join(f"({t}, {c})" for t, c in named)})""",
        # Each fact with its period's kind: an instant, or an annual period of 364-371 days (ticket 35).
        f"""fact AS (
  SELECT f.company_key, f.taxonomy, f.concept, f.unit, f.currency, f.period_start, f.period_end, f.value,
         f.accession, f.filed, f.form,
         CASE WHEN f.period_start IS NULL THEN 'instant'
              WHEN f.period_end - f.period_start + 1 BETWEEN 364 AND 371 THEN 'annual' END AS kind
  FROM {source} f)""",
        """annual AS (SELECT * FROM fact WHERE kind = 'annual' AND taxonomy IN ('us-gaap', 'ifrs-full'))""",
        # Each annual report's own period: the annual period it files the most facts for, the later on a tie.
        f"""report_end AS (
  SELECT DISTINCT ON (company_key, accession) company_key, accession, period_end
  FROM annual WHERE split_part(form, '/', 1) IN ({", ".join(map(_lit, ANNUAL_REPORTS))})
  GROUP BY company_key, accession, period_end
  ORDER BY company_key, accession, count(*) DESC, period_end DESC)""",
        # Each fiscal year (Compustat FYEAR: an end in January to May is the previous year's): the latest
        # end an annual report covers as its own year, else the latest end (ticket 35).
        """year_end AS (
  SELECT DISTINCT ON (a.company_key, a.fiscal_year) a.company_key, a.fiscal_year, a.period_end
  FROM (SELECT DISTINCT company_key, period_end,
               CAST(CASE WHEN extract(month FROM period_end) >= 6 THEN extract(year FROM period_end)
                         ELSE extract(year FROM period_end) - 1 END AS bigint) AS fiscal_year
        FROM annual) a
  LEFT JOIN (SELECT DISTINCT company_key, period_end FROM report_end) r
         ON r.company_key = a.company_key AND r.period_end = a.period_end
  ORDER BY a.company_key, a.fiscal_year, (r.period_end IS NOT NULL) DESC, a.period_end DESC)""",
        # The year's taxonomy: the one most facts use in the latest filing holding an annual fact
        # ending that day (ticket 42); us-gaap on a tie.
        """fiscal AS (
  SELECT DISTINCT ON (y.company_key, y.fiscal_year) y.company_key, y.fiscal_year, y.period_end, a.taxonomy
  FROM year_end y JOIN annual a ON a.company_key = y.company_key AND a.period_end = y.period_end
  GROUP BY y.company_key, y.fiscal_year, y.period_end, a.filed, a.accession, a.taxonomy
  ORDER BY y.company_key, y.fiscal_year, a.filed DESC, a.accession DESC, count(*) DESC,
           (a.taxonomy = 'us-gaap') DESC)""",
        # Each filing's units, by how many facts use them: a copy filed in two units keeps the one its
        # filing uses most (its reporting currency; ticket 42 never converts), then the unit's text.
        """filing_unit AS (SELECT company_key, accession, unit, count(*) AS uses FROM fact GROUP BY 1, 2, 3)""",
        # Each named concept's latest-filed copy for a year's exact period.
        """copy AS (
  SELECT DISTINCT ON (f.company_key, y.fiscal_year, f.taxonomy, f.concept, f.kind)
         y.fiscal_year, f.company_key, f.taxonomy, f.concept, f.kind, f.unit, f.currency, f.period_start,
         f.value, f.accession, f.filed
  FROM fact f
  JOIN named n ON n.taxonomy = f.taxonomy AND n.concept = f.concept
  JOIN year_end y ON y.company_key = f.company_key AND y.period_end = f.period_end
  JOIN filing_unit u ON u.company_key = f.company_key AND u.accession = f.accession AND u.unit = f.unit
  WHERE f.kind IS NOT NULL
  ORDER BY f.company_key, y.fiscal_year, f.taxonomy, f.concept, f.kind, f.filed DESC, f.accession DESC,
           u.uses DESC, f.unit COLLATE "C", f.period_start DESC)""",
        """direct AS (
  SELECT y.company_key, y.fiscal_year, e.line_item, e.position, c.value, c.unit, c.currency, c.period_start,
         c.concept, c.accession, c.filed, e.flags, NULL::jsonb AS inputs
  FROM fiscal y JOIN entry e ON e.taxonomy = y.taxonomy
  JOIN copy c ON c.company_key = y.company_key AND c.fiscal_year = y.fiscal_year
             AND c.taxonomy = e.concept_taxonomy AND c.concept = e.concept AND c.kind = e.kind)""",
        # Each fact term's value: the first present of its concepts.
        """fact_term AS (
  SELECT DISTINCT ON (y.company_key, y.fiscal_year, t.line_item, t.position, t.term)
         y.company_key, y.fiscal_year, t.line_item, t.position, t.term, c.value, c.unit, c.currency,
         c.period_start, c.concept, c.accession, c.filed
  FROM fiscal y JOIN term t ON t.taxonomy = y.taxonomy AND t.concept IS NOT NULL
  JOIN copy c ON c.company_key = y.company_key AND c.fiscal_year = y.fiscal_year
             AND c.taxonomy = t.concept_taxonomy AND c.concept = t.concept AND c.kind = t.kind
  ORDER BY y.company_key, y.fiscal_year, t.line_item, t.position, t.term, t.choice)""",
    ]
    chosen = []
    for stage, codes in enumerate(items.stages()):
        earlier = " UNION ALL ".join(f"SELECT * FROM chosen_{s}" for s in range(stage)) or (
            "SELECT * FROM direct WHERE false")
        inside = ", ".join(map(_lit, codes))
        ctes.append(f"""term_{stage} AS (
  SELECT y.company_key, y.fiscal_year, y.taxonomy, t.line_item, t.position, t.term, t.sign, t.optional,
         COALESCE(f.value, l.value) AS value, COALESCE(f.unit, l.unit) AS unit,
         COALESCE(f.currency, l.currency) AS currency, f.period_start, f.concept, f.accession, f.filed,
         t.line_item_ref
  FROM fiscal y JOIN term t ON t.taxonomy = y.taxonomy AND t.choice = 1 AND t.line_item IN ({inside})
  LEFT JOIN fact_term f ON f.company_key = y.company_key AND f.fiscal_year = y.fiscal_year
        AND f.line_item = t.line_item AND f.position = t.position AND f.term = t.term
  LEFT JOIN ({earlier}) l ON t.line_item_ref IS NOT NULL AND l.company_key = y.company_key
        AND l.fiscal_year = y.fiscal_year AND l.line_item = t.line_item_ref AND l.value IS NOT NULL)""")
        # A computed entry: every required term present, one unit; it names its first fact term's filing.
        ctes.append(f"""computed_{stage} AS (
  SELECT v.company_key, v.fiscal_year, v.line_item, v.position, sum(v.sign * v.value) AS value,
         min(v.unit) AS unit, min(v.currency) AS currency,
         (array_agg(v.period_start ORDER BY v.term) FILTER (WHERE v.accession IS NOT NULL))[1] AS period_start,
         'computed' AS concept,
         (array_agg(v.accession ORDER BY v.term) FILTER (WHERE v.accession IS NOT NULL))[1] AS accession,
         (array_agg(v.filed ORDER BY v.term) FILTER (WHERE v.accession IS NOT NULL))[1] AS filed,
         e.flags,
         jsonb_agg(jsonb_strip_nulls(jsonb_build_object('concept', v.concept, 'line_item', v.line_item_ref,
             'accession', v.accession, 'value', v.value::text)) ORDER BY v.term)
             FILTER (WHERE v.value IS NOT NULL) AS inputs
  FROM term_{stage} v JOIN computed_entry e
    ON e.line_item = v.line_item AND e.taxonomy = v.taxonomy AND e.position = v.position
  GROUP BY v.company_key, v.fiscal_year, v.line_item, v.position, e.flags
  HAVING bool_and(v.value IS NOT NULL OR v.optional) AND count(DISTINCT v.unit) = 1)""")
        ctes.append(f"""chosen_{stage} AS (
  SELECT DISTINCT ON (company_key, fiscal_year, line_item) * FROM (
    SELECT * FROM direct WHERE line_item IN ({inside})
    UNION ALL SELECT * FROM computed_{stage}) x
  ORDER BY company_key, fiscal_year, line_item, position)""")
        chosen.append(f"SELECT * FROM chosen_{stage}")
    ctes.append(f"chosen AS ({' UNION ALL '.join(chosen)})")
    checks = [(_lit(code), _lit(flag)) for code, flag in items.larger_total_check.items()]
    ctes.append(f"""larger_total_check AS ({_values("line_item, flag", checks, "NULL::text, NULL::text")})""")
    codes = ", ".join(f"({_lit(c)}, {_lit(kind[c])})" for c in items.lists)
    return "WITH " + ",\n".join(ctes) + f"""
SELECT y.company_key, i.line_item, y.fiscal_year,
       CASE WHEN i.kind = 'annual' THEN c.period_start END AS period_start, y.period_end,
       c.value, c.unit, c.currency, y.taxonomy, c.concept, c.inputs, c.accession, c.filed,
       to_jsonb(COALESCE(c.flags, ARRAY[]::text[]) || CASE WHEN EXISTS (
           SELECT 1 FROM direct d WHERE d.company_key = c.company_key AND d.fiscal_year = c.fiscal_year
              AND d.line_item = c.line_item AND d.unit = c.unit AND d.value > c.value)
         THEN (SELECT array_agg(k.flag) FROM larger_total_check k WHERE k.line_item = c.line_item)
         ELSE ARRAY[]::text[] END) AS flags,
       CASE WHEN c.value IS NULL THEN {_lit(NO_CONCEPT)} END AS null_reason,
       {_lit(items.version)} AS rule_version
FROM fiscal y CROSS JOIN (VALUES {codes}) AS i(line_item, kind)
LEFT JOIN chosen c ON c.company_key = y.company_key AND c.fiscal_year = y.fiscal_year AND c.line_item = i.line_item
ORDER BY y.company_key, i.line_item, y.fiscal_year"""


def build(silver_engine, sink, ids, items: LineItems | None = None) -> dict:
    """Run the query on silver and land its rows in `company_line_item` through the writer."""
    from sqlalchemy import text

    from edgar_warehouse.silver_writer.writer import land

    items = items or load()
    with silver_engine.connect() as conn:
        rows = [dict(r._mapping) for r in conn.execute(text(query(items)))]
    return land(sink, "company_line_item", rows, ids)
