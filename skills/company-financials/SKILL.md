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

## The time model (ticket 35, decided 2026-10-21)

- **Every filed copy is kept; the latest is the default** (operator: "Keep all,
  latest by default (Recommended)"). Silver keeps each filed figure, as of its
  period (start, end) and as at its filing (filed date, accession). Measures use
  the latest-filed copy, which keeps per-share series consistent across a stock
  split; the first-reported figure can be read back from the kept copies.
- **A year is keyed on the period's end date** (operator: "Period end, 364–371
  days (Recommended)"). A figure belongs to the fiscal year whose end falls in
  calendar year Y. A period is annual when it is 364–371 days long. CAGR counts
  years, not days, so a 53-week year keeps its extra week.
- **A changed fiscal year end, Compustat-style** (operator: "Compustat-style,
  null if missing (Recommended)"). A transition period is kept as filed but is
  not a year. When two annual periods end in one calendar year, that year is the
  later one (the new year end). A window that needs a year with no annual period
  gives null with the reason "fiscal year changed".

Evidence and sources: ticket 35, research 02 section 1.

## Standard line items (ticket 38, decided 2026-10-21)

- **Nineteen line items**, as research 01 section 6 lists them
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
- **The map is rules configuration** (operator: "Rules configuration
  (Recommended)"): a reviewed YAML file under `rules/` names each line item, its
  concepts in order, any computed fallback and its flag; a configured step
  applies it. An operation the engine lacks is added as a generic engine
  primitive (build ticket 46).
- USD only, until ticket 42 (currencies and IFRS) rules otherwise.

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
- **Definitions** as research 01 section 4 gives them: ROIC after tax on debt +
  equity − cash; FCF = operating cash flow − capital expenditure; per-share on
  the latest-filed series.
- **Proved** per measure and per null reason against ticket 44's hand-computed
  answer key.

Evidence and sources: ticket 39, research 02 section 3.
