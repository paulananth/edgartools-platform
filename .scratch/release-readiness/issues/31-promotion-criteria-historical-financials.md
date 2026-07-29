# 31 — Product-ready promotion criteria for Historical financials (F4)

Type: grilling
Status: open
Blocked by: 42

## Question

What is the complete, product-ready set of acceptance criteria that must all pass before
Historical financials is promoted from Partial to Covered in the coverage matrix? Concrete
platform surface per the matrix footnote: gold/export `SEC_FINANCIAL_DERIVED`/
`financial_derived` (revenue, GP, EBITDA, EBIT, NI, EPS, BS/CF, FCF, margins, ROIC/ROE/ROA,
shares); `SEC_FINANCIAL_FACT`/`financial_facts` (XBRL concept, unit, period, segment); Subject
Bundle `subject_features` (as-of pure-SEC vector, not full history). Matrix note: "Multi-year
history is gold tables; Bundle only exposes feature vector, not full history section yet."

Write this as a numbered list of criteria (coverage breadth, history depth per skill need,
derived-metric correctness/formula verification, XBRL fact/derived agreement, Bundle-vs-gold
scope boundary), each with a concrete, checkable acceptance query or procedure, following the
exact method and rigor of `erdp-coverage-promotion` tickets 03–06 — grounded in real
schema/code, cross-checked against ticket 27's ER-skill survey findings for this product
(likely the most broadly-needed of all 12 — nearly every ER skill touches financials),
adversarially stress-tested for what a naive checklist would miss.

## Answer

(pending)
