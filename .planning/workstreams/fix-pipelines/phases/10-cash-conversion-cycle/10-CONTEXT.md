# Phase 3: Cash Conversion Cycle - Context

**Gathered:** 2026-07-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Consumers can query Days Sales Outstanding (DSO), Days Inventory Outstanding (DIO), and
Days Payable Outstanding (DPO) from `FINANCIAL_FACTORS`. DSO ships unconditionally (zero
new silver fields — `accounts_receivable`/`revenue` already exist). DIO/DPO ship
conditionally, requiring two new silver parser fields (`cost_of_revenue`,
`accounts_payable`) extracted from the already-fetched `companyfacts` JSON — no new
loader, no new SEC fetch path. Coverage research (03-RESEARCH.md, live-measured against
the SEC XBRL Frames API) is treated as sufficient to unblock DIO/DPO build (see D-01
below) — this phase is NOT a "build only if a future spike passes" gate; the spike
already ran and passed under the framing decided here.

</domain>

<decisions>
## Implementation Decisions

### Coverage threshold (CCC-02)
- **D-01:** "Acceptable coverage" for CCC-02 purposes is measured as % of
  economically-applicable filers, not % of all filers. Research measured
  `CostOfGoodsAndServicesSold`/`CostOfRevenue` (COGS-family) coverage at 51.5% of a broad
  filer proxy and 63.3% of revenue-tag reporters — this passes the bar. The 27.5%
  all-three-combined number (COGS-family ∩ AccountsPayable ∩ Inventory across ALL filers)
  is explicitly NOT the deciding denominator — it reflects structural inapplicability
  (banks/insurers/REITs/SaaS genuinely have no COGS/inventory line), not a tagging-quality
  gap, matching the "Not Meaningful" (NM) convention used by Bloomberg/FactSet for
  sector-inapplicable ratios and this platform's own already-shipped `gross_margin`
  precedent (Phase 2) — null for the same population, never flagged as a coverage failure.
  **Operational implication for the planner:** no SIC-code/industry filter needs to be
  built to enforce this threshold at query time — null propagation through
  `days_outstanding()` (null when `cost_of_revenue`/`accounts_payable` is null) already
  IS the "applicable population" mechanism. The threshold decision here is a one-time
  go/no-go for whether to build DIO/DPO at all, not a runtime filter.
- Result of D-01: CCC-01/CCC-02 evidence is satisfied for DIO/DPO — they are NOT declared
  out of scope. Document the accepted 51-63% coverage rate (and the reasoning above) as
  the CCC-02 evidence in REQUIREMENTS.md when this phase's plan updates it.

### DSO/DIO/DPO bundling
- **D-02:** Split delivery, not all-or-nothing. DSO ships in its own plan (Wave 1),
  independent of the DIO/DPO coverage decision — it never touches `cost_of_revenue` or
  `accounts_payable`, so CCC-02's gate condition (scoped to `cost_of_revenue` extraction)
  does not literally apply to it. DIO/DPO ship in a separate plan (Wave 2, depends on
  Wave 1's `days_outstanding()` macro), now unblocked per D-01. Both ship within this same
  Phase 3 — D-01 already resolved the coverage question as acceptable, so there is no
  reason to defer DIO/DPO to a future phase. Mirrors this milestone's existing pattern of
  independently-shippable execution plans (Phase 1's 01-01/01-02 wave split; Phase 2
  shipping ahead of Phase 1 per ROADMAP's "Suggested order").

### Factor priority
- **D-03:** DSO gets priority and the heaviest verification investment, consistent with
  D-02's Wave 1 placement. Rationale: DSO is the only one of the three universal across
  all industries (applies to any company with credit sales, regardless of inventory/COGS
  applicability) and doubles as a standalone earnings-quality/fraud signal via the Beneish
  M-Score's DSRI component (`current DSO / prior DSO > 1.1` flags aggressive revenue
  recognition) — a use case DIO/DPO don't carry with comparable standardization. DIO/DPO
  remain valuable but are correctly sequenced second (Wave 2), both for risk reasons
  (D-02) and because their relevance is industry-conditional rather than universal.

### Scope completeness (research finding, not a new decision)
- **D-04:** REQUIREMENTS.md's CCC-01 text mentions only `cost_of_revenue` as the new
  silver field, but DPO also requires `accounts_payable` (not currently parsed anywhere
  in this codebase — confirmed via full grep in 03-RESEARCH.md). This is a scope-gap fix,
  not scope creep: `accounts_payable` is a parser field extracted from the same
  already-fetched `companyfacts` JSON, consistent with the milestone's "no new loader"
  constraint (REQUIREMENTS.md's own non-negotiable constraint explicitly allows this kind
  of addition). The planner should treat `accounts_payable` as an in-scope second silver
  field alongside `cost_of_revenue`, both following the identical 9-touchpoint pattern
  documented in 03-RESEARCH.md Pattern 1.

### Claude's Discretion
- Exact `_COST_OF_REVENUE_CONCEPTS`/`_ACCOUNTS_PAYABLE_CONCEPTS` fallback-list contents
  beyond the live-verified primary concepts (`CostOfGoodsAndServicesSold`, `CostOfRevenue`,
  `AccountsPayableCurrent`) — 03-RESEARCH.md's Assumptions Log A2/A3 flag secondary tags as
  unverified; the planner/executor may verify via one more Frames API call or proceed with
  the documented fallback list as a starting point.
- Whether DSO/DIO/DPO share one execution plan with two waves, or are two separate plans —
  an implementation-pattern decision, not a vision-level one, mirroring Phase 1's approach.
- Ending-balance-only (not average-of-beginning-and-ending) formula convention for
  DSO/DIO/DPO — 03-RESEARCH.md's Alternatives Considered already recommends this,
  consistent with the existing ROA/ROE precedent; not re-litigated here as it wasn't
  raised as a discussion area.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Research and requirements (this phase)
- `.planning/workstreams/fundamental-factors-v2/phases/03-cash-conversion-cycle/03-RESEARCH.md` — full coverage measurement (live SEC XBRL Frames API data), 9-touchpoint parser-addition checklist (Pattern 1), `days_outstanding()` macro design (Pattern 2), Pitfalls 1-3, Assumptions Log, Open Questions (both resolved by this discussion — see Decisions above).
- `.planning/workstreams/fundamental-factors-v2/REQUIREMENTS.md` — CCC-01, CCC-02 requirement text; milestone-wide "no new loader" constraint.
- `.planning/workstreams/fundamental-factors-v2/ROADMAP.md` — Phase 3 goal and success criteria; "Research Evidence" section with prior `_GROSS_PROFIT_CONCEPTS` parser-pattern findings.
- `.planning/workstreams/fundamental-factors-v2/STATE.md` — the live Phase 1/2 blocker (`SEC_FINANCIAL_DERIVED` source-schema drift in dev Snowflake) this phase's Terraform column addition is at direct risk of repeating (03-RESEARCH.md Pitfall 1).

### Existing code patterns to follow
- `edgar_warehouse/parsers/financials_derived.py` — `_GROSS_PROFIT_CONCEPTS` (single-concept) and `_REVENUE_CONCEPTS` (multi-concept fallback list) patterns; the exact template for `_COST_OF_REVENUE_CONCEPTS`/`_ACCOUNTS_PAYABLE_CONCEPTS`.
- `edgar_warehouse/silver_store.py` — `sec_financial_derived` DDL, `_SEC_FINANCIAL_DERIVED_FACTOR_COLUMNS` migration dict, `merge_financial_derived()` staging/INSERT/UPDATE column lists (4 separate places per 03-RESEARCH.md Pattern 1).
- `edgar_warehouse/serving/gold_models.py` — `_SEC_FINANCIAL_DERIVED_SCHEMA` PyArrow schema + `_build_sec_financial_derived()` SELECT list.
- `infra/terraform/snowflake/modules/native_pull/main.tf` — `SEC_FINANCIAL_DERIVED` table column list; requires explicit `terraform apply` + `SHOW COLUMNS` verification per Pitfall 1.
- `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio.sql`, `cagr.sql` — structural macro convention `days_outstanding()` should follow.
- `infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql`, `gold.yml`, `_financial_factors_unit_tests.yml` — the model/docs/tests this phase extends, same files Phase 1/2 already touched.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `accounts_receivable`, `revenue`, `inventory` — already parsed silver/gold columns; DSO and DIO's balance-side inputs need zero new parsing.
- `safe_ratio.sql`/`cagr.sql` macro convention — `days_outstanding(balance_col, flow_col, days=365)` macro (03-RESEARCH.md Pattern 2) follows the identical null-guard shape.

### Established Patterns
- Every new derived silver field in this codebase touches 9 files/resources across 3 layers (Python parser → DuckDB → PyArrow export → Terraform → 2 dbt models → gold.yml → 2 dbt test fixtures → Python unit test) — 03-RESEARCH.md Pattern 1 has the full checklist with line numbers.
- The Terraform/native-pull layer is the most likely place for silent drift (confirmed by the live, currently-unresolved Phase 1/2 `current_assets` blocker) — an explicit `SHOW COLUMNS` verification task is required, not assumed as a side effect of the Terraform edit.

### Integration Points
- New DSO/DIO/DPO columns are added to the existing `financial_factors.sql` model — no new model file, matching Phase 1/2's approach.
- `cost_of_revenue`/`accounts_payable` are new columns on the existing `sec_financial_derived`/`financial_derived` chain, not a new table.

</code_context>

<specifics>
## Specific Ideas

No specific UI/display requirements — backend gold-model change only, consumed by
dbt/Snowflake clients (same as Phase 1/2).

</specifics>

<deferred>
## Deferred Ideas

- **SIC-code-based "applicable population" filter** — considered during the coverage
  threshold discussion as a way to formally define "economically applicable" but rejected
  as unnecessary: null propagation through the `days_outstanding()` macro (null when
  `cost_of_revenue`/`accounts_payable` is null) already achieves the same effect without
  needing industry classification data this codebase doesn't currently have.
- **Average-of-beginning-and-ending-balance DSO/DIO/DPO formula** — the textbook variant;
  03-RESEARCH.md's Alternatives Considered recommends ending-balance-only for consistency
  with the existing ROA/ROE precedent. Not re-opened in this discussion (wasn't selected
  as a discussion area); left as Claude's Discretion per Decisions above, but flagged here
  in case a future phase wants to revisit for cross-CCC-factor methodology consistency.

</deferred>

---

*Phase: 03-cash-conversion-cycle*
*Context gathered: 2026-07-01*
