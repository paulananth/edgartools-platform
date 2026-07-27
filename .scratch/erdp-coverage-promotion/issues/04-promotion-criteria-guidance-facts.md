# 04 — Product-ready promotion criteria for GUIDANCE_FACTS (ERDP-02)

Type: grilling
Status: resolved
Blocked by: 01

## Question

What is the complete, product-ready set of acceptance criteria that must all pass before `GUIDANCE_FACTS` is promoted from Partial to Covered — covering every critical requirement surfaced by ticket 01's skill survey, plus the open question already on record: the one real production run (Apple, `bootstrap-fundamentals`) yielded 0 `rows_earnings_release`, so 8-K may not reliably be the right primary source for guidance extraction. This ticket must either resolve that source-reliability question as part of the criteria (e.g. a minimum measured yield rate against a sample of known-guidance-issuing 8-Ks before promotion is even considered) or explicitly state it as a blocking criterion that can't be satisfied yet. Write this as the `ERDP-05-04` promotion-checklist entry for this product: a numbered list of criteria, each with a concrete, checkable acceptance query or procedure.

## Answer

Grounded in `_FACT_GUIDANCE_SCHEMA` (`gold_schemas.yaml`), `guidance_facts.py`, and `parsers/earnings_release.py`. Two findings from an adversarial code read reframed the ticket's own premise:

- **Apple's `rows_earnings_release: 0` is a more basic signal than "guidance extraction found nothing"** — it means zero `EARNINGS_RELEASES` rows were produced at all for any of the 30 parsed filings, i.e. the earnings-release parser itself likely never matched (a form-selection question), not that guidance extraction ran and came up empty. Diagnosing that specific run is an ops/build task outside this ticket's scope — but it means "8-K is not a reliable guidance source" was never actually established by the Apple run; that conclusion doesn't hold up.
- **`has_guidance` (`earnings_release.py:116-124`) and the guidance extractor (`guidance_facts.py:565-594`) both swallow *any* exception as "absent guidance"** (`except Exception: has_guidance = False` / `return []`). A real code bug (edgartools API shape change, malformed table) is indistinguishable from a legitimate "no guidance issued" at the data layer — no SQL acceptance query can tell them apart after the fact. **Confirmed as a blocking prerequisite with the user**, not an accepted residual risk.

### Blocking prerequisite (must land before promotion is even evaluated)

0. **Fix exception-swallowing.** Both `except Exception: has_guidance = False` and the extractor's silent `return []` on exception must distinguish "confirmed absent" from "exception during access/parse" (e.g. log and count separately, or route to `sec_guidance_fact_reject` instead of silent drop). Criteria 2–3 below are unenforceable until this lands.

### Promotion criteria

1. **Grain floor** — `metric ∈ {revenue, eps_diluted}` supported at minimum (ERDP-02-07), re-verified live not just unit-tested.
2. **Explicit no-guidance is provable, not assumed** — for every `EARNINGS_RELEASES` row with `has_guidance = FALSE`, that is a *positive*, exception-free determination (guaranteed by prerequisite #0) — not silently indistinguishable from an extraction failure. Checkable post-fix via the exception counter/log added in #0.
3. **Extraction yield ≥ 90%** — of all `EARNINGS_RELEASES` rows with `has_guidance = TRUE`, ≥90% have ≥1 corresponding `GUIDANCE_FACTS` row for the same `accession_number`. The remaining ≤10% must land in `sec_guidance_fact_reject` with a `reject_reason` (quarantined, not silently dropped) — this is the concrete, measured replacement for "is 8-K a reliable source," resolving the ticket's open question via a yield bar instead of an unqualified reliability claim.
4. **Current + prior quarter both extractable (guide-vs-guide)** — for any CIK with guidance in two consecutive fiscal quarters, both quarters' `GUIDANCE_FACTS` rows exist (earnings-analysis's minimum: current-quarter AND immediately-prior, each independently dated/sourced — ticket 01 §2).
5. **Every published row has ≥1 of low/mid/high non-null** — already enforced in `normalize_guidance_row` (ERDP-02-06); re-verified live.
6. **SEC-8-K rows: format-verified authenticity** — for `source_system='sec_8k'`, `source_ref` matches `^sec_8k:[0-9]{10}-[0-9]{2}-[0-9]{6}:guidance:.+$` (the deterministic format `guidance_facts.py:557` actually emits), **and** the embedded `accession_number` joins to a real `FILING_DETAIL`/`EARNINGS_RELEASES` row. A row that doesn't match this, or whose accession doesn't exist, could not have come from the real extraction path.
7. **firm_manual rows: reviewable-artifact provenance** — same procedural analog as `CONSENSUS_ESTIMATES` (ticket 03 criterion 5): promoted `firm_manual` guidance must trace to a checked-in, git-reviewed CSV, not an ad-hoc row (`source_ref` here has no deterministic format to verify, per `guidance_facts.py:321-322` — it's passed through as-is).
8. **Prefer SEC-derived; firm_manual overrides coexist by key** — already enforced by natural key including `source_system` (ERDP-02-05); re-verified live.
9. **Join integrity, identity-checked** — 100% join to `COMPANY`/`TICKER_REFERENCE` on `cik`, spot-checked against `entity_name` (same pattern as ticket 03 criterion 7).
10. **Explore-only labeling re-affirmed** (ADR 0001 / ERDP-06-02).

**Explicitly not required** (per ticket 01, no ER skill needs it): universe-wide coverage — every consumer is per-request/single-company for this product, unlike `CONSENSUS_ESTIMATES`; segment-level guidance detail.

**Known residual risk, not closable by any acceptance query:** criterion 3's 90% yield bar is measured against *known* guidance tables (`has_guidance=TRUE`); it cannot detect a systematic false-negative in `has_guidance` itself beyond what prerequisite #0's exception-count makes visible (e.g. a guidance table shape edgartools exposes that neither `has_guidance` nor the extractor recognizes as a table at all). This mirrors ticket 03's residual-risk framing: promotion reflects demonstrated reliability on what the platform can currently detect, not a guarantee against unknown-unknowns in the underlying `edgartools` parsing surface.
