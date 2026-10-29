"""The fundamental measures (ticket 47): `rules/sources/sec.company-facts/measures.yaml`
read once, and the SQL that builds silver's `company_measure` from the line items in
`company_line_item` (ticket 46: "CAGR and the measures are SQL on top").

One row per company, measure, fiscal year and window, for every fiscal year the
line items hold: a value, or empty with its reason. Each filer's statement format
(Compustat's industrial or financial services, from its SIC) and country (from its
place of incorporation) are read from its Company master and passed in as rows.
The rulings are `skills/company-financials/SKILL.md`, "Measures"; the answer key
(ticket 44) checks the result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from edgar_warehouse.control_contract import Blocked

from . import line_items, sql
from .sql import lit

ROOT = Path(__file__).resolve().parents[2]
DEFINITIONS = ROOT / "rules" / "sources" / "sec.company-facts" / "measures.yaml"
FORMS = ("average", "beginning")
# Values a measure reads that are not line items: computed per year below.
DERIVED = {"fcf", "operating_income_after_tax", "invested_capital"}
COMPANY_SOURCE = "sec.submissions.company.v1"
NO_CONCEPT = line_items.NO_CONCEPT
MIXED = "mixed currencies"
FINANCIAL_SERVICES = "financial services"
_NAME = re.compile(r"[a-z][a-z0-9_]{0,59}")


@dataclass(frozen=True)
class Measures:
    version: str
    not_for_financial_services: frozenset[str]
    ratios: dict[str, tuple[str, str]]  # measure -> (numerator, denominator)
    returns: dict[str, tuple[str, str]]  # base -> (the year's return, the balance)
    series: tuple[str, ...]
    windows: tuple[int, ...]

    def names(self) -> set[str]:
        return set(self.ratios) | {f"{base}_{form}" for base in self.returns for form in FORMS} | {
            f"{name}_cagr" for name in self.series}


def _pair(raw, allowed: set[str], what: str) -> tuple[str, str]:
    if not (isinstance(raw, list) and len(raw) == 2 and all(r in allowed for r in raw)):
        raise Blocked(f"{what} is two of the line items or {sorted(DERIVED)}: {raw!r}")
    return raw[0], raw[1]


def parse(body: dict, codes: set[str]) -> Measures:
    """The definitions, checked whole: every input a line item or a derived value."""
    allowed = codes | DERIVED
    for name in [*body.get("ratios", {}), *body.get("returns", {})]:
        if not _NAME.fullmatch(name):
            raise Blocked(f"a measure's name is lower-case words: {name!r}")
    ratios = {name: _pair(raw, allowed, name) for name, raw in body["ratios"].items()}
    returns = {name: _pair(raw, allowed, name) for name, raw in body["returns"].items()}
    growth = body["growth"]
    if not set(growth["series"]) <= allowed:
        raise Blocked(f"growth reads line items: {sorted(set(growth['series']) - allowed)}")
    if not all(isinstance(n, int) and n > 0 for n in growth["windows"]):
        raise Blocked("a growth window is a whole number of years")
    measures = Measures(line_items.words(body["version"]), frozenset(body["not_for_financial_services"]),
                        ratios, returns, tuple(growth["series"]), tuple(growth["windows"]))
    # A growth rate divides a series by itself, so the statement format never makes it meaningless.
    one_year = measures.names() - {f"{name}_cagr" for name in measures.series}
    if not measures.not_for_financial_services <= one_year:
        raise Blocked(f"not a ratio or return: {sorted(measures.not_for_financial_services - one_year)}")
    return measures


def load(path: Path = DEFINITIONS) -> Measures:
    import yaml

    return parse(yaml.safe_load(path.read_text()), set(line_items.load().period))


# --- each filer's format and country, from its Company master ------------------------

def financial_services(sic: str | None) -> bool:
    """Ticket 42: SIC 6000-6199 and 6300-6411, as Compustat keeps `FS`."""
    return bool(sic and sic.isdigit() and (6000 <= int(sic) <= 6199 or 6300 <= int(sic) <= 6411))


def _countries() -> dict[str, str]:
    """Each SEC place code's ISO country, a subdivision (US-PA) read as its country."""
    found = {}
    for row in line_items.published("sec-place-codes", "1"):
        for to_set, _, code, match in row.get("crosswalk", []):
            if to_set == "iso-3166" and match == "exact":
                found[row["code"]] = code.split("-")[0]
    return found


def filers(companies: dict[str, tuple[str | None, str | None]]) -> dict[str, tuple[str, str | None]]:
    """Each company's statement format and country, from its SIC and place of
    incorporation. A company left out has no Company master: its format is unknown."""
    countries = _countries()
    return {key: (FINANCIAL_SERVICES if financial_services(sic) else "industrial", countries.get(place or ""))
            for key, (sic, place) in companies.items()}


def from_company(mdm_engine, keys: set[str]) -> dict[str, tuple[str | None, str | None]]:
    """Each company's SIC and place of incorporation, read from its Company master;
    a key with no master is left out."""
    from edgar_warehouse.mdm.clean.consumer import ContractReader
    from edgar_warehouse.silver_writer.writer import MdmIds

    masters = {k: v for k, v in MdmIds(mdm_engine)(COMPANY_SOURCE, "company", keys).items() if v}
    reader, out = ContractReader(mdm_engine), {}
    for key, master in masters.items():
        fields = reader.entity(master)["identity"].get("fields", {})
        out[key] = tuple((fields.get(name) or {}).get("value") or None for name in ("sic", "state_of_incorporation"))
    return out


def _rates(countries: set[str]) -> list[tuple]:
    """The statutory rate of each country and year, as a fraction (RDM corporate-tax-rates)."""
    rows = []
    for row in line_items.published("corporate-tax-rates", "1"):
        if row.get("value") is not None and row["code"].split(":")[0] in countries:
            rows.append((lit(row["code"].split(":")[0]), f"{lit(row['valid_from'])}::date",
                         f"{lit(row['valid_to'])}::date", f"{lit(row['value'])}::numeric / 100"))
    return rows


# --- the query -------------------------------------------------------------------

def query(measures: Measures, formats: dict, lines: str = "silver.company_line_item",
          facts: str = "silver.company_fact") -> str:
    """One SQL statement (PostgreSQL), giving every row of `company_measure`."""
    return sql.query(*_steps(measures, formats, lines, facts))


def statements(measures: Measures, formats: dict, lines: str = "silver.company_line_item",
               facts: str = "silver.company_fact") -> list[str]:
    return sql.counted(*_steps(measures, formats, lines, facts))


def _part(alias: str) -> str:
    """One figure's trace: its value, concept and filing."""
    return (f"jsonb_strip_nulls(jsonb_build_object('value', {alias}.value::text, 'concept', {alias}.concept, "
            f"'accession', {alias}.accession))")


def _input(alias: str) -> str:
    """One input's trace: its fiscal year and its figure, or the parts it was computed from."""
    return (f"jsonb_strip_nulls(jsonb_build_object('fiscal_year', {alias}.fiscal_year, 'value', {alias}.value::text, "
            f"'concept', {alias}.concept, 'accession', {alias}.accession)) || COALESCE({alias}.detail, '{{}}'::jsonb)")


def _item(alias: str, name: str, year: str = "y") -> str:
    return (f"LEFT JOIN item {alias} ON {alias}.company_key = {year}.company_key "
            f"AND {alias}.fiscal_year = {year}.fiscal_year AND {alias}.line_item = {lit(name)}")


def _flag(name: str, not_fs: frozenset[str]) -> str:
    return "true" if name in not_fs else "false"


def _format_reason(not_fs: str = "m.not_fs", fmt: str = "f.format") -> str:
    """The first null reason of a measure that depends on the statement format (ticket 42); a filer
    with no Company master has no format ("unknown until Company is mastered", skill, ticket 43)."""
    return f"""WHEN {not_fs} AND {fmt} = {lit(FINANCIAL_SERVICES)} THEN 'not meaningful for financial services'
              WHEN {not_fs} AND {fmt} IS NULL THEN 'statement format unknown'"""


def _steps(measures: Measures, formats: dict, lines: str, facts: str) -> tuple[list[tuple[str, str]], str]:
    for table in (lines, facts):
        if not re.fullmatch(r"[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)?", table):
            raise Blocked(f"the measures read a table name: {table!r}")
    not_fs = measures.not_for_financial_services
    windows = sorted(set(measures.windows) | {1})
    ctes = [
        ("filer", sql.values("company_key, format, country",
                             [(lit(k), lit(fmt), lit(country)) for k, (fmt, country) in sorted(formats.items())],
                             "NULL::text, NULL::text, NULL::text")),
        ("rate", sql.values("country, valid_from, valid_to, rate",
                            _rates({c for _, c in formats.values() if c}),
                            "NULL::text, NULL::date, NULL::date, NULL::numeric")),
        ("ratio_def", sql.values("measure, top, bottom, not_fs",
                                 [(lit(n), lit(t), lit(b), _flag(n, not_fs)) for n, (t, b) in measures.ratios.items()],
                                 "NULL::text, NULL::text, NULL::text, false")),
        ("return_def", sql.values("measure, form, top, balance, not_fs",
                                  [(lit(f"{n}_{form}"), lit(form), lit(t), lit(b), _flag(f"{n}_{form}", not_fs))
                                   for n, (t, b) in measures.returns.items() for form in FORMS],
                                  "NULL::text, NULL::text, NULL::text, NULL::text, false")),
        ("growth_def", sql.values("measure, series, window_years",
                                  [(lit(f"{s}_cagr"), lit(s), f"{n}::bigint")
                                   for s in measures.series for n in measures.windows],
                                  "NULL::text, NULL::text, 0::bigint")),
        # A value with a reason is an input that could not be computed (mixed currencies, no tax rate).
        ("item", f"""
  SELECT company_key, fiscal_year, line_item, value, currency, concept, accession, NULL::text AS reason,
         NULL::jsonb AS detail
  FROM {lines}"""),
        # Each fiscal year once, at its end.
        ("fiscal", f"""SELECT company_key, fiscal_year, max(period_end) AS period_end FROM {lines} GROUP BY 1, 2"""),
        # Free cash flow: operating cash flow less capital expenditure, in one currency (non-GAAP).
        ("fcf", f"""
  SELECT y.company_key, y.fiscal_year, 'fcf' AS line_item,
         CASE WHEN o.currency IS NOT DISTINCT FROM c.currency THEN o.value - c.value END AS value,
         o.currency, 'computed' AS concept, NULL::text AS accession,
         CASE WHEN o.value IS NOT NULL AND c.value IS NOT NULL
                   AND o.currency IS DISTINCT FROM c.currency THEN {lit(MIXED)} END AS reason,
         jsonb_build_object('ocf', {_part("o")}, 'capex', {_part("c")}) AS detail
  FROM fiscal y {_item("o", "ocf")} {_item("c", "capex")}"""),
        # ROIC's tax rate: income tax over pretax income, else the country's statutory rate in force at the
        # year's end (ticket 39; RDM corporate-tax-rates, ticket 133).
        ("taxed", f"""
  SELECT y.company_key, y.fiscal_year, y.period_end, oi.value AS oi, oi.currency, f.country,
         {_part("oi")} AS oi_part, {_part("pre")} AS pre_part, {_part("tax")} AS tax_part,
         oi.value IS NULL OR pre.value IS NULL OR tax.value IS NULL AS missing,
         CASE WHEN pre.value > 0 THEN CASE WHEN tax.value / pre.value BETWEEN 0 AND 1
                                         THEN tax.value / pre.value END END AS own_rate
  FROM fiscal y LEFT JOIN filer f ON f.company_key = y.company_key
  {_item("oi", "operating_income")} {_item("pre", "pretax_income")} {_item("tax", "income_tax")}"""),
        ("operating_income_after_tax", f"""
  SELECT company_key, fiscal_year, line_item, CASE WHEN reason IS NULL THEN value END AS value, currency,
         concept, accession, reason, detail
  FROM (
    SELECT t.company_key, t.fiscal_year, 'operating_income_after_tax' AS line_item,
           t.oi * (1 - COALESCE(t.own_rate, r.rate)) AS value, t.currency, 'computed' AS concept,
           NULL::text AS accession,
           CASE WHEN t.missing THEN {lit(NO_CONCEPT)}
                WHEN t.own_rate IS NULL AND t.country IS NULL THEN 'no country of incorporation'
                WHEN t.own_rate IS NULL AND r.rate IS NULL THEN 'no statutory rate for the country and year'
           END AS reason,
           jsonb_strip_nulls(jsonb_build_object('operating_income', t.oi_part, 'pretax_income', t.pre_part,
               'income_tax', t.tax_part, 'tax_rate', COALESCE(t.own_rate, r.rate)::text,
               'rate_source', CASE WHEN t.own_rate IS NOT NULL THEN 'filed'
                                   WHEN r.rate IS NOT NULL THEN 'statutory: ' || t.country END)) AS detail
    FROM taxed t
    LEFT JOIN rate r ON r.country = t.country AND t.period_end BETWEEN r.valid_from AND r.valid_to) a"""),
        # Invested capital: debt + equity - cash, the three in one currency.
        ("invested_capital", f"""
  SELECT y.company_key, y.fiscal_year, 'invested_capital' AS line_item,
         CASE WHEN d.currency IS NOT DISTINCT FROM e.currency AND e.currency IS NOT DISTINCT FROM c.currency
              THEN d.value + e.value - c.value END AS value,
         e.currency, 'computed' AS concept, NULL::text AS accession,
         CASE WHEN d.value IS NOT NULL AND e.value IS NOT NULL AND c.value IS NOT NULL
                   AND (d.currency IS DISTINCT FROM e.currency OR e.currency IS DISTINCT FROM c.currency)
              THEN {lit(MIXED)} END AS reason,
         jsonb_build_object('total_debt', {_part("d")}, 'book_value', {_part("e")}, 'cash', {_part("c")}) AS detail
  FROM fiscal y {_item("d", "total_debt")} {_item("e", "book_value")} {_item("c", "cash")}"""),
        ("series", """
  SELECT * FROM item UNION ALL SELECT * FROM fcf
  UNION ALL SELECT * FROM operating_income_after_tax UNION ALL SELECT * FROM invested_capital"""),
        # A fiscal year that holds two annual periods (the year end moved; ticket 35).
        ("two_ends", f"""
  SELECT company_key, fiscal_year FROM (
    SELECT DISTINCT company_key, period_end, {sql.fiscal_year("period_end")} AS fiscal_year
    FROM {facts}
    WHERE taxonomy IN ('us-gaap', 'ifrs-full') AND period_start IS NOT NULL
      AND {sql.annual("period_start", "period_end")}) a
  GROUP BY company_key, fiscal_year HAVING count(*) > 1"""),
        # Why an earlier year a measure needs has no figure: a year with an annual period is "missing
        # year"; a year with none is "fiscal year changed" when the year end moved around the gap (the
        # month a year ends in, a 52/53-week drift into early January read as December), else "missing year".
        ("gap", f"""
  SELECT c.company_key, c.prior,
         CASE WHEN p.fiscal_year IS NOT NULL OR lo.fiscal_year IS NULL OR hi.fiscal_year IS NULL THEN 'missing year'
              WHEN extract(month FROM lo.period_end - 7) <> extract(month FROM hi.period_end - 7)
                OR EXISTS (SELECT 1 FROM two_ends t WHERE t.company_key = c.company_key
                           AND t.fiscal_year BETWEEN lo.fiscal_year AND hi.fiscal_year) THEN 'fiscal year changed'
              ELSE 'missing year' END AS reason
  FROM (SELECT DISTINCT y.company_key, y.fiscal_year - n.n AS prior
        FROM fiscal y CROSS JOIN (VALUES {", ".join(f"({n}::bigint)" for n in windows)}) AS n(n)) c
  LEFT JOIN fiscal p ON p.company_key = c.company_key AND p.fiscal_year = c.prior
  LEFT JOIN LATERAL (SELECT fiscal_year, period_end FROM fiscal WHERE company_key = c.company_key
                     AND fiscal_year < c.prior ORDER BY fiscal_year DESC LIMIT 1) lo ON true
  LEFT JOIN LATERAL (SELECT fiscal_year, period_end FROM fiscal WHERE company_key = c.company_key
                     AND fiscal_year > c.prior ORDER BY fiscal_year LIMIT 1) hi ON true"""),
        # One year's numerator over its denominator. Each null reason in order: the format, a missing
        # input (its own reason, if it could not be computed), mixed currencies, the denominator. A figure
        # with no currency (a share count) is never mixed, as the answer key reads it.
        ("ratio", f"""
  SELECT y.company_key, m.measure, y.fiscal_year, 1::bigint AS window_years,
         CASE {_format_reason()}
              WHEN t.value IS NULL THEN COALESCE(t.reason, {lit(NO_CONCEPT)})
              WHEN b.value IS NULL THEN COALESCE(b.reason, {lit(NO_CONCEPT)})
              WHEN t.currency <> b.currency THEN {lit(MIXED)}
              WHEN b.value <= 0 THEN 'denominator zero or negative' END AS null_reason,
         CASE WHEN b.value > 0 THEN t.value / b.value END AS value,
         CASE WHEN b.currency IS NULL THEN t.currency END AS currency,
         jsonb_build_object(m.top, {_input("t")}, m.bottom, {_input("b")}) AS inputs
  FROM fiscal y CROSS JOIN ratio_def m
  LEFT JOIN filer f ON f.company_key = y.company_key
  LEFT JOIN series t ON t.company_key = y.company_key AND t.fiscal_year = y.fiscal_year AND t.line_item = m.top
  LEFT JOIN series b ON b.company_key = y.company_key AND b.fiscal_year = y.fiscal_year AND b.line_item = m.bottom"""),
        # A return on the average of the year's and the prior year's balance, or on the prior year's.
        ("returned", f"""
  SELECT company_key, measure, fiscal_year, 1::bigint AS window_years,
         CASE {_format_reason("not_fs", "format")}
              WHEN top IS NULL THEN COALESCE(top_reason, {lit(NO_CONCEPT)})
              WHEN balance IS NULL THEN COALESCE(balance_reason, {lit(NO_CONCEPT)})
              WHEN prior_balance IS NULL THEN COALESCE(prior_reason, gap_reason)
              WHEN currencies > 1 THEN {lit(MIXED)}
              WHEN bottom <= 0 THEN 'denominator zero or negative' END AS null_reason,
         CASE WHEN bottom > 0 THEN top / bottom END AS value, NULL::text AS currency, inputs
  FROM (
    SELECT y.company_key, m.measure, y.fiscal_year, m.not_fs, f.format,
           t.value AS top, t.reason AS top_reason, n.value AS balance, n.reason AS balance_reason,
           p.value AS prior_balance, p.reason AS prior_reason, g.reason AS gap_reason,
           CASE WHEN m.form = 'average' THEN (n.value + p.value) / 2 ELSE p.value END AS bottom,
           (SELECT count(DISTINCT c) FROM (VALUES (t.currency), (n.currency), (p.currency)) v(c)) AS currencies,
           jsonb_build_object('return', {_input("t")}, 'balance', {_input("n")}, 'prior_balance', {_input("p")})
               AS inputs
    FROM fiscal y CROSS JOIN return_def m
    LEFT JOIN filer f ON f.company_key = y.company_key
    LEFT JOIN series t ON t.company_key = y.company_key AND t.fiscal_year = y.fiscal_year AND t.line_item = m.top
    LEFT JOIN series n ON n.company_key = y.company_key AND n.fiscal_year = y.fiscal_year
                      AND n.line_item = m.balance
    LEFT JOIN series p ON p.company_key = y.company_key AND p.fiscal_year = y.fiscal_year - 1
                      AND p.line_item = m.balance
    LEFT JOIN gap g ON g.company_key = y.company_key AND g.prior = y.fiscal_year - 1) m"""),
        # Compound annual growth over exactly `window_years` years: (end / start)^(1/n) - 1. Worked at 40
        # places: at its default, PostgreSQL keeps about 16 digits, short of 10 places on a large rate.
        ("growth", f"""
  SELECT y.company_key, m.measure, y.fiscal_year, m.window_years,
         CASE WHEN e.value IS NULL THEN COALESCE(e.reason, {lit(NO_CONCEPT)})
              WHEN s.value IS NULL THEN COALESCE(s.reason, g.reason)
              WHEN s.currency <> e.currency THEN {lit(MIXED)}
              WHEN s.value <= 0 OR e.value <= 0 THEN 'not meaningful' END AS null_reason,
         CASE WHEN s.value > 0 AND e.value > 0
              THEN exp(ln(round(e.value, 40) / s.value) / m.window_years) - 1 END AS value,
         NULL::text AS currency,
         jsonb_build_object('start', {_input("s")}, 'end', {_input("e")}) AS inputs
  FROM fiscal y CROSS JOIN growth_def m
  LEFT JOIN series e ON e.company_key = y.company_key AND e.fiscal_year = y.fiscal_year AND e.line_item = m.series
  LEFT JOIN series s ON s.company_key = y.company_key AND s.fiscal_year = y.fiscal_year - m.window_years
                    AND s.line_item = m.series
  LEFT JOIN gap g ON g.company_key = y.company_key AND g.prior = y.fiscal_year - m.window_years"""),
    ]
    return ctes, f"""SELECT company_key, measure, fiscal_year, window_years,
       CASE WHEN null_reason IS NULL THEN round(value, 10) END AS value,
       CASE WHEN null_reason IS NULL THEN currency END AS currency, null_reason, inputs,
       {lit(measures.version)} AS definition_version
FROM (SELECT * FROM ratio UNION ALL SELECT * FROM returned UNION ALL SELECT * FROM growth) m
ORDER BY company_key, measure, fiscal_year, window_years"""


def build(silver_engine, sink, ids, companies, measures: Measures | None = None) -> dict:
    """Run the query on silver and land its rows in `company_measure` through the writer.
    `companies` gives each company key's SIC and place of incorporation (`from_company`)."""
    from sqlalchemy import text

    from edgar_warehouse.silver_writer.writer import land

    measures = measures or load()
    with silver_engine.connect() as conn:
        keys = set(conn.scalars(text("SELECT DISTINCT company_key FROM silver.company_line_item")))
    formats = filers(companies(keys))
    with silver_engine.connect() as conn, conn.begin():
        *steps, final = statements(measures, formats)
        for step in steps:
            conn.execute(text(step))
        rows = [dict(r._mapping) for r in conn.execute(text(final))]
    return land(sink, "company_measure", rows, ids)
