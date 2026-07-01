# Phase 3: Cash Conversion Cycle - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-01
**Phase:** 03-cash-conversion-cycle
**Areas discussed:** Coverage threshold (CCC-02), DSO/DIO/DPO bundling, Factor prioritization by customer value (user-added, freeform)

---

## Coverage threshold (CCC-02)

Research-backed comparison via `gsd-advisor-researcher` (calibration tier: minimal_decisive).

| Option | Description | Selected |
|--------|-------------|----------|
| % of economically-applicable filers | 51.5-63.3% coverage. Matches Bloomberg/FactSet's "Not Meaningful" convention for sector-inapplicable ratios, and this platform's own `gross_margin` precedent. | ✓ |
| % of ALL filers | 27.5% combined coverage. Simpler denominator but penalizes structural inapplicability (banks/insurers/SaaS genuinely lack COGS) the same way as a real data-quality gap. | |

**User's choice:** % of economically-applicable filers (Recommended option accepted)
**Notes:** Result — DIO/DPO are NOT declared out of scope. Recorded as D-01 in CONTEXT.md, including the operational note that no SIC-code filter needs to be built; null propagation through `days_outstanding()` already achieves the "applicable population" effect.

---

## DSO/DIO/DPO bundling

Research-backed comparison via `gsd-advisor-researcher`.

| Option | Description | Selected |
|--------|-------------|----------|
| Split — DSO ships now | DSO needs zero new fields, ships immediately. DIO/DPO ship conditionally once the coverage threshold above is met. Matches this milestone's existing pattern of independent phase delivery. | ✓ |
| All-or-nothing | Hold DSO until DIO/DPO's coverage question resolves. Simpler single go/no-go, but delays a zero-risk, already-buildable factor behind an unrelated coverage judgment. | |

**User's choice:** Split — DSO ships now (Recommended option accepted)
**Notes:** Recorded as D-02 in CONTEXT.md. DSO → Wave 1 (no new fields). DIO/DPO → Wave 2, depends on Wave 1's `days_outstanding()` macro, now unblocked per the coverage-threshold decision. Both ship within Phase 3 — no deferral to a future phase.

---

## Factor prioritization by customer value (user-added, freeform "Other" response)

Research-backed comparison via `gsd-advisor-researcher`.

| Option | Description | Selected |
|--------|-------------|----------|
| DSO first | Universal across all industries, doubles as an earnings-quality/fraud signal (Beneish M-Score DSRI component), zero new data needed. | ✓ |
| Equal priority across all three | Treat DSO/DIO/DPO as equally important, invest verification effort evenly once all are buildable. | |

**User's choice:** DSO first (Recommended option accepted)
**Notes:** Recorded as D-03 in CONTEXT.md. Consistent with D-02's Wave 1 placement — DSO gets first build slot and heaviest verification investment.

---

## Claude's Discretion

- Exact `_COST_OF_REVENUE_CONCEPTS`/`_ACCOUNTS_PAYABLE_CONCEPTS` fallback-list contents beyond the live-verified primary concepts.
- Whether DSO/DIO/DPO share one execution plan with two waves, or are two separate plans.
- Ending-balance-only vs average-of-beginning-and-ending-balance formula convention (not raised as a discussion area; 03-RESEARCH.md's existing recommendation stands).

## Scope-completeness note (not a discussed gray area, surfaced by research)

`accounts_payable` — needed for DPO, not currently parsed anywhere in the codebase, not
mentioned in REQUIREMENTS.md's CCC-01 text. Recorded as D-04 in CONTEXT.md: treated as an
in-scope scope-gap fix (parser field addition, consistent with the "no new loader"
constraint), not scope creep requiring a separate discussion.

## Deferred Ideas

- **SIC-code-based "applicable population" filter** — considered during the coverage
  threshold discussion, rejected as unnecessary (null propagation already achieves the
  same effect).
- **Average-of-beginning-and-ending-balance DSO/DIO/DPO formula** — the textbook variant;
  left as Claude's Discretion per 03-RESEARCH.md's existing recommendation, flagged for a
  possible future cross-factor methodology review.
