# 36 — Product-ready promotion criteria for Segment / product-geo revenue (F9)

Priority: 52, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/release-readiness/issues/36-promotion-criteria-segment-revenue.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: grilling
Status: open
Blocked by: release-readiness 42

## Question

What is the complete, product-ready set of acceptance criteria that must all pass before
Segment/product-geo revenue is promoted from Partial to Covered in the coverage matrix?
Concrete platform surface per the matrix footnote: `SEC_FINANCIAL_FACT.segment` (raw XBRL
segment string on facts) only. Matrix note: "**No** curated product/geo revenue model mart;
initiation T2 still **Gap** for 20-30-row model." This is likely the second-hardest F1–F12
product to promote as-is (after F3, filing text) since the matrix explicitly says the curated
mart doesn't exist — the checklist may need to conclude "not promotable at the raw-segment
level; promotion requires the curated mart to be built first" rather than assume a raw XBRL
string can meet an ER skill's structured segment-table need.

Write this as a numbered list of criteria (or, if warranted, an explicit finding that
promotion is blocked on a prerequisite curated-mart build, with the mart's minimum viable
shape specified), grounded in real schema/code, cross-checked against ticket 27's ER-skill
survey findings for this product, adversarially stress-tested for what a naive checklist would
miss — following the method of `erdp-coverage-promotion` tickets 03–06.

## Answer

(pending)
