# Phase 2: Profitability And Returns Factors - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-30
**Phase:** 02-profitability-and-returns-factors
**Areas discussed:** Negative equity handling (ROE), Period scope for new factors, ROIC trust vs re-derivation

---

## Scope creep redirected: valuation factors

User's initial area selection included "valuation factors" alongside the 3 presented
gray areas. This is explicitly out of scope per `REQUIREMENTS.md`'s "Out of Scope"
section (market-derived factors deferred to the held `model-builder-contract-gaps`
Phase 5 charter decision). Redirected and captured under Deferred Ideas in CONTEXT.md
rather than expanding Phase 2 scope.

---

## Negative equity handling (ROE)

| Option | Description | Selected |
|--------|-------------|----------|
| Null when total_equity < 0 | Treat negative-equity ROE as undefined, matching safe_ratio() pattern with extra sign check | ✓ |
| Compute as-is, no special handling | Plain safe_ratio(), consumers handle negative-equity cases themselves | |
| Compute but add a separate flag column | Compute raw ratio + boolean flag column | |

**User's choice:** Requested research before deciding ("research and take what MIT recommendation").

**Research performed:** Web search for Damodaran (NYU Stern) guidance on negative book equity and ROE. Finding: ROE is "meaningless" under negative book equity (negative/negative produces a misleadingly positive value); ~10% of companies in Damodaran's sample have negative book equity; recommended treatment is to null/exclude and fall back to ROA. Sources: pages.stern.nyu.edu/~adamodar/pdfiles/papers/returnmeasures.pdf, aswathdamodaran.substack.com/p/good-bad-banks-good-bad-investments.

**Final decision (after research presented):** Null when total_equity < 0 (Option 1), confirmed by user as research-backed standard practice.

**Notes:** Only ROE gets the sign-check guard. Gross/operating/net margin and ROA use plain `safe_ratio()` — revenue and total_assets aren't expected to go negative the way equity can via buybacks/accumulated losses.

---

## Period scope for new factors

| Option | Description | Selected |
|--------|-------------|----------|
| All periods, FY and quarterly | Compute for every fiscal_period — margins/returns are meaningful at any cadence | ✓ |
| FY only, matching asset_growth_yoy | Keep consistent with the one existing growth factor's FY-only scope | |

**User's choice:** All periods, FY and quarterly.

**Notes:** The existing `asset_growth_yoy` factor's FY restriction exists because YoY growth needs a full prior year for a clean comparison. That constraint doesn't apply to single-period margin/return factors, so restricting them to FY-only would just silently drop quarterly data without a real reason.

---

## ROIC trust vs re-derivation

| Option | Description | Selected |
|--------|-------------|----------|
| Surface as-is, document the simplification | Phase 2 stays pure-SQL; add column description noting simplified pre-tax ROIC; defer textbook re-derivation | ✓ |
| Re-derive with the textbook formula now | Expand Phase 2 to add tax-rate parsing and proper NOPAT-based ROIC | |

**User's choice:** Requested research before deciding ("Revisit, use the textbook and MIT as references, use COT to validate before finalizing").

**Research performed:** Web search for textbook ROIC formula. Finding: ROIC = NOPAT (EBIT × (1 − tax rate)) / Average Invested Capital. Checked codebase for the tax-rate input via grep of `financials_derived.py` — no `income_tax_expense` or effective-tax-rate field parsed anywhere. The existing `roic` column's code comment (`financials_derived.py:279`) already documents the current formula as a deliberate simplification (`EBIT / (Equity + Debt)`, no tax adjustment), not an oversight.

**Final decision (after research presented):** Surface as-is, document the gap (Option 1). Re-deriving textbook ROIC requires adding a new parsed field — a silver-layer change that exceeds Phase 2's "pure SQL, zero parser changes" scope (Phase 2 success criterion #5). Captured as a deferred idea for a future phase/requirement.

---

## Claude's Discretion

- Exact dbt column naming for new factors — follow `financial_factors.sql`'s existing convention (no `_pct` suffix on ratio columns).
- Whether ROA needs a comparable negative-denominator guard to ROE — decided no: negative total_assets is not a realistic accounting scenario (unlike negative equity via buybacks), so plain `safe_ratio()` suffices.

## Deferred Ideas

- Valuation/market-derived factors (P/E, EV/EBITDA) — out of scope, tracked under `model-builder-contract-gaps` Phase 5 charter decision.
- Textbook NOPAT-based ROIC re-derivation — needs a new `income_tax_expense` silver field; candidate for a future phase in this workstream.
