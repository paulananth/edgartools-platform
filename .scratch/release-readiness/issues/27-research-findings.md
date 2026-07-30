# 27 — Research findings: ER skill requirements per F1–F12 product

Feeds ticket 27 (`.scratch/release-readiness/issues/27-survey-er-skill-requirements-per-f1-f12-product.md`).
Written as a durable sibling artifact per this repo's issue-tracker convention, matching the shape
of `.scratch/erdp-coverage-promotion/issues/01-survey-er-skill-requirements-per-product.md`'s
Answer section (12 sections here, F1–F12, instead of that ticket's 4).

## Method

Read all 9 `SKILL.md` files in full (line-numbered). The other 7 skills are single-file (confirmed
via `find ... -name references` — no `references/` dir exists for them), so the `SKILL.md` read is
exhaustive for those.

For the two skills that defer detail to sub-files, read some sub-files in full and the rest via
targeted grep-then-read-in-context (not a full line-by-line read of every sub-file):

- **Read in full:** `initiating-coverage/references/task1-company-research.md` (all ~360 lines) and
  `task2-financial-modeling.md` (lines 1-180 of ~640); `earnings-analysis/references/workflow.md`
  (lines 1-330 of ~490).
- **Grepped, hits read in context:** `earnings-analysis/references/{report-structure,
  best-practices}.md`; `initiating-coverage/references/{task3-valuation,task4-chart-generation,
  task5-report-assembly,valuation-methodologies}.md`; `initiating-coverage/assets/
  {quality-checklist,report-template}.md`.

For each of the twelve F1–F12 data classes I grepped every file above (full-read and grep-only alike)
for the relevant keyword set (ticker/CIK; 10-K/10-Q/8-K/EDGAR/accession; segment/geography; insider/
Form 4/ownership; 13F/institutional/shareholder/holders; auditor/PCAOB/forensic/Beneish/Altman/
Piotroski/restatement; executive/CEO/CFO/compensation/bio; parent company/subsidiary/affiliate) and
read every hit in its surrounding context, not just the matched line. Every citation path below is
relative to `~/projects/financial-services/plugins/vertical-plugins/equity-research/skills/`.

**On "matrix-vs-text mismatch" flags below:** the coverage matrix's own "Classification notes"
section (`.scratch/er-data-plane/coverage-matrix.md:140-147`) already states that some Partial
labels are not claims of per-skill textual need — e.g. line 142: "Identity / filings / financials /
ownership / 13F / graph: remain Partial (products named in footnotes F1–F8, F10–F12); not Covered
until ERDP-05" (a product-exists-but-no-ER-contract status, not a skill-need claim), and line 147:
"Filing text × catalyst / preview / sector: Partial (bronze/daily filings support event discovery;
text backfill incomplete)" (an event-discovery claim, not a prose-mining claim). Where a flag below
would restate something the matrix already explains on that axis, it says so explicitly rather than
implying the matrix owner missed it — the mismatches worth flagging are the ones where **no
plausible reading of the matrix's own rationale** accounts for the Partial label (e.g. F7/F8/F11
below, where the matrix gives no event-discovery or contract-status rationale and the skill text is
simply silent).

**Cross-cutting finding used throughout:** several matrix cells marked **Partial** have **no
supporting text anywhere** in the 9 skills + their reference files, once actually grepped — these
are flagged per-product as **matrix-vs-text mismatches**, following the precedent set by ticket 01.
This matters directly for the 12 downstream promotion-checklist tickets: a checklist written
against a skill requirement that doesn't textually exist would be inventing scope, not promoting a
real Partial→Covered gap.

---

## F1 — Identity (ticker/CIK)

**Skills with explicit textual need:**

| Skill | Cite | What it says |
|---|---|---|
| **catalyst-calendar** | `SKILL.md:10-12` | Step 1 "Define Coverage Universe" — "List of companies to track (tickers or names)" (no other field listed as required for this step) |
| **earnings-preview** | `SKILL.md:12` | Step 1: "Identify the company and reporting quarter" |
| | `:61` | Output: "Company, quarter, earnings date" |
| **earnings-analysis** | `SKILL.md:28-31` | "Do NOT use if: ... Company is not already covered → Need initiation first" — implies a coverage-universe membership check keyed on company identity |
| | `references/report-structure.md:15` | Report header template: `[COMPANY NAME] ([TICKER])` |
| **initiating-coverage** | `references/task1-company-research.md:10` | Task 1 prerequisites: "Company name or ticker symbol only" — the *entire* stated input requirement |
| **thesis-tracker** | `SKILL.md:14` | Step 1 (new thesis): "**Company**: Name and ticker" |
| **idea-generation** | `SKILL.md:78` | Per-idea header template: "**[Company Name] — [Long/Short] — [One-Line Thesis]**" |
| **sector-overview** | `SKILL.md:43` | Company Profiles table, `Company` column header (no explicit ticker column) |

**Skills with only implicit/generic grounding (no explicit ticker/name field stated):**
morning-note (Step 1 just says "Scan for relevant events across coverage universe," `SKILL.md:12`;
templates use bare placeholders `[Company A]`/`[Company B]`, never a ticker field); model-update
(the word "[company]" appears only in the YAML frontmatter `description` line, `SKILL.md:3`, not in
any numbered workflow step).

**"Good enough to rely on" — requirement shape:**
- **Universe scope:** catalyst-calendar needs the **whole coverage universe** resolved at once
  ("list of companies to track"); earnings-preview, earnings-analysis, thesis-tracker,
  initiating-coverage are **per-request/single-company**; idea-generation and sector-overview need
  **multi-issuer** resolution but the set is dynamically discovered by a screen/peer-set, not a
  fixed roster.
- **Freshness:** no skill states any freshness requirement for identity data — ticker/CIK mappings
  change rarely and none of the 9 skills flag staleness as a concern for this class (contrast with
  F18 Earnings-calendar in the sibling ticket 01, where catalyst-calendar explicitly warns dates
  shift).
- **History:** none needed — every skill wants only the *current* mapping, never a ticker-change
  history.
- **Grain:** ticker + company name is the ceiling ever requested in skill text. No skill asks for
  CIK by name (that's a platform-internal identifier, not something the ER workflows themselves
  reference) or for exchange/listing-venue detail.
- **Explicit caveats:** **none found.** No skill anywhere states a data-quality/provenance caveat
  about identity resolution (e.g., ticker collisions, company renames, dual-class share tickers).

---

## F2 — Filings metadata

**Skills with explicit textual need:**

| Skill | Cite | What it says |
|---|---|---|
| **earnings-analysis** | `SKILL.md:71` | Required sources list: "10-Q filing (with filing date and EDGAR link)" |
| | `references/workflow.md:73` | "SEC EDGAR: Search for company and look at most recent 10-Q or 10-K filing date" |
| | `:130,146-151` | "Look for most recent 10-Q (quarterly) or 10-K (annual if Q4)"; "Direct link format: `https://www.sec.gov/cgi-bin/viewer?accession=[accession-number]`" |
| | `:196` | Mandatory verification gate: "10-Q/10-K filing date: _______ (MUST be same quarter as release)" — a hard, checklist-gated correctness bar tying filing metadata to the earnings release date |
| **initiating-coverage** | `references/task1-company-research.md:19-23` | Task 1 primary sources: "Latest 10-K... Recent 10-Qs... DEF 14A (Proxy)... 8-Ks: Material events, acquisitions, management changes" |
| | `references/task2-financial-modeling.md:150` | Notes sheet must document "10-K filing date and fiscal year end" |

**Skills with only generic/event-driven grounding (filing-triggered events referenced, but never as
"filing metadata" — form type, accession number, filing date — in its own right):**
- catalyst-calendar: "M&A milestones (close dates, regulatory approvals)", "Management transitions"
  (`SKILL.md:32-33`) — these are 8-K-triggered event *types*, not a stated filing-index need.
- earnings-preview: no direct hit — its earnings-date need (`SKILL.md:14`) is functionally an
  Earnings-calendar (F18, already surveyed in ticket 01) lookup, not a filing-metadata one; the
  skill never asks for form type/accession/filing date as such.
- morning-note: "M&A announcements or rumors", "Management changes" (`SKILL.md:20-21`) — news-driven.
- model-update: "Event-driven: M&A, restructuring, new product, management change" (`SKILL.md:17`) —
  generic trigger category.
- thesis-tracker: Step 4 generic `Date/Event/...` catalyst table (`SKILL.md:44-49`), earnings is one
  event type among several with no filing-index field.
- idea-generation: "Recent IPOs/SPACs with lockup expirations", "Spin-offs in last 12 months",
  "emerging from restructuring", "Activist involvement" (Special Situation Screen, `SKILL.md:57-62`)
  — implicitly filing-driven (S-1/8-K/13D events) but never stated as a filings-metadata lookup.
- sector-overview: "Recent developments (earnings, M&A, product launches)" (`SKILL.md:50`) —
  generic.

Note: the matrix marks all 9 skills Partial on this row, and its own classification notes
(`coverage-matrix.md:142`) frame Identity/filings/financials/ownership/13F/graph as Partial on a
product-exists-vs-ER-contract axis, not a per-skill-textual-need axis — so the seven skills above
aren't a "mismatch" so much as evidence that their real, stated need is generally shallower
(event-discovery, per the matrix's own framing) than earnings-analysis/initiating-coverage's.

**"Good enough to rely on" — requirement shape:**
- **Correctness bar:** earnings-analysis is the only skill with an explicit, mechanical, date-match
  requirement — filing date must match the release quarter, checklist-gated, named failure mode.
  No other skill states a comparable bar.
- **Depth/freshness:** initiating-coverage Task 1/2 want the **latest** 10-K + recent 10-Qs + latest
  DEF 14A + 8-Ks — a current single-snapshot need, not a filing history sweep (though Task 2's
  3-5-year financials, covered under F4, implicitly touch several years of underlying 10-Ks).
- **Grain:** form type + filing date + accession/EDGAR link is the ceiling explicitly requested
  anywhere (earnings-analysis). No skill asks for XBRL-flag-level filing metadata.
- **Scope:** all per-request/single-company; no skill needs a filings-metadata sweep across a whole
  coverage universe.
- **Explicit caveats:** the only skill-stated caveat is earnings-analysis's RED FLAG "the transcript
  date does NOT match the release date" / "materials show different quarters" (`workflow.md:212-213`)
  — extends the filing-metadata correctness bar into a named stop condition, not just a nice-to-have.
- **Matrix-vs-text note:** catalyst-calendar/morning-note/model-update/thesis-tracker/idea-generation/
  sector-overview are all marked Partial in the matrix for this row, but their textual grounding is
  thin — they reference filing-*triggered events* (M&A, management change, restructuring), never the
  filing metadata fields themselves (form/accession/date). A promotion checklist should treat
  earnings-analysis and initiating-coverage as the two skills with a real, specific need; the rest
  are riding on generic event-type language.

---

## F3 — Filing / research text

**Skills with explicit textual need:**

| Skill | Cite | What it says |
|---|---|---|
| **initiating-coverage** | `references/task1-company-research.md:20` | Task 1 primary sources: "Latest 10-K: **Business description, risk factors, MD&A**, financials" — explicit prose-mining requirement |
| | `:55` | "High-level financial metrics (from 10-K **prose**, not detailed extraction)" — explicitly distinguishes qualitative text-reading from the structured numeric extraction done in Task 2 |

**Skills with thin/no grounding:**
- earnings-analysis cites the 10-Q as a source/hyperlink (`SKILL.md:71`) but never asks for prose
  extraction from it (no "risk factors"/"MD&A" mention anywhere in `earnings-analysis/references/`)
  — the filing is a citation pointer, not a text-mining input, for this skill.
- sector-overview's "Business description (2-3 sentences)" per company profile (`SKILL.md:48`) is
  never explicitly sourced to SEC filing text — could equally be company-website copy; no citation
  path in the skill text ties it to F3 specifically.
- catalyst-calendar, earnings-preview, morning-note, model-update, thesis-tracker, idea-generation:
  **no reference found** (grep across `SKILL.md` + all reference/asset files for
  MD&A/"risk factors"/"business description"/"10-K prose"/"10-K text" returned nothing for these six).

**"Good enough to rely on" — requirement shape:**
- **Only initiating-coverage Task 1 has a real, explicit need**, and it's for the **latest** 10-K
  only (no history depth stated) for a **single company** (Task 1 has no prerequisites beyond
  "company name or ticker").
- **Grain:** specific named sections — business description, risk factors, MD&A — read for prose
  content, not just cited. This is qualitatively different from F2 (filing metadata/citation
  pointer) and matches the coverage matrix's own footnote that F3 is "not a gold narrative table" /
  manual-backfill-only (`sec_filing_text`).
- **Freshness:** no bar stated — a static, one-time read as part of Task 1 research.
- **Explicit caveats:** none found. No skill states a caveat about filing-text quality, OCR
  fidelity, or completeness of the text-extraction path.
- **Matrix rationale check:** the matrix marks catalyst-calendar, earnings-preview, morning-note,
  earnings-analysis, and sector-overview Partial on this row, but its own classification notes
  (`coverage-matrix.md:147`) already explain this as "bronze/daily filings support event discovery;
  text backfill incomplete" — an event-*discovery* claim (does a filing exist, when), not a
  prose-*mining* claim. Read that way, these five cells are not a mismatch: none of the five skills
  claims to mine filing prose, and the matrix never said they did. The one skill with a genuine,
  stated prose-extraction need — reading business description/risk factors/MD&A content, not just
  detecting that a filing happened — is initiating-coverage Task 1, and that need is narrower in
  scope (single company, latest 10-K only) than the matrix's five-skill Partial row might suggest.

---

## F4 — Historical financials

**Skills with explicit textual need:**

| Skill | Cite | What it says |
|---|---|---|
| **earnings-preview** | `SKILL.md:22-25` | "Revenue vs. consensus (total and by segment)"; "EPS vs. consensus"; "Margins (gross, operating, net) — expanding or contracting?"; "Free cash flow" |
| **morning-note** | `SKILL.md:65-69` | Quick-take table: Revenue / EPS / [Key metric] rows with Consensus/Actual/Beat-Miss columns |
| **model-update** | `SKILL.md:24-32` | "Plug New Data" table: Revenue, Gross Margin, Operating Expenses, EBITDA, EPS, [Key metrics] with Prior Estimate/Actual/Delta columns |
| | `:90` | "Always reconcile your estimates to the company's reported figures before projecting forward" |
| **earnings-analysis** | `references/workflow.md:220-236` | REPORTED RESULTS table: Revenue, Gross Margin, EBITDA, Operating Profit, EPS (Adjusted), EPS (GAAP), vs. Our Est/Consensus/Beat-Miss |
| | `SKILL.md:149-151` | Chart list: "Quarterly revenue progression"; "Quarterly EPS progression"; "Quarterly margin trends" — implies multi-quarter trailing series, not a single point |
| **initiating-coverage** | `references/task2-financial-modeling.md:91-145` | Explicit 3-5-year extraction of full Income Statement (14 line items incl. revenue/COGS/gross profit/EBITDA/EBIT/pretax/tax/NI/EPS basic+diluted/shares), Cash Flow Statement (9 items), Balance Sheet (8 items), plus calculated Historical Metrics (revenue growth %, gross/EBITDA/operating/net margin %, FCF, FCF margin, ROIC, D/E, current ratio) |
| **thesis-tracker** | `SKILL.md:38-41` | Scorecard example: "Revenue growth >20% ... Q3 was 22%"; "Margin expansion ... Margins flat YoY" — needs at least a YoY comparison point |
| **idea-generation** | `SKILL.md:25-46` | Screens require, across the **whole candidate universe**: revenue growth >15% YoY, earnings growth >20% YoY, ROIC >15%, ROE >15%, FCF yield >5%, FCF conversion, debt/equity |
| **sector-overview** | `SKILL.md:43` | Company Profiles table columns: Revenue, Growth, EBITDA Margin, for 5-10 peer companies |

**"Good enough to rely on" — requirement shape:**
- **Depth is the sharpest differentiator:** initiating-coverage Task 2 is by far the deepest single
  consumer — full 3-statement, 3-5-year history plus derived ratios, for one company. idea-generation
  and sector-overview need **breadth** (whole screening universe / 5-10 peers) but only **shallow
  depth** (current + one YoY comparison point per metric). earnings-analysis/model-update need the
  current-quarter actual plus a short trailing series (for charts) and their own forward-projected
  estimates (computed by the skill, not sourced from the platform). morning-note needs only the
  single just-reported quarter.
- **Freshness:** morning-note/earnings-analysis need same-quarter-just-reported freshness; the rest
  have no explicit staleness bar beyond "most recent available."
- **GAAP-vs-adjusted distinction:** model-update's explicit caveat ("Note any non-recurring items and
  whether your estimates are GAAP or adjusted," `SKILL.md:91`) and earnings-analysis's REPORTED
  RESULTS table listing **both** "EPS (Adjusted)" and "EPS (GAAP)" as separate rows
  (`workflow.md:228-229`) matter directly for this product: the platform's `SEC_FINANCIAL_DERIVED`/
  `financial_derived` is GAAP/XBRL-derived — it does not carry a separately-disclosed adjusted/
  non-GAAP figure (that gap is tracked as its own matrix row, "Non-GAAP values," already a named
  Gap). A promotion checklist for F4 should not silently assume it also covers the adjusted-EPS need.
- **Explicit caveats:** model-update `SKILL.md:90-91` (quoted above) is the clearest skill-stated
  caveat: reconcile to reported figures first, and be explicit about GAAP vs. adjusted basis.

---

## F5 — Earnings 8-K GAAP snapshot

**Skills with explicit textual need:**

| Skill | Cite | What it says |
|---|---|---|
| **morning-note** | `SKILL.md:14-17,65-70` | "Any coverage companies reporting overnight or pre-market?"; "Earnings surprises (beat/miss on revenue, EPS, key metrics)"; quick-take table Consensus/Actual/Beat-Miss for Revenue/EPS/[Key metric]/Guidance |
| **model-update** | `SKILL.md:21-32` | Step 2 "After Earnings" — "Update the model with reported actuals" table (Revenue, Gross Margin, OpEx, EBITDA, EPS, key metrics) |
| **earnings-analysis** | `references/workflow.md:220-229` | REPORTED RESULTS table with both "EPS (Adjusted)" and "EPS (GAAP)" rows — needs the reported GAAP flash plus a separately-disclosed adjusted figure the platform doesn't carry |
| **thesis-tracker** | `SKILL.md:29,40` | Update-log example data-point type "earnings beat"; scorecard example "Q3 was 22%" (a reported-quarter revenue-growth figure) |

**Thin/templatey grounding:**
- catalyst-calendar's only F5-adjacent text is the illustrative weekly-preview line "[Company] Q[X]
  earnings — consensus [$X EPS], our estimate [$X]" (`SKILL.md:59`) — this is about the *estimate*
  ahead of the print (F16 Consensus, already surveyed in ticket 01), not the reported GAAP actual
  itself.
- earnings-preview runs *before* the print by design (Step 1: "Find the earnings date," `SKILL.md:14`)
  so has no stated need for the current quarter's already-reported flash; its only related note is
  "Historical earnings reactions help calibrate expectations" (`SKILL.md:72`), which is thin and
  about market reaction, not GAAP figures.
- initiating-coverage: no explicit 8-K-flash reference; its 8-K mention (`task1-company-research.md:23`)
  is categorical ("Material events, acquisitions, management changes"), not earnings-flash-specific —
  the skill's financial data instead comes from 10-K/10-Q (F4), not the 8-K earnings release.

**"Good enough to rely on" — requirement shape:**
- **Freshness:** morning-note has the tightest bar — same-day, "reporting overnight or pre-market."
  model-update/earnings-analysis need it within their 24-48 hour turnaround windows. thesis-tracker
  needs it whenever a new data point is logged (event-driven, not scheduled).
- **Scope:** all per-request/single-company (or, for morning-note, a daily scan across the whole
  coverage book — same universe-scope pattern already found for F18 Earnings-calendar in ticket 01).
- **History:** none needed for this class specifically — every reference wants only the just-reported
  quarter's flash, never a series (the multi-quarter *trend* comes from F4, not F5).
- **GAAP vs. adjusted:** earnings-analysis's explicit two-row (Adjusted/GAAP) table is the sharpest
  gap-relevant finding — the platform's `EARNINGS_RELEASE`/`fact_earnings_release` is GAAP-only per
  the matrix footnote (`revenue_gaap`, `net_income_gaap`, `eps_gaap_diluted`; `has_non_gaap` is a flag
  only, not a value) — so this skill's stated need is only half-satisfiable by F5 alone.
- **Explicit caveats:** none of the four skills states a caveat about the GAAP-flash data's quality
  or provenance specifically (distinct from the GAAP-vs-adjusted distinction noted above, which is a
  scope point, not a stated trust/quality caveat).

---

## F6 — Ownership / Form 4

**Skills with explicit textual need:**

| Skill | Cite | What it says |
|---|---|---|
| **idea-generation** | `SKILL.md:29` | Value Screen: "Insider buying in last 90 days" |
| | `:46` | Quality Screen: "Insider ownership >5%" |
| | `:52` | Short Screen: "Insider selling" |
| **initiating-coverage** | `references/task1-company-research.md:139,252` | Governance-assessment bullet: "Insider ownership percentage" (one item among board composition / comp structure) |
| | `assets/report-template.md:300-304` | Optional "Ownership Structure [if disclosed]" section: "Major shareholders and ownership %"; "Insider ownership trends" |

**Skills confirmed with no reference (grep negative across `SKILL.md` + all reference/asset files
for insider/"Form 4"/ownership/shareholder):** morning-note, earnings-analysis, thesis-tracker.
The matrix's general contract-status rationale (`coverage-matrix.md:142`, "remain Partial... not
Covered until ERDP-05") covers *why the label is Partial rather than Covered*, but it does not assert
that all listed skills have a stated textual need — that's a separate question this survey answers:
for these three, no textual need was found at all, which matters for scoping what "Covered" should
even mean per-skill in the downstream checklist.

**Note on catalyst-calendar:** its "Insider trading windows (lockup expirations)" (`SKILL.md:34`) is
a **calendar/timing** concern (when a lockup opens), not a Form 4 transaction/holdings data need —
the matrix correctly marks catalyst-calendar N/A on this row, consistent with this reading.

**"Good enough to rely on" — requirement shape:**
- **idea-generation is the only skill with a specific, actionable spec**: direction (buying vs.
  selling), a recency window ("last 90 days"), and an ownership-percentage threshold (">5%") —
  needed **across the whole screening universe** (cross-sectional, since screens run over many
  candidates at once), not a per-request lookup.
- **initiating-coverage's need is a single point-in-time percentage for one company**, explicitly
  soft-gated ("if disclosed") rather than a hard requirement for the report.
- **Freshness:** idea-generation's 90-day window is the only stated freshness bar; initiating-coverage
  has none (static, as-of-report-date is fine).
- **History:** idea-generation's screens are effectively a rolling 90-day transaction window, not a
  full transaction history; initiating-coverage wants a snapshot percentage only.
- **Explicit caveats:** none found in either skill about ownership-data provenance/completeness.

---

## F7 — 13F / holders

**Skills with explicit textual need:**

| Skill | Cite | What it says |
|---|---|---|
| **idea-generation** | `SKILL.md:111` | Important Notes: "Avoid crowded trades — check ownership data, short interest, and how many analysts cover the name" |
| **initiating-coverage** | `assets/report-template.md:300-301` | "Ownership Structure [if disclosed] — Major shareholders and ownership %" (ambiguous — could reflect insider or institutional/13F ownership; the template text does not distinguish) |

**Skills confirmed with no reference:** earnings-analysis, thesis-tracker (grep negative for
13F/institutional/holders/shareholder across all their files, beyond generic uses of "institutional"
as an adjective describing report quality, e.g. "institutional standards"). As with F6, the matrix's
`coverage-matrix.md:142` rationale explains the Partial-not-Covered label on a contract-status axis,
not a per-skill textual-need claim — but neither earnings-analysis nor thesis-tracker states a need
for this data class at all, textually.

**"Good enough to rely on" — requirement shape:**
- **This is the weakest-grounded of all twelve F1–F12 products.** No skill anywhere states a
  field-level need for a 13F holder list (top holders, % held, filer/manager names, holding period).
  idea-generation's "check ownership data ... how many analysts cover the name" is a **crowding
  check**, not a request for the holder-list data itself — it's closer to a qualitative gut-check
  than a data-consumption requirement, and doesn't specify grain, freshness, or universe breadth.
  initiating-coverage's "major shareholders" bullet is generic and explicitly optional
  ("if disclosed").
- **Scope/freshness/history:** none stated by any skill — there simply isn't enough textual
  substance to characterize a "good enough" bar for this product from the skill text alone.
- **Explicit caveats:** none found.

---

## F8 — Graph neighborhood (insider/audit/parent)

**Skills with explicit textual need:**

| Skill | Cite | What it says |
|---|---|---|
| **initiating-coverage** | `references/task1-company-research.md:122-134` | Executive research: "Prior roles and companies (last 2-3 positions)" as part of each 300-400-word bio — the closest de-facto grounding for an EMPLOYED_BY-style employment-history graph |
| **idea-generation** | `SKILL.md:62` | Special Situation Screen: "Management changes at underperforming companies" — implies tracking management transitions, but not an auditor/parent-company network |

**Skills confirmed with no reference (grep negative for insider/auditor/PCAOB/"parent
compan"/subsidiary/affiliate across all files):** earnings-analysis, thesis-tracker. Again, the
matrix's `coverage-matrix.md:142` rationale addresses why the label is Partial-not-Covered generally,
not whether a specific skill states a need — and critically, **no skill anywhere mentions auditor
networks or parent/subsidiary relationships at all**, despite F8's footnote explicitly naming
`AUDITED_BY`/`HAS_PARENT_COMPANY` as in-scope relationship types. That absence holds across all 9
skills, not just the two flagged here, so it isn't explained by the contract-status framing either.

**"Good enough to rely on" — requirement shape:**
- **No skill states a need for multi-hop graph traversal** (e.g., "who else does this auditor also
  audit," "what's the parent/subsidiary chain," "who are this company's institutional co-holders").
  The only grounded sub-piece across all 9 skills is initiating-coverage's executive employment
  history — 2-3 prior positions per executive, single company, no freshness bar (bios are static
  once written), no cross-company traversal implied (it's "where did this person work before," not
  "who else at this company also worked at company X").
- **This is, alongside F7, one of the two weakest-grounded products.** The matrix's Partial
  assignment for earnings-analysis/initiating-coverage/thesis-tracker/idea-generation substantially
  outruns what the skill text actually supports — three of the four relationship types the footnote
  names (`AUDITED_BY`, `HAS_PARENT_COMPANY`, `INSTITUTIONAL_HOLDS`-as-graph-edge) have **zero**
  textual basis in any of the 9 skills.
- **Explicit caveats:** none found.

---

## F9 — Segment / product-geo revenue

**Skills with explicit textual need:**

| Skill | Cite | What it says |
|---|---|---|
| **earnings-preview** | `SKILL.md:22` | "Revenue vs. consensus (total **and by segment**)" |
| **model-update** | `SKILL.md:34-36` | "Segment Detail (if applicable) — Update each segment's revenue and margin; Note any segment mix shifts" |
| **earnings-analysis** | `SKILL.md:151` | Chart list: "Revenue by segment/geography" |
| | `references/workflow.md:278-291` | Step 6 "Segment/Geographic/Product Analysis" — business segment, geography (NA/Europe/China/etc.), product category, channel; "Trends vs. prior quarters" (implies a multi-quarter trailing series, not one point) |
| | `references/report-structure.md:94-104` | Table template with named segment rows (Segment A/B/C) across multiple historical quarters + YoY growth |
| **initiating-coverage** | `references/task2-financial-modeling.md:94,153,235-267` | Explicit "Revenue by Geography (15-20 rows)" tab and "20-30 rows" product breakdown, 3-5yr historical + 5yr projected, with an explicit reconciliation rule: "Revenue by product total = Revenue by geography total = Total revenue" (`:267`) |
| **sector-overview** | `SKILL.md:24` | "Market segmentation (by product, geography, end market, customer type)" — **industry/TAM-level** segmentation, not company financial-statement segment reporting; distinguish carefully from the platform's XBRL `segment` concept |

**"Good enough to rely on" — requirement shape:**
- **initiating-coverage Task 2 is by far the most demanding** — a curated, reconciling 15-30-row
  product/geography revenue mart per company, single company, 3-5 years history + 5 years forward.
  This matches the coverage matrix's own footnote verbatim: "No curated product/geo revenue model
  mart; initiation T2 still Gap for 20-30-row model" (F9 footnote) — the skill text confirms this is
  a real, load-bearing requirement, not an inflated one.
- **earnings-analysis needs at least a few named segments across several trailing quarters** for its
  chart set and trend narrative — shallower than initiating-coverage but still multi-period.
- **earnings-preview/model-update need only the current quarter's segment cut**, single company,
  explicitly conditional ("if applicable" — model-update; segment mentioned only once in
  earnings-preview's framework, not elaborated further).
- **sector-overview's "segmentation" is a market-sizing/TAM concept** (by product/geography/end-market/
  customer-type at the *industry* level), not the company financial-statement segment revenue this
  product covers — likely a matrix mislabel; flag to the downstream ticket rather than assume
  sector-overview needs the same `SEC_FINANCIAL_FACT.segment` data as the others.
- **Explicit caveats:** initiating-coverage's reconciliation rule (segment sums must tie to total
  revenue) is a correctness constraint stated in the skill text, not phrased as a data-quality
  caveat about the source, but it directly implies the promoted product must guarantee sum-to-total
  reconciliation, which raw XBRL segment strings (the platform's current F9 surface) do not
  inherently guarantee.

---

## F10 — Executive / management & pay

**Skills with explicit textual need:**

| Skill | Cite | What it says |
|---|---|---|
| **initiating-coverage** | `references/task1-company-research.md:22` | "DEF 14A (Proxy): Executive compensation, board composition" |
| | `:115-134` | Full spec: CEO + CFO always required, 2 additional C-suite; 300-400 word bio per executive covering current role, prior 2-3 roles/companies, key accomplishments, education, years of experience, tenure at current company |
| | `:136-140` | Governance assessment: board composition/independence, key board members' backgrounds, insider ownership %, "**Executive compensation structure**" |

**Thin/generic grounding:**
- morning-note's only related text is "Management changes" as a news-event category (`SKILL.md:22`)
  — an event trigger, not a structured executive/pay record.
- thesis-tracker's "management departure" is listed only as an example data-point type in the update
  log (`SKILL.md:29`) — generic.
- idea-generation's "Management changes at underperforming companies" (Special Situation Screen,
  `SKILL.md:62`) is likewise event-only.
- earnings-analysis: no pay-specific hit found; its only person-level reference is using a title for
  a quote citation ("CFO prepared remarks," `references/report-structure.md:354`), not a personnel
  record.

**"Good enough to rely on" — requirement shape:**
- **initiating-coverage Task 1 is the only skill with a real, structured spec** — named roles
  (CEO/CFO always, +2 others), tenure, prior-company history, education, and compensation structure,
  for a **single company**, **single point-in-time** (bios are static once written — no freshness or
  history-depth bar stated).
- **All other skills** (morning-note, thesis-tracker, idea-generation) treat executives only as
  **event subjects** ("management change" as a headline/data point), never as a queryable name/role/
  pay record — their Partial marking in the matrix is grounded only in this thin, event-level sense.
- **Grain match to platform surface:** the platform's `EXECUTIVE_RECORD` (name, role, salary, bonus,
  stock, option, total) lines up closely with initiating-coverage's bio + "compensation structure"
  need, but initiating-coverage's bio content (prior roles, education, accomplishments) goes beyond
  what a pay-focused gold table alone would supply — the bio-narrative portion likely still requires
  filing-text/web research (F3-adjacent), not a pure F10 lookup.
- **Explicit caveats:** none found.

---

## F11 — Accounting forensic scores

**Skills with explicit textual need:**

| Skill | Cite | What it says |
|---|---|---|
| **idea-generation** | `SKILL.md:55` | Short Screen: "Accounting red flags (**auditor changes, restatements**)" |

**Skills confirmed with no reference:** earnings-analysis, initiating-coverage, thesis-tracker — a
full grep for auditor/PCAOB/forensic/Beneish/Altman/Piotroski/restatement/"going concern" across
every `SKILL.md` and every reference/asset file for all 9 skills returned **exactly one hit**, the
idea-generation line above.
All three of earnings-analysis/initiating-coverage/thesis-tracker are marked Partial in the matrix
for this row; the matrix's general contract-status rationale (`coverage-matrix.md:142`) explains
the label but not a per-skill need, and none of these three states one — idea-generation is the
only skill with any textual grounding at all for this data class.

**"Good enough to rely on" — requirement shape:**
- **idea-generation's stated need is a boolean/categorical screen criterion** — auditor-change
  flag and restatement flag, each yes/no — needed **across the whole screening universe**
  (cross-sectional, since screens run over many candidates at once). The skill text **never asks
  for a computed forensic score** (no mention of Beneish M-Score, Altman Z-Score, or Piotroski
  F-Score anywhere, despite the platform's `ACCOUNTING_FLAG` product explicitly carrying
  "Beneish/Altman/Piotroski-type scores" per the coverage-matrix footnote).
- **This means the platform's F11 surface is materially broader than what any skill actually asks
  for in text** — the real, textually-grounded need is narrower: two specific event flags
  (auditor change, restatement), not a numeric forensic-risk score.
- **Freshness/history:** no bar stated; idea-generation's screens presumably want the most recent
  status, no history depth specified.
- **Explicit caveats:** none found.

---

## F12 — Pure-SEC subject features

**Skills with explicit textual need:**

| Skill | Cite | What it says |
|---|---|---|
| **idea-generation** | `SKILL.md:24-55` | Value/Growth/Quality/Short screens collectively request, **across the whole candidate universe**: revenue growth (YoY), earnings growth (YoY), margin trend/expansion, ROIC (>15%), ROE (>15%), FCF yield (>5%), FCF conversion, debt/equity, revenue growth consistency (5+ years) |
| **sector-overview** | `SKILL.md:43` | Company Profiles table for 5-10 peers: Revenue, Growth, EBITDA Margin, Market Share, Key Differentiator |

**"Good enough to rely on" — requirement shape:**
- **Both consuming skills need cross-sectional, whole-universe (or whole-peer-set) breadth**, not a
  per-request single-company lookup — idea-generation runs a screen over a candidate universe;
  sector-overview builds a comparison table over 5-10 peers at once. This is the defining shape for
  F12: it must serve many issuers at once, not one CIK on demand.
- **Neither skill's text distinguishes pure-SEC metrics from market-joined metrics.** From the
  skill's own point of view, "P/E below sector median," "EV/EBITDA below historical average,"
  "Free cash flow yield >5%," and "ROE >15%" are all just line items in one combined screening
  request (`SKILL.md:24-31` for idea-generation's Value Screen alone) — the skill text makes no
  internal distinction between the pure-SEC-derived subset (revenue growth, margins, ROE/ROIC, FCF
  yield's cash-flow numerator, debt/equity) and the market-price-derived subset (P/E, EV/EBITDA,
  P/B, market cap).
- **The ADR 0001 / ERDP-06 boundary (no price/PE/mcap in this vector) is a platform design decision
  the skill text itself doesn't acknowledge or accommodate.** The portion of each skill's stated ask
  that F12 can actually satisfy is: revenue growth, margin levels/trend, ROE/ROIC, FCF-yield
  numerator (FCF itself, not FCF/price), and debt/equity. P/E, EV/EBITDA, P/B, and market cap remain
  categorically out of scope for this product by design, routed instead to F13/ERDP-07 (the
  yfinance/market-price Explore join) — the two skills' stated asks are broader than what F12 alone
  can satisfy; the gap is by design, not a shortfall in the product.
- **Freshness/history:** idea-generation's growth screens imply at least a YoY comparison (one prior
  period); "Consistent revenue growth (5+ years)" (Quality Screen, `SKILL.md:41`) is the single
  deepest history requirement found for this product — 5 years of trailing growth consistency,
  cross-sectional across the whole screened universe.
- **Explicit caveats:** none found — neither skill states a caveat about pure-SEC vs. market-blended
  feature provenance; that boundary is purely a platform-side decision (ADR 0001), not something the
  skill text asks for or warns about.

---

## Cross-product summary for downstream tickets (28–39)

| Product | Strength of textual grounding | Skills with real (not just matrix-asserted) need |
|---|---|---|
| F1 Identity | Strong, but freshness/caveat text absent | catalyst-calendar, earnings-preview, earnings-analysis, initiating-coverage, thesis-tracker, idea-generation, sector-overview |
| F2 Filings metadata | Strong for 2 skills, thin/generic for the rest | earnings-analysis, initiating-coverage |
| F3 Filing/research text | Real for exactly 1 skill | initiating-coverage (Task 1 only) |
| F4 Historical financials | Strong across most skills, sharply varying depth | earnings-preview, morning-note, model-update, earnings-analysis, initiating-coverage, thesis-tracker, idea-generation, sector-overview |
| F5 Earnings 8-K GAAP snapshot | Solid for 4 skills; GAAP-only gap vs. "Adjusted" need flagged | morning-note, model-update, earnings-analysis, thesis-tracker |
| F6 Ownership/Form 4 | Strong for 1 skill, soft for 1, absent for 3 despite matrix Partial | idea-generation (strong), initiating-coverage (soft) |
| F7 13F/holders | **Weakest of all 12** — no field-level ask anywhere | none with real grounding; idea-generation's "crowding" note is the only adjacent text |
| F8 Graph neighborhood | **Weakest alongside F7** — 3 of 4 named relationship types have zero hits | initiating-coverage (executive employment history only) |
| F9 Segment/geo revenue | Strong, matches matrix's own "no curated mart" framing | earnings-preview, model-update, earnings-analysis, initiating-coverage; sector-overview's need is industry-TAM-level, likely mislabeled |
| F10 Executive/management & pay | Real for 1 skill; event-only for the rest | initiating-coverage |
| F11 Accounting forensic scores | Real need is narrower than the product (2 flags, not 3 scores) | idea-generation only |
| F12 Pure-SEC subject features | Strong but conflated with market metrics in skill text | idea-generation, sector-overview |

Tickets 28-39 should read the relevant F-section above plus their own product's schema/code detail;
where a mismatch or narrower-than-matrix finding is noted, treat it as the basis for scoping the
promotion checklist's acceptance criteria, not as license to expand scope back to the full matrix
Partial-cell claim.
