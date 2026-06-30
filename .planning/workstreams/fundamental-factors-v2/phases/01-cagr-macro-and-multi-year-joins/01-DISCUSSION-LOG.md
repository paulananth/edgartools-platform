# Phase 1: CAGR Macro And Multi-Year Joins - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-30
**Phase:** 01-cagr-macro-and-multi-year-joins
**Areas discussed:** Quarterly scope clarification, Negative-to-negative CAGR, Fiscal-year matching tolerance

---

## Quarterly scope clarification

User's initial area selection included a custom option: "5 year window, with quarterly
projections." This was ambiguous — could mean (a) just clarifying quarterly rows are
excluded, or (b) adding a genuine new quarterly-cadence growth/projection capability.
Asked for disambiguation; user requested research against textbook/market documentation
before deciding ("check MIT and textbook and market documentation to decide").

**Research performed:** Web search confirmed the textbook formula for annualizing
quarterly growth exists (CAGR with exponent n=4 for quarters). A second, more targeted
search specifically on revenue/earnings fundamentals (not generic investment returns)
found that annualizing QoQ growth is an explicitly named industry pitfall — seasonality
makes it volatile/misleading for many businesses; practitioner consensus reserves it for
narrow short-run capacity-planning contexts with explicit "annualized" labeling, not
general-purpose fundamentals datasets. Sources: daloopa.com/blog/analyst-best-practices/
yoy-vs-qoq, wallstreetprep.com/knowledge/cagr-compound-annual-growth-rate.

| Option | Description | Selected |
|--------|-------------|----------|
| FY-only CAGR, as already scoped | Keep ROADMAP.md's original scope exactly | ✓ |
| Add quarterly-annualized growth anyway, clearly labeled | Expand scope, add n=4 exponent variant with seasonal-risk labeling | |

**User's choice:** FY-only CAGR, as already scoped (confirmed after research presented).

**Notes:** Quarterly-cadence growth captured as a deferred idea, not pursued further —
research showed it would need real seasonal-adjustment work to be responsible, a
substantially larger feature than this phase.

---

## Negative-to-negative CAGR

| Option | Description | Selected |
|--------|-------------|----------|
| Null on any negative endpoint | Both numerator and denominator must be strictly positive | ✓ |
| Compute it — negative/negative is mathematically valid | Only null on an actual sign change, per GROW-02's literal wording | |

**User's choice:** Null on any negative endpoint.

**Notes:** Directly parallels Phase 2's D-01 (ROE negative-equity null guard, Damodaran-
sourced) — a negative-to-negative CAGR (e.g. -100 → -50) is mathematically computable but
produces a misleadingly positive number for a still-unprofitable company. Same class of
problem, same resolution pattern.

---

## Fiscal-year matching tolerance

| Option | Description | Selected |
|--------|-------------|----------|
| Exact match only, no tolerance | fiscal_year - N must match exactly or CAGR nulls | ✓ |
| Accept ±1 year tolerance | Nearest available year within 1 year accepted for FY-end shifts | |

**User's choice:** Exact match only, no tolerance.

**Notes:** A fuzzy match would compute a CAGR over a non-N-year span while still labeling
it as an N-year CAGR — exactly the "incorrectly-spanning calculation" GROW-03 already
prohibits for the fiscal-year-gap case.

---

## Claude's Discretion

- Exact `cagr()` macro signature/parameter naming — follow `yoy_growth()`'s existing pattern.
- Whether 3yr/5yr CAGR share one parameterized CTE or use two separate CTEs — implementation detail, not vision-level.

## Deferred Ideas

- Quarterly-cadence annualized growth metric — researched and explicitly rejected for this phase (seasonality pitfall for revenue/earnings fundamentals); would need its own scope if ever revisited.
