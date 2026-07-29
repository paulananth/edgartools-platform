# Define ERDP-05-04-Equivalent Promotion Criteria for the F1–F12 Coverage-Matrix Products

Type: grilling
Status: resolved
Blocked by:

## Question

The `erdp-coverage-promotion` wayfinder map (`.scratch/erdp-coverage-promotion/`, DESTINATION REACHED 2026-07-27) defined a product-ready, all-critical-requirements Partial→Covered promotion checklist for the four new Explore products (`ERDP-05-04`: `CONSENSUS_ESTIMATES`, `GUIDANCE_FACTS`, `EARNINGS_CALENDAR`, `TRANSCRIPT_EVENTS`). Confirmed with the user (2026-07-27): the same rigor should later apply to the twelve pre-existing coverage-matrix footnote products (F1–F12 in `.scratch/er-data-plane/coverage-matrix.md` — identity/ticker-CIK, filings metadata, filing/research text, historical financials, earnings 8-K GAAP snapshot, ownership/Form 4, 13F/holders, graph neighborhood, segment revenue, executive/management pay, accounting forensic scores, pure-SEC subject features), none of which currently have a defined Partial→Covered promotion checklist despite several already being marked Partial in the matrix and actively consumed by ER skills today.

Deliberately **not resolved by this ticket** — recorded as a required go-live dependency, not yet worked. When picked up: what is the complete, product-ready promotion checklist for each of the 12 F1–F12 products, following the same method as `erdp-coverage-promotion` tickets 03–06 (grounded in the real schema/code, cross-checked against what financial-services ER skills actually need per data class, adversarially stress-tested for what a naive checklist would miss)?

## Answer

**Scoping decision (2026-07-29): survey first, then graduate to 12 per-product satellite
tickets** — the same shape as `erdp-coverage-promotion`, where ticket 01 (a research ticket
surveying all 9 ER skills once) fed tickets 03–06 (one grilling ticket per product, each
resolved independently against the survey's findings).

**Why not resolve all 12 checklists directly in this ticket:** the F1–F12 products are
consumed far more broadly than any of the four `erdp-coverage-promotion` products — Identity
and Historical financials alone are needed by nearly every one of the 9 ER skills, versus 2–6
skills for each of `CONSENSUS_ESTIMATES`/`GUIDANCE_FACTS`/`EARNINGS_CALENDAR`/
`TRANSCRIPT_EVENTS`. Producing a checklist at the same depth as tickets 03–06 (grounded in
real schema/code, cross-checked per skill, adversarially stress-tested) for all 12 products in
one sitting would blow the ~100K-token per-ticket budget this map's tickets are sized to, and
would likely produce shallower, less-grounded criteria than the precedent this ticket is
explicitly asked to match.

**This ticket resolves as a pure scoping decision, not a completed checklist.** It graduates
into:
- [Survey financial-services ER skill requirements per F1–F12 product](27-survey-er-skill-requirements-per-f1-f12-product.md)
  — research ticket, mirroring `erdp-coverage-promotion` ticket 01's method exactly but for
  the 12 legacy Gold/MDM products instead of the 4 new Explore products.
- Twelve new grilling tickets (28–39, one per F1–F12), each blocked by ticket 27, each asking
  "what is the complete, product-ready promotion checklist for this one product" in the same
  form as `erdp-coverage-promotion` tickets 03–06.

No product-specific criteria are decided here — that work is explicitly deferred to the
graduated tickets.
