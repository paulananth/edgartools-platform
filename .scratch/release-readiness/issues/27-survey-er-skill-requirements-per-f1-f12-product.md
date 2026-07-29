# 27 — Survey financial-services ER skill requirements per F1–F12 product

Type: research
Status: resolved
Blocked by:

## Question

For each of the twelve F1–F12 footnote products in `.scratch/er-data-plane/coverage-matrix.md`
(Identity/ticker-CIK, Filings metadata, Filing/research text, Historical financials, Earnings
8-K GAAP snapshot, Ownership/Form 4, 13F/holders, Graph neighborhood, Segment/product-geo
revenue, Executive/management pay, Accounting forensic scores, Pure-SEC subject features),
survey every financial-services equity-research skill (`catalyst-calendar`, `earnings-preview`,
`morning-note`, `model-update`, `earnings-analysis`, `initiating-coverage`, `thesis-tracker`,
`idea-generation`, `sector-overview`; `~/projects/financial-services/plugins/vertical-plugins/equity-research/skills/*/SKILL.md`,
read-only — do not edit, commit, or push anything in that repo) that touches that data class,
and report:

- Which skills actually reference/need this data class, and in what form (exact fields, grain,
  freshness expectations, coverage-breadth expectations) — quote the relevant workflow steps.
- What "good enough to rely on" looks like from the skill's own workflow (per-request lookup vs.
  full coverage-universe breadth; same-day freshness vs. week-old acceptable; latest-only vs.
  history depth needed).
- Any explicit skill-stated caveats about this data class's quality, completeness, or provenance
  (mirroring `erdp-coverage-promotion` ticket 01's finding that earnings-preview explicitly notes
  "consensus estimates change — always note the source and date").

The coverage matrix's own footnotes (F1–F12 rows) already record each product's concrete
platform surface (table/view names, layer, why it's Partial not Covered) — use those as the
starting point for what to check against real schema/code, not as a substitute for actually
reading the 9 skill files.

Report findings grouped by product (12 sections, F1 through F12), each listing the skills that
need it and the concrete requirements extracted, following the exact structure and level of
detail as ticket 01's answer in
`.scratch/erdp-coverage-promotion/issues/01-survey-er-skill-requirements-per-product.md`. This
survey directly feeds tickets 28–39 (one per-product promotion-checklist ticket) — write
findings so each of those tickets can be resolved by reading this ticket's answer plus its own
product-specific schema/code detail, not by re-reading all 9 skill files from scratch.

## Answer

Full findings written to
[27-research-findings.md](27-research-findings.md) (durable sibling artifact, per this repo's
issue-tracker convention — kept out of this file to stay resolvable by the 12 downstream tickets
without re-reading all 9 skill files).

**Method:** read all 9 `SKILL.md` files in full; for `earnings-analysis`/`initiating-coverage`
(the two that defer detail to `references/`), read the most relevant sub-files in full
(`task1-company-research.md`, `task2-financial-modeling.md` lines 1-180, `workflow.md` lines
1-330) and grepped the rest for the F1-F12 keyword set, reading every hit in context.

**Headline findings (detail + citations in the sibling file):**
- Grounding strength varies sharply across the 12 products. F1 (Identity) and F4 (Historical
  financials) are strongly grounded across nearly every skill. **F7 (13F/holders) and F8 (Graph
  neighborhood) are the weakest** — most of the matrix's Partial cells for these two rows have no
  supporting skill text at all once actually grepped; the matrix's own contract-status rationale
  (`coverage-matrix.md:142`) explains why the *label* is Partial-not-Covered, but does not assert a
  per-skill textual need, which is a separate question this survey answers per product.
- **F11 (Accounting forensic scores)**: a full grep across all 9 skills + reference files for
  auditor/PCAOB/Beneish/Altman/Piotroski/restatement returned **exactly one hit** (idea-generation's
  "Accounting red flags (auditor changes, restatements)") — and that hit asks for two boolean event
  flags, never a computed forensic score, despite the platform's `ACCOUNTING_FLAG` product carrying
  Beneish/Altman/Piotroski-type scores.
- **F5 (Earnings 8-K GAAP snapshot)**: earnings-analysis explicitly wants both "EPS (Adjusted)" and
  "EPS (GAAP)" side by side — the platform's `EARNINGS_RELEASE` table is GAAP-only, so this stated
  need is only half-satisfiable by F5 alone (the adjusted half is the separately-tracked "Non-GAAP
  values" Gap).
- **F9 (Segment/product-geo revenue)**: initiating-coverage Task 2's need (a reconciling 15-30-row
  product/geography mart, 3-5yr history) is the single most demanding, well-grounded requirement
  found for any of the 12 products — confirms rather than inflates the matrix footnote's own "no
  curated mart" framing.
- **F12 (Pure-SEC subject features)**: both consuming skills (idea-generation, sector-overview) ask
  for combined pure-SEC + market-priced metrics in one undifferentiated request; the ADR 0001/
  ERDP-06 boundary excluding price/PE/mcap from this vector is a platform design choice the skill
  text itself never acknowledges — the skills' stated asks are broader than what F12 alone can
  satisfy, by design.

Per-product detail, full citation tables, "good enough to rely on" shape (universe scope,
freshness, history depth, grain), and explicit skill-stated caveats for all twelve products are in
the sibling findings file. No promotion checklists (numbered acceptance criteria) are written here
or there — that is explicitly deferred to tickets 28-39.
