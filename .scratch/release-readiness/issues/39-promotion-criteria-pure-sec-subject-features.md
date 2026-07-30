# 39 — Product-ready promotion criteria for Pure-SEC subject features (F12)

Type: grilling
Status: resolved
Blocked by: 27

## Question

What is the complete, product-ready set of acceptance criteria that must all pass before
Pure-SEC subject features is promoted from Partial to Covered in the coverage matrix? Concrete
platform surface per the matrix footnote: Subject Feature Screen + Bundle `subject_features`
(FY + interim pure-SEC vectors; **no** price/PE/mcap per ADR 0001). Matrix note: "Idea/sector
multi-issuer screens; ERDP-06 keeps market joins out of this vector."

This product has a hard architectural boundary (ADR 0001: no market data in the pure-SEC
vector) that the checklist must explicitly preserve, not accidentally weaken while trying to
make the product feel more "complete" for ER skills that also want price/PE/mcap (those are
served by ERDP-07/F13, a separate, explicitly External/Explore product, not this one).

Write this as a numbered list of criteria (coverage breadth across the multi-issuer screen
universe, FY/interim vector completeness, ADR 0001 boundary re-affirmation as an explicit gate
— not just an assumption, feature freshness/as-of correctness), each with a concrete,
checkable acceptance query or procedure, following the exact method and rigor of
`erdp-coverage-promotion` tickets 03–06 — grounded in real schema/code, cross-checked against
ticket 27's ER-skill survey findings for this product, adversarially stress-tested for what a
naive checklist would miss.

## Answer

Grounded in `docs/subject-feature-screen.md`, `infra/snowflake/sql/decision_contract/
01_subject_feature_screen.sql`, and ticket 27's F12 survey findings. This product's situation is
the **inverse** of tickets 28-30's — the design and Python semantics are the most mature of any
F1-F12 product (ADR 0001's market-data boundary is explicit, coverage states are
present/empty/unavailable/not_applicable, watermark identity is built in) — but the Snowflake
artifact itself doesn't exist yet.

1. **A documented read path exists conceptually, but is not deployed — the actual gate here.**
   Checked live: `SHOW TABLES LIKE '%FEATURE%' IN SCHEMA EDGARTOOLS_GOLD` returns **nothing**.
   `01_subject_feature_screen.sql`'s own file is explicitly labeled a "view **sketch**" in
   `docs/subject-feature-screen.md`'s own code-layer table — the same "sketch, not deployed"
   language CLAUDE.md uses elsewhere for other unfinished Decision Contract SQL. The Python
   semantics (`edgar_warehouse/serving/subject_feature_screen.py`) are real and unit-tested per
   the doc, but there is no live Snowflake view or table an ER agent could query directly today.
   Acceptance: a real Snowflake object (view or table) implementing the documented contract
   exists in `EDGARTOOLS_GOLD` and is queryable — currently failing.

2. **Universe scope, exactly as already specified — do not weaken it.** The existing contract
   already states `Universe = warehouse active ∩ MDM active` (ticket 14's intersection) — this is
   the correct scope per ticket 27's survey (idea-generation/sector-overview both need
   cross-sectional, whole-universe/whole-peer-set breadth, not per-request lookup). No change
   needed to this definition; just confirm the deployed view actually implements the intersection,
   not a looser union.

3. **ADR 0001 boundary must be a re-affirmed, checkable gate — not an assumption.** Per this
   ticket's own framing: both consuming skills' own text (idea-generation, sector-overview) never
   distinguishes pure-SEC from market-joined metrics — P/E, EV/EBITDA, market cap all appear
   in the same screen requests as revenue growth/ROE/margins. The platform boundary excluding
   price/PE/mcap is a **design decision the skills don't ask for or acknowledge**, which makes it
   easy to accidentally weaken under skill pressure ("just add P/E, it's convenient"). Explicit
   negative acceptance: `SELECT column_name FROM <deployed screen>.INFORMATION_SCHEMA.COLUMNS`
   must contain zero columns matching price/PE/EV/market-cap/beta naming patterns.

4. **Null-vs-zero semantics, exactly as already specified.** "**null ≠ zero** — missing metrics
   stay null" is already a documented rule; verify the deployed view actually preserves this
   (a naive `COALESCE(x, 0)` anywhere in the SQL would silently violate it) rather than assume
   the sketch SQL, once deployed verbatim, gets this right without a check.

5. **Coverage-state correctness for the deepest stated need: 5-year growth consistency.**
   idea-generation's Quality Screen ("Consistent revenue growth (5+ years)") is the single
   deepest history requirement found for this product (ticket 27 F12). The deployed screen must
   correctly mark `unavailable` (not `empty` or a silent null) for any subject with less than 5
   years of qualifying history, per the Bundle Coverage Flags glossary distinction
   (`CONTEXT.md`: "unavailable means the platform could not assert completeness... not zero").

**Explicitly not required for promotion:** anything from the market-price-derived subset
(P/E, EV/EBITDA, P/B, market cap, beta) — categorically out of scope by design (ADR 0001/
ERDP-06), routed to F13/ERDP-07 instead; the two skills' stated asks are broader than what F12
can satisfy, and that gap is intentional, not a shortfall to close.

**Known residual risk:** criterion 1 (deployment) is a hard, currently-failing gate purely on
execution — unlike F4/F5/F9/F11 (ticket 41), there is no data-capture question here at all, no
bronze/silver gap, and no code-correctness question either (the Python semantics are unit-tested
per the doc). This is the single most mechanical fix among the still-blocked F1-F12 products:
deploy the existing, already-designed SQL sketch as a real Snowflake view and verify it against
criteria 2-5 above.
