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
