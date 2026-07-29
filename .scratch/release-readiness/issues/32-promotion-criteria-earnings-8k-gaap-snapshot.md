# 32 — Product-ready promotion criteria for Earnings 8-K GAAP snapshot (F5)

Type: grilling
Status: open
Blocked by: 42

## Question

What is the complete, product-ready set of acceptance criteria that must all pass before the
Earnings 8-K GAAP snapshot is promoted from Partial to Covered in the coverage matrix? Concrete
platform surface per the matrix footnote: gold `EARNINGS_RELEASE`/`fact_earnings_release`
(`revenue_gaap`, `net_income_gaap`, `eps_gaap_diluted`, FY/FQ, period_end, filing_date; flags
`has_non_gaap`, `has_guidance` only). Matrix note: "GAAP flash only; non-GAAP **values** and
guidance **values** are Gaps (ERDP-02 family)" — this ticket must NOT scope-creep into
non-GAAP/guidance values promotion, which is already covered by the separate, resolved
`erdp-coverage-promotion` ERDP-02 (`GUIDANCE_FACTS`) checklist.

Write this as a numbered list of criteria (coverage breadth vs. reporting-window CIKs, GAAP
figure correctness/reconciliation against `SEC_FINANCIAL_DERIVED`, flag accuracy for
`has_non_gaap`/`has_guidance`, freshness relative to 8-K filing timestamp), each with a
concrete, checkable acceptance query or procedure, following the exact method and rigor of
`erdp-coverage-promotion` tickets 03–06 — grounded in real schema/code, cross-checked against
ticket 27's ER-skill survey findings for this product, adversarially stress-tested for what a
naive checklist would miss.

## Answer

(pending)
