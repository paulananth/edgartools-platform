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

Every rule here is **live**: built in silver (`company_fact`, `company_line_item`,
`company_measure`) and proved by the cohort proof, which the operator
accepted (operator: "yes"). The proof ran the installed
commands over 368 filers once, with its final checks: every filed line item equal
to a fact of its filing, every measure's inputs stored line items, no empty value
without a reason, the hand-checked answer key equal. A rule changed after that
proof is live only once its own change is proved
([mdm-engineering](../mdm-engineering/SKILL.md), "Choose the cheapest proof").

## Hard stops

| Never | Instead |
|---|---|
| Propose a financials rule from the captured data alone | Read research 02 (`.scratch/company-financials/research/02-vendor-standards.md` in the repository) first and follow the outside standard unless the operator rules otherwise (operator: "again use standards from external vendors keep this reserch handy for other decssions") |
| Key a year on the filing's `fy` or `fp` | Key it on the period's end date (below) |
| Overwrite a figure when a later filing restates it | Keep every filed copy; the latest is the default (below) |
| Fill a missing year from a nearby year | Null, with its reason |
| Send a request to the SEC or a data provider | Captured files only; a new request needs the operator's permission for that request |
| Type a financial column `integer`, `int`, `float`, `double` or `real`, in a silver spec, dbt, Python or the engine, or read a filed figure as a float | A whole number (CIK, year, window, count) is `bigint`; a figure, ratio or measure is a big decimal (`decimal(38,10)`, Python `Decimal`, exact text from the engine: `big_numbers: text` and `decimals: text`, or a JSON reader with `parse_float=str`). No float anywhere between the filed text and the stored value, even where no captured figure loses a digit today (operator: "For financial projects never use integer's use only bigint or big decimal", "Big decimal", "Fix the data type issue") |

## The time model (decided)

- **Every filed copy is kept; the latest is the default** (operator: "Keep all,
  latest by default (Recommended)"). Silver keeps each filed figure, as of its
  period (start, end) and as at its filing (filed date, accession number). Measures use
  the latest-filed copy, which keeps per-share series consistent across a stock
  split; the first-reported figure can be read back from the kept copies.
- **A year is keyed on the period's end date** (operator: "Period end, 364–371
  days (Recommended)"), by Compustat's FYEAR (operator: "Compustat
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
  year (operator: "The reported year (Recommended)"). When both or
  neither are reported, the later one (the new year end). A window that needs a
  year with no annual period gives null with the reason "fiscal year changed",
  and a missing figure in a year that has one gives "missing year".

Evidence and sources: `.scratch/company-financials/research/02-vendor-standards.md`, section 1.

## Standard line items (decided)

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
  concept and accession number are recorded beside the value.
- **Computed fallbacks** (the standard's impute rules: net income = `ProfitLoss`
  − NCI net income; parent equity = equity including NCI − `MinorityInterest`;
  gross profit = revenue − cost of revenue; liabilities from liabilities and
  equity; total debt from its parts) only where research 01 lists them, each
  value flagged "computed".
- **Revenue keeps the standard order** (`Revenues` first), with a data-quality
  rule that flags a period where the chosen revenue is smaller than another
  revenue total filed for it (another unflagged concept of its list, same
  unit: never an industry kind), for a steward (operator: "Standard order + a
  quality check (Recommended)"). Never a silent switch to the larger total.
- **A missing line item** is empty, with the reason "no concept filed", and
  counted per line item.
- **The line items are an RDM code set** (operator: "Yes, code set +
  crosswalk (Recommended)"): `financial-line-items`, 23 codes with label,
  definition and period (duration or instant), crosswalked to the `us-gaap`,
  `ifrs-full` and `dei` concepts each tries (a computed value's terms stay in
  the map). The rules file `rules/sources/sec.company-facts/line-items.yaml`
  names those codes and holds the order, the flags and the fallbacks; a test
  holds the two equal. The taxonomies are not loaded into RDM, and a
  concept's label and description stay out of silver: the same text on every
  fact of the concept is reference data, never a row field, and no analysis
  needs it (operator: "keep financial so that is it easy to
  calculate cgar and other analytics do not complecate too much"). Analyses
  read the line items (labelled by the code set) and the measures.
- **The map is rules configuration** (operator: "Rules configuration
  (Recommended)"): a reviewed YAML file under `rules/` names each line item, its
  concepts in order, any computed fallback and its flag. One SQL query,
  generated from it, builds `company_line_item` from silver's `company_fact`,
  and the silver writer lands the rows (operator: "SQL over silver
  (Recommended)", after the engine path proved to need a whole group and join
  language): `edgar_warehouse/financials/line_items.py`, run by
  `edgar-warehouse silver line-items`. On Snowflake the same query becomes a
  dbt model. It runs as steps, each a temporary table PostgreSQL has counted
  (`statements()`): as one statement the planner guessed hundreds of rows for
  millions and never finished; as steps the cohort builds in
  seconds. Never test its speed under `count(*)`, which skips the select list.
- **A cover-page figure is read from the year's own annual report, at its own
  date** (operator: "Annual report's cover (Recommended)"): the
  shares-outstanding fallback takes the cover-page count filed in the annual
  report covering that year, flagged "cover-page date", its date in `inputs`
  (`as_of: report` in the map, on a balance line item only); never a copy dated
  on the year end from another filing. An amended annual report, filed later,
  wins; one filing no annual facts (a Part III amendment) covers no year, so its
  cover count is not read.
- **A concept of another taxonomy than the year's is named with its taxonomy**
  (`dei:EntityCommonStockSharesOutstanding`), since the row's `taxonomy` is
  the year's.
- **Ties the rulings leave open** (measured on the cohort): an
  annual report filing as many facts for two annual periods covers the later
  as its own year; one filed copy in two units keeps the unit its filing uses
  most (its reporting currency), then the unit's text. The query and the answer
  key break them alike.
- Figures in the reporting currency with its ISO code (below).

Evidence and sources: `.scratch/company-financials/research/02-vendor-standards.md`, section 2.

## Measures (decided)

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
  balance is missing, as the beginning form is (operator: 'Null,
  "missing year" (Recommended)').
- **ROIC's tax rate** is income tax over pretax income; when pretax income is
  zero or negative, or that rate falls outside 0–100%, it is the statutory rate
  of the filer's country, from RDM's `corporate-tax-rates` (OECD; operator: "Statutory rate (new source)", "RDM, OECD source (Recommended)"). The country is the filer's place of incorporation through the
  pinned `sec-place-codes` ISO crosswalk (a subdivision such as US-PA reads as
  its country); the rate is the child code whose year holds the fiscal year's
  end, the combined central and sub-central rate, divided by 100.
- **Definitions** as research 01 section 4 gives them: ROIC after tax on debt +
  equity − cash; FCF = operating cash flow − capital expenditure; per-share on
  the latest-filed series.
- **Proved** per measure and per null reason against the hand-computed answer key
  (`.scratch/company-financials/answer-key/`).
- **Built as SQL over the line items**: `measures.yaml` names each
  ratio, return and growth series; `company_measure` is rebuilt whole from
  `company_line_item`, and reads `company_fact` only to find a year that holds
  two annual periods.
- **One list of null reasons**, the same in the spec, the code and the answer
  key: no concept filed, missing year, fiscal year changed, mixed currencies,
  denominator zero or negative, not meaningful (growth from or to zero or less),
  not meaningful for financial services, statement format unknown, no country
  of incorporation, no statutory rate for the country and year. A measure
  checks the format first, then a missing input, then mixed currencies, then
  its denominator. A computed input (free cash flow, invested capital) whose parts
  are in two currencies is missing with the reason "mixed currencies", never
  "no concept filed". A new reason is added to all three at once.
- **The statement format and country come from the Company master**, read in
  Python and passed to the SQL as rows (MDM and silver are separate databases).
  A filer with no Company master has no format: a measure that depends on it is
  null, "statement format unknown"; every other measure is computed.
- **Work a growth rate at 40 places**: PostgreSQL's `ln` and `exp` keep about
  16 digits by default, which misses the tenth decimal on a large rate (one in
  the 368-company cohort). Compare with an answer key rounded once, as silver
  stores it: a key rounded to 12 places and then to 10 moves the last digit.

Evidence and sources: `.scratch/company-financials/research/02-vendor-standards.md`, section 3.

## Reading company facts (decided)

- **Configured reading only** (operator: "configure only"): a
  source-extract contract, no Python custom step. It is
  `rules/sources/sec.company-facts/facts.yaml`. Its `company_fact`
  table gives one row per filed fact through the engine's generic `nest`
  iteration (operator: "Engine step, local
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
- **A concept with no facts** lands and flattens to nothing.
- **A number beyond exact 64-bit** is kept as exact text: declare
  `big_numbers: text` on the `units` value (operator: "Exact big
  numbers in the reader"). Never round it; without the option the file is
  refused (`value_number_range`). With it, all 368 captured files read.
- **Every decimal figure is a big decimal**: declare `decimals: text` on the
  `units` value too, so a figure with a decimal point reaches
  silver as its exact filed digits, never through a float (operator: "For financial projects never use integer's use only bigint or
  big decimal", "Big decimal"). No decimal figure captured loses a
  digit through a float today; the rule holds anyway.

## Currencies, IFRS and industry formats (decided)

- **Reporting currency with its ISO code beside each figure** (operator:
  "Reporting currency + code (Recommended)"); never convert. A measure whose
  inputs mix currencies is null with the reason "mixed currencies". USD
  conversion needs an exchange-rate source: a new provider, its own ticket.
- **IFRS mapped into the same 19 line items** (operator: "Map into same items
  (Recommended)"): an ordered `ifrs-full` list beside each `us-gaap` list in
  the rules YAML; a filer is read from the taxonomy it files in. The lists are
  research 04 (`.scratch/company-financials/research/04-ifrs-concept-lists.md`;
  operator: "Approve the lists (Recommended)"): IFRS taxonomy
  elements, first present wins; operating income empty where a filer presents
  none (IAS 1 defines none); lease liabilities never added to total debt; the
  taxonomy read period by period, since a filer can move between the two.
- **One item set, flagged by kind** (operator: "Same items, flagged by kind
  (Recommended)"): a value from an industry concept carries its kind (bank,
  insurer, REIT, utility). Each filer has a format, industrial or financial
  services, from its SIC code (6000–6199, 6300–6411 are financial services),
  as Compustat keeps `INDL` and `FS`. A measure meaningless for financial
  services (gross margin, ROIC, total debt and its ratios, and the current
  ratio, since a bank presents its balance sheet by liquidity; operator: "The four, plus current ratio (Recommended)") is null with the
  reason "not meaningful for financial services". Operating margin follows its
  inputs.

## Silver tables and their review (decided)

- **Three tables**: `company_fact` (every filed fact, append, keyed on the
  measured eight columns), `company_line_item` and `company_measure` (built from
  the facts by SQL, rebuilt whole each run). `company_line_item` holds one row per company, line item and
  fiscal year, the latest copy, so CAGR is a plain join on `fiscal_year`; every
  filed copy stays in `company_fact` (one system of record).
- **Review every ruling before a spec or a build**: each ruling in this skill
  reaches the spec, the reader, the line items and the answer key. A review
  once found a spec waiting on
  too few rulings, a build still offering a custom step, an answer key without
  the IFRS, financial-services, mixed-currency and changed-year-end cases.
- **The statement format is read from Company, never copied onto a row**: it
  comes from the Company master's SIC code, and is "unknown" until Company is
  mastered.

## Running the facts through Bookkeeping

`sec.company-facts` has one Bookkeeping target, `silver`: `facts` (`source.read`,
filers' files in slices of at most 8 MiB), `land` (`silver.land`: the reading's
`company_fact` table into silver, once per filer file), `line_items` and
`measures` (`silver.derive`: each derived table rebuilt whole), and `processed`
(`journal.record`). The Change Journal skips a file recorded under the same
rules and content, and a changed facts, line-item or measure rule is a new
processing identity. A run with no changed file does not start. A run that has
one rebuilds both derived tables for every company: both are snapshots, and the
writer removes any row a delivery lacks, so a delivery of some companies would
remove the rest. Rebuilding only the changed companies needs a writer that
replaces by partition (`company_key`); that is not built.

## RDM code sets and their sources

Reloaded from `rules/reference/published/` by `scripts/dev/reload_rdm.py`; the words of each are in
`WORDS` there.

| Code set | Source | Ticket |
|---|---|---|
| `financial-line-items` | internal: the line-item map `rules/sources/sec.company-facts/line-items.yaml` and company-financials research 01 | 46 |
| `corporate-tax-rates` | OECD Corporate Tax Statistics, dataflow `OECD.CTP.TPS` `DSD_TAX_CIT@DF_CIT` 2.0 (combined central and sub-central statutory rate) | 133 |
| `sec-sic-codes` | the SEC's company submissions: 407 SIC codes, each with its one description; `0000` kept invalid | 129 |
