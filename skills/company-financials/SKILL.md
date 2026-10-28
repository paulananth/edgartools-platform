---
name: company-financials
description: The operator's rules for company financials - which reported figure silver keeps, how a fiscal year is keyed, how a changed year end is handled, how standard line items come from reported XBRL concepts, and how CAGR and the fundamental measures are defined. Use before changing how company facts are read, mapped to line items or turned into measures, or when answering what a financial figure means.
---

# Company Financials

> Part of the **data-platform** skill set. data-onboarding and refining-rules
> say *how* to change rules; this skill says *what* a company's financials
> must be. Every rule here is an operator ruling, dated; change one only on the
> operator's words, and record them here.

It answers: **which figure is a company's figure for a year, and how is each
measure computed from it?**

## Status of each rule

Every rule here is **decided**: ruled on a ticket of the rebuild map, not yet
built or proved. The cohort proof (ticket 48) makes them live; until then, do
not describe any of them as running.

## Hard stops

| Never | Instead |
|---|---|
| Propose a financials rule from the captured data alone | Read research 02 (`.scratch/company-financials/research/02-vendor-standards.md` in the repository) first and follow the outside standard unless the operator rules otherwise (operator, 2026-10-21: "again use standards from external vendors keep this reserch handy for other decssions") |
| Key a year on the filing's `fy` or `fp` | Key it on the period's end date (below) |
| Overwrite a figure when a later filing restates it | Keep every filed copy; the latest is the default (below) |
| Fill a missing year from a nearby year | Null, with its reason |
| Send a request to the SEC or a data provider | Captured files only; a new request needs the operator's permission for that request |
| Type a financial column `integer`, `int`, `float`, `double` or `real`, in a silver spec, dbt, Python or the engine, or read a filed figure as a float | A whole number (CIK, year, window, count) is `bigint`; a figure, ratio or measure is a big decimal (`decimal(38,10)`, Python `Decimal`, exact text from the engine: `big_numbers: text` and `decimals: text`, or a JSON reader with `parse_float=str`). No float anywhere between the filed text and the stored value, even where no captured figure loses a digit today (operator, 2026-10-22: "For financial projects never use integer's use only bigint or big decimal", "Big decimal", "Fix the data type issue") |

## The time model (ticket 35, decided 2026-10-21)

- **Every filed copy is kept; the latest is the default** (operator: "Keep all,
  latest by default (Recommended)"). Silver keeps each filed figure, as of its
  period (start, end) and as at its filing (filed date, accession). Measures use
  the latest-filed copy, which keeps per-share series consistent across a stock
  split; the first-reported figure can be read back from the kept copies.
- **A year is keyed on the period's end date** (operator: "Period end, 364–371
  days (Recommended)"), by Compustat's FYEAR (operator, 2026-10-22: "Compustat
  FYEAR (Recommended)"): a year ending June to December is that calendar year's,
  one ending January to May the previous year's, so a 52/53-week year ending on
  1-3 January stays in its year. A period is annual when it is 364–371 days long, counting
  its first and last day (`end − start + 1`): a 52-week year is 364 days, a
  53-week year 371. CAGR counts
  years, not days, so a 53-week year keeps its extra week.
- **A changed fiscal year end, Compustat-style** (operator: "Compustat-style,
  null if missing (Recommended)"). A transition period is kept as filed but is
  not a year. When two annual periods fall in one fiscal year, the year is the
  one an annual report (10-K, 20-F, 40-F) covers as its own fiscal year; a
  12-month period seen only as a later comparative is kept as filed but is not a
  year (operator, 2026-10-22: "The reported year (Recommended)"). When both or
  neither are reported, the later one (the new year end). A window that needs a
  year with no annual period gives null with the reason "fiscal year changed",
  and a missing figure in a year that has one gives "missing year".

Evidence and sources: ticket 35, research 02 section 1.

## Standard line items (ticket 38, decided 2026-10-21)

- **Nineteen groups, 23 line items** (current assets and liabilities, pretax
  income and income tax, and dividends paid, buybacks and dividends per share
  are each their own), as research 01 section 6 lists them
  (`.scratch/company-financials/research/01-measures-and-concepts.md`). Each is
  an ordered list of reported concepts. Where research 01's order differs from
  the Fundamental Accounting Concepts' Try Order, the standard's order wins:
  cost of revenue tries `CostOfRevenue` first, then `CostOfGoodsAndServicesSold`,
  `CostOfServices`, `CostOfGoodsSold`.
- **First present wins:** for each company and annual period, the first concept
  with a fact for that exact period, using the latest-filed copy. The chosen
  concept and accession are recorded beside the value.
- **Computed fallbacks** (the standard's impute rules: net income = `ProfitLoss`
  − NCI net income; parent equity = equity including NCI − `MinorityInterest`;
  gross profit = revenue − cost of revenue; liabilities from liabilities and
  equity; total debt from its parts) only where research 01 lists them, each
  value flagged "computed".
- **Revenue keeps the standard order** (`Revenues` first), with a data-quality
  rule that flags a period where the chosen revenue is smaller than another
  revenue total filed for it, for a steward (operator: "Standard order + a
  quality check (Recommended)"). Never a silent switch to the larger total.
- **A missing line item** is empty, with the reason "no concept filed", and
  counted per line item.
- **The line items are an RDM code set** (operator, 2026-10-22: "Yes, code set +
  crosswalk (Recommended)"): `financial-line-items`, 23 codes with label,
  definition and period (duration or instant), crosswalked to the `us-gaap`,
  `ifrs-full` and `dei` concepts each tries (a computed value's terms stay in
  the map). The rules file `rules/sources/sec.company-facts/line-items.yaml`
  names those codes and holds the order, the flags and the fallbacks; a test
  holds the two equal. The taxonomies are not loaded into RDM; a fact keeps its
  concept's label in silver.
- **The map is rules configuration** (operator: "Rules configuration
  (Recommended)"): a reviewed YAML file under `rules/` names each line item, its
  concepts in order, any computed fallback and its flag; a configured step
  applies it, locally, landing through the silver writer (operator, 2026-10-28:
  "Engine step, local (Recommended)"); not dbt. An operation the engine lacks
  is added as a generic engine primitive (build ticket 46).
- Figures in the reporting currency with its ISO code (ticket 42, below).

Evidence and sources: ticket 38, research 02 section 2.

## Measures (ticket 39, decided 2026-10-21)

- **Stored, built from silver** (operator: "Stored, built from silver
  (Recommended)"): one row per company, measure, fiscal year and window, naming
  its inputs and the definition's version; definitions are rules configuration;
  raw ratios, no truncation or smoothing.
- **Returns in both forms** (operator: "can we have both"): ROE, ROA and ROIC on
  the average of start and end balance (WRDS) and on the beginning balance
  (Damodaran), as two named measures. Null with a reason when a balance is
  missing or the denominator is zero or negative.
- **CAGR** over exactly 1, 3, 5 and 10 annual years (operator: "1, 3, 5 and 10
  years (Recommended)"). "Not meaningful" when the first or last value is zero
  or negative; null with "missing year" or "fiscal year changed" when an
  endpoint is missing.
- **An average balance needs both balances**: a return on the average balance
  is null, "missing year" (or "fiscal year changed"), when the prior year's
  balance is missing, as the beginning form is (operator, 2026-10-22: 'Null,
  "missing year" (Recommended)').
- **ROIC's tax rate** is income tax over pretax income; when pretax income is
  zero or negative, or that rate falls outside 0–100%, it is the statutory rate
  of the filer's country, from RDM's `corporate-tax-rates` (OECD; operator,
  2026-10-22: "Statutory rate (new source)", "RDM, OECD source (Recommended)";
  ticket 133). The country is the filer's place of incorporation through the
  pinned `sec-place-codes` ISO crosswalk (a subdivision such as US-PA reads as
  its country); the rate is the child code whose year holds the fiscal year's
  end, the combined central and sub-central rate, divided by 100.
- **Definitions** as research 01 section 4 gives them: ROIC after tax on debt +
  equity − cash; FCF = operating cash flow − capital expenditure; per-share on
  the latest-filed series.
- **Proved** per measure and per null reason against ticket 44's hand-computed
  answer key.

Evidence and sources: ticket 39, research 02 section 3.

## Reading company facts (ticket 40, decided 2026-10-22)

- **Configured reading only** (operator, 2026-10-22: "configure only"): a
  source-extract contract, no Python custom step. It is
  `rules/sources/sec.company-facts/facts.yaml` (ticket 45). Its `company_fact`
  table gives one row per filed fact through the engine's generic `nest`
  iteration (ticket 46; operator, 2026-10-28: "Engine step, local
  (Recommended)"), the rows silver's `company_fact` lands.
- **The filer's CIK is filed two ways**: a JSON number in some files, digit text
  (zero-padded) in others (262 and 105 of the cohort). `integer` reads both as
  one bigint; never key on its spelling.
- **Any other shape refuses the file, never drops it**: document assertions
  require facts, each taxonomy and each concept's `units` to be objects, and a
  CIK wherever there are facts. A filer with no facts (an empty object) lands
  nothing.
- **One table per taxonomy**, `each.entries` on `facts.<taxonomy>`: one row per
  concept with its key, and its `units` kept whole as one value (label and
  description). The facts themselves are `company_fact`'s rows, flattened by
  `nest`: taxonomy, concept and unit carried onto each fact.
- **A taxonomy with no table refuses the file**: a `taxonomies` table looks each
  key up in a frozen reference list with `on_missing: error`. Never drop one
  silently; add its table.
- **A concept with no facts** lands and flattens to nothing (119 of 138,987 in
  the cohort).
- **A number beyond exact 64-bit** is kept as exact text: declare
  `big_numbers: text` on the `units` value (ticket 128; operator: "Exact big
  numbers in the reader"). Never round it; without the option the file is
  refused (`value_number_range`). With it, all 368 captured files read.
- **Every decimal figure is a big decimal**: declare `decimals: text` on the
  `units` value too (ticket 134), so a figure with a decimal point reaches
  silver as its exact filed digits, never through a float (operator,
  2026-10-22: "For financial projects never use integer's use only bigint or
  big decimal", "Big decimal"). Of 323,634 decimal figures captured, none loses a
  digit through a float today; the rule holds anyway.

## Currencies, IFRS and industry formats (ticket 42, decided 2026-10-22)

- **Reporting currency with its ISO code beside each figure** (operator:
  "Reporting currency + code (Recommended)"); never convert. A measure whose
  inputs mix currencies is null with the reason "mixed currencies". USD
  conversion needs an exchange-rate source: a new provider, its own ticket.
- **IFRS mapped into the same 19 line items** (operator: "Map into same items
  (Recommended)"): an ordered `ifrs-full` list beside each `us-gaap` list in
  the rules YAML; a filer is read from the taxonomy it files in. The lists are
  research 04 (`.scratch/company-financials/research/04-ifrs-concept-lists.md`;
  operator, 2026-10-22: "Approve the lists (Recommended)"): IFRS taxonomy
  elements, first present wins; operating income empty where a filer presents
  none (IAS 1 defines none); lease liabilities never added to total debt; the
  taxonomy read period by period, since a filer can move between the two.
- **One item set, flagged by kind** (operator: "Same items, flagged by kind
  (Recommended)"): a value from an industry concept carries its kind (bank,
  insurer, REIT, utility). Each filer has a format, industrial or financial
  services, from its SIC code (6000–6199, 6300–6411 are financial services),
  as Compustat keeps `INDL` and `FS`. A measure meaningless for financial
  services (gross margin, ROIC, total debt and its ratios, and the current
  ratio, since a bank presents its balance sheet by liquidity; operator,
  2026-10-22: "The four, plus current ratio (Recommended)") is null with the
  reason "not meaningful for financial services". Operating margin follows its
  inputs.

## Silver tables and their review (ticket 43, decided 2026-10-22)

- **Three tables**: `company_fact` (every filed fact, append, keyed on the
  measured eight columns), `company_line_item` and `company_measure` (built from
  the facts by a configured engine step, rebuilt whole each run). The spec is on ticket 43.
- **Review the financials tickets before a spec or a build**: the rulings of 35,
  38, 39, 40, 42 and 128 each reach the spec, the reader (45), the line items
  (46) and the answer key (44). The review of 2026-10-22 found a spec waiting on
  too few tickets, a build still offering a custom step, an answer key without
  the IFRS, financial-services, mixed-currency and changed-year-end cases.
- **The statement format is "unknown" until Company is mastered**: it comes from
  the Company master's SIC code, and the local MDM has no Company yet (ticket 37).
