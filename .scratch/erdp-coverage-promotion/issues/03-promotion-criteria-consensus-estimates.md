# 03 — Product-ready promotion criteria for CONSENSUS_ESTIMATES (ERDP-01)

Type: grilling
Status: resolved
Blocked by: 01

## Question

What is the complete, product-ready set of acceptance criteria that must all pass before `CONSENSUS_ESTIMATES` is promoted from Partial to Covered in the coverage matrix — covering not just "does at least one row exist" but every critical requirement surfaced by ticket 01's skill survey (coverage breadth across the tracked universe, freshness/`as_of` recency, source reliability and disclosure per earnings-preview's "always note the source and date" caveat, no fabricated/placeholder rows reaching Gold, correct join to `COMPANY`/`TICKER_REFERENCE`, and any others the survey turns up)? Write this as the `ERDP-05-04` promotion-checklist entry for this product: a numbered list of criteria, each with a concrete, checkable acceptance query or procedure.

## Answer

Grounded in the real schema (`_FACT_CONSENSUS_ESTIMATE_SCHEMA`, `gold_schemas.yaml`), the real `SOURCE_SYSTEMS` enum and ingest functions (`edgar_warehouse/explore/consensus_estimates.py`), and ticket 01's ER-skill findings. Every criterion below must pass; several were tightened after an adversarial pass surfaced that a naive version would not have caught tonight's own incident (a hand-inserted fabricated row).

1. **Universe coverage — ≥50%.** ≥50% of the Decision Subject Universe (tracked/active CIKs) has ≥1 row for both `metric=revenue` and `metric=eps_diluted` at the latest completed-or-upcoming fiscal quarter.
   `SELECT COUNT(DISTINCT cik) FILTER (WHERE has_revenue AND has_eps) * 1.0 / (SELECT COUNT(*) FROM <tracked/active universe>) >= 0.50`

2. **Pre-earnings freshness, trailing 4 fiscal quarters.** For every CIK that reported in the trailing 4 fiscal quarters (not a hand-picked sample), the `CONSENSUS_ESTIMATES` row closest to that print has `as_of < filing_date` (joined against `EARNINGS_RELEASES`/`EARNINGS_CALENDAR`). A post-print-only consensus for any CIK in the window fails this criterion (earnings-analysis's named failure mode — ticket 01 §1).

3. **Source scope restricted to free, implemented sources.** `source_system ∈ {yahoo, firm_manual}` only. Any row with `source_system ∈ {fmp, finnhub, estimize, factset, bloomberg, cap_iq}` disqualifies that row from the promoted set — no ingest code produces these today (`consensus_estimates.py` has only `fetch_yahoo_consensus_estimates` and `load_firm_manual_csv`/`load_firm_manual_records`), so such a row is either fabricated or a not-yet-eligible future integration, either way not promotion-eligible.

4. **Yahoo rows: format-verified authenticity.** For every `source_system='yahoo'` row, `source_ref` matches `^yahoo:[^:]+:(0q|\+1q|0y|\+1y):(avg|low|high|numberOfAnalysts)$` exactly — the deterministic format `parse_yahoo_consensus_estimate` actually emits (`consensus_estimates.py:351`). A row that doesn't match this string shape could not have come from the real fetch path, full stop.

5. **firm_manual rows: reviewable-artifact provenance.** Since `firm_manual`'s `source_ref` is free-form (no format to verify), every promoted `firm_manual` row must trace to a checked-in, git-reviewed CSV file under version control — not a bare ad-hoc `INSERT`/`MERGE`/manual SQL row with no corresponding file. This is the procedural analog for the one source where a format proof isn't possible.

6. **Grain coherence.** For a given `(cik, fiscal_year, fiscal_quarter, as_of)`, the `revenue` and `eps_diluted` rows share the same `source_system` — not silently mixed vintages from two different sources.

7. **Join integrity, identity-checked.** 100% of promoted rows join to `COMPANY`/`TICKER_REFERENCE` on `cik`; spot-check a sample against `entity_name` agreement (not just a non-null join success) to catch ticker collisions/reused tickers.

8. **Explore-only labeling re-affirmed.** Consumer-facing docs/dashboard clearly mark `CONSENSUS_ESTIMATES` as Explore, not Agent-Grade (ADR 0001 / ERDP-06-02) — a re-confirmation gate, not new work.

**Explicitly not required for promotion** (per ticket 01, no ER skill needs it): a trailing history of consensus values (every skill wants only the current/NTM figure); segment-level metrics beyond revenue/eps_diluted (earnings-preview's "nice to have," not gating).

**Known residual risk, not closable by any acceptance query:** criteria 2 and 4 can only be proven *retrospectively*, against quarters that have already reported. For a not-yet-reported quarter, "will this consensus row be genuinely pre-earnings and accurate" is not something any SQL check can verify in advance — promotion status reflects demonstrated historical reliability, not a guarantee about the next print.
