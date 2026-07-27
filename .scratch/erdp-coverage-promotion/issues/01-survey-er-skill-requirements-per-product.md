# 01 — Survey financial-services ER skill requirements per new Explore product

Type: research
Status: resolved
Blocked by:

## Question

For each of the four new Explore products — `CONSENSUS_ESTIMATES` (ERDP-01), `GUIDANCE_FACTS` (ERDP-02), `EARNINGS_CALENDAR` (ERDP-03), `TRANSCRIPT_EVENTS` (ERDP-04) — survey every financial-services equity-research skill (`catalyst-calendar`, `earnings-preview`, `morning-note`, `model-update`, `earnings-analysis`, `initiating-coverage`, `thesis-tracker`, `idea-generation`, `sector-overview`; `~/projects/financial-services/plugins/vertical-plugins/equity-research/skills/*/SKILL.md`, read-only) that touches that data class, and report:

- Which skills actually reference/need this data class, and in what form (exact fields, grain, freshness expectations) — quote the relevant workflow steps.
- What "good enough to rely on" looks like from the skill's own workflow (e.g. does it need every ticker in a coverage universe, or is per-request lookup fine? Does it need same-day freshness or is week-old acceptable? Does it need history or just latest?).
- Any explicit skill-stated caveats about estimate/guidance/calendar/transcript data quality (e.g. earnings-preview's note that "consensus estimates change — always note the source and date").

Report findings grouped by product (4 sections), each listing the skills that need it and the concrete requirements extracted. This survey directly feeds tickets 02–06 (matrix reclassification + per-product promotion checklists) — write findings so each of those tickets can be resolved by reading this ticket's answer plus its own product-specific detail, not by re-reading all 9 skill docs from scratch.

## Answer

### Method

Read all 9 `SKILL.md` files in full (line-numbered) plus, for the two skills that defer detail to
sub-files (`earnings-analysis`, `initiating-coverage`), grepped every file under their
`references/` subdirectory for `consensus|transcript|guidance|earnings date|earnings
calendar|pre-market|after-hours|street` and read every hit in context. The other 7 skills are
single-file (`find … -name references` confirms no `references/` dir exists for them), so the
`SKILL.md` grep is exhaustive for those. All line numbers below are verified against the actual
file content (not extrapolated from a `grep -n` hit alone) — where a quote spans lines I read the
full surrounding block before citing it.

Every citation path is relative to
`~/projects/financial-services/plugins/vertical-plugins/equity-research/skills/`.

Cross-cutting finding used below: for **`idea-generation`** and **`sector-overview`**, a full
`SKILL.md` read plus targeted greps for `consensus|transcript|guidance|earnings date|calendar|
analyst|estimate|street` found **zero** references to any of the four data classes (the only
adjacent hit is idea-generation's "check … how many analysts cover the name" — a crowding/coverage
*count*, not a consensus *value*). `initiating-coverage`'s `SKILL.md` itself is also silent on all
four, but its `references/` sub-files are not — see per-product detail below. Where the
coverage-matrix (`.scratch/er-data-plane/coverage-matrix.md`) marks a cell `Gap` for
idea-generation/sector-overview despite this silence, that's flagged per-product below as a
**matrix-vs-text mismatch for ticket 02 to decide**, not resolved here.

---

### 1. CONSENSUS_ESTIMATES (ERDP-01)

**Skills with explicit textual need:**

| Skill | Cite | What it says |
|---|---|---|
| **earnings-preview** | `earnings-preview/SKILL.md:13` | Step 1: "Pull consensus estimates via web search (revenue, EPS, key segment metrics)" |
| | `:22-23,26` | Step 2 framework: "Revenue vs. consensus (total and by segment)"; "EPS vs. consensus"; "Forward guidance vs. consensus" |
| | `:54` | Step 4 catalyst checklist: "[Metric] vs. [consensus/whisper number] — why it matters" |
| | `:62` | Step 5 output: "Consensus estimates table" |
| | `:70` | Important Notes: **"Consensus estimates change — always note the source and date of estimates"** |
| | `:71` | "'Whisper numbers' from buy-side surveys are often more relevant than published consensus" |
| **earnings-analysis** | `SKILL.md:74` | Critical Requirement #4 (⭐⭐⭐ MANDATORY citations): "✅ Consensus estimates source (Bloomberg/FactSet/etc. with date)" is on the REQUIRED SOURCES LIST |
| | `SKILL.md:101` | Verification checklist: "Beat/miss analysis cites consensus source with date" |
| | `references/workflow.md:185-188` | "Consensus estimates - From Bloomberg, FactSet, Refinitiv, or Yahoo Finance / CRITICAL: Use estimates from BEFORE earnings release / Look for 'as of [date before earnings]' to ensure pre-announcement consensus / Needed for beat/miss analysis" |
| | `references/workflow.md:205` | Mandatory Step-2 verification gate: "Have pre-earnings consensus estimates with source date" |
| | `references/workflow.md:223` | Beat/miss table header template: `Reported / Our Est / Consensus / Beat/(Miss)` |
| | `references/best-practices.md:128-129,182` | "[ ] Beat/miss analysis cites consensus source (Bloomberg, FactSet, etc.)"; "[ ] Consensus source includes 'as of' date (pre-earnings close)"; "[ ] Consensus estimates are pre-earnings (not post-earnings)" |
| **morning-note** | `SKILL.md:63-70` | Step 3 "Quick Takes on Earnings" table has a `Consensus` column alongside `Actual`/`Beat-Miss`, rows Revenue/EPS/[Key metric]/Guidance — gated: "If a coverage company reported" |
| **model-update** | `SKILL.md:94` | Important Notes: "Check consensus after updating — how do your revised estimates compare to the Street?" — comparison-only, no source/date mandate stated |
| **catalyst-calendar** | `SKILL.md:59` | Step 4 weekly-preview template bullet: "[Day]: [Company] Q[X] earnings — consensus [$X EPS], our estimate [$X], key focus: [metric]" — illustrative template text, EPS-only, not stated as a hard requirement elsewhere in the skill |
| **initiating-coverage** | `references/task3-valuation.md:307,314` | Task 3 (Valuation) peer-comps data-gather step: "NTM (Next Twelve Months) consensus estimates"; "Consensus estimates from Yahoo Finance, Seeking Alpha (if pro tools unavailable)" |
| | `references/valuation-methodologies.md:186` | "Next-year (NTM) estimates from consensus" (multiples methodology) | 

**Skills confirmed with no reference** (checked `SKILL.md` + `references/` where present):
thesis-tracker, idea-generation, sector-overview. (`initiating-coverage`'s *own* `SKILL.md` is
silent — the requirement only surfaces in Task 3's reference doc, one input among several for
peer-comp NTM multiples, not gating any deliverable.)

**"Good enough to rely on" — requirement shape:**
- **Universe scope:** per-request, single company, except catalyst-calendar which is
  coverage-universe-wide (but only for the illustrative weekly-preview line, EPS-only).
- **Freshness:** earnings-preview/earnings-analysis need the **pre-earnings-release** snapshot —
  earnings-analysis is explicit and mechanical about this ("as of [date before earnings]",
  checklist item "Consensus estimates are pre-earnings (not post-earnings)"); using a
  post-print-revised consensus is a named failure mode. morning-note needs same-day freshness
  (only for names reporting *today*). model-update and initiating-coverage have no stated
  freshness bar — "current" is enough.
- **History:** none of the 9 skills need a *history* of consensus values — every reference is to
  the single current-quarter (or NTM) figure. No skill asks for a trailing series.
- **Grain:** revenue + EPS is the floor everywhere it's mentioned; earnings-preview additionally
  wants "key segment metrics"; initiating-coverage wants NTM revenue/EBITDA/EPS for peer multiples.
- **Source attribution:** **mandatory and specific** for earnings-analysis (named source +
  as-of date, hyperlinked, checklist-gated) and strongly recommended for earnings-preview ("always
  note the source and date"). Not required elsewhere.
- **Matrix-vs-text mismatch (ticket 02):** coverage-matrix marks Consensus+as-of `Gap` for
  idea-generation and sector-overview; no textual basis was found in either skill for that. Also
  marks it `Gap` for initiating-coverage, which is directionally right but understates that the
  real need is scoped narrowly to Task 3 peer comps (NTM only), not a Task-1/2/4/5 requirement.

---

### 2. GUIDANCE_FACTS (ERDP-02)

**Skills with explicit textual need:**

| Skill | Cite | What it says |
|---|---|---|
| **earnings-preview** | `SKILL.md:15` | Step 1: "Review the company's **prior quarter** earnings call for any guidance or commentary" — needs the **prior**-quarter guide, not the just-reported one |
| | `:26,55` | "Forward guidance vs. consensus"; catalyst checklist "[Guidance item] — what the buy-side expects to hear" |
| **earnings-analysis** | `SKILL.md:75` | Required sources list: "✅ Prior guidance (from previous quarter's materials)" |
| | `SKILL.md:102` | Checklist: "Guidance changes cite current and prior guidance sources" |
| | `references/report-structure.md:155-160` | Dedicated report page "Guidance & Outlook (1 page)": "What guidance was provided (if any)"; "Comparison to prior guidance"; "Comparison to Street estimates"; "Our assessment of achievability"; "Key assumptions" |
| | `references/report-structure.md:164-170` | Table template: `MANAGEMENT GUIDANCE vs. ESTIMATES / New Guidance / Old Guidance / Change / Street`, e.g. `FY2024E Revenue $XX-XXB $XX-XXB Raised $XX.XB` |
| | `references/report-structure.md:352-357` | Worked citation example: "Management raised FY2024 revenue guidance to $9.8-10.0B from prior $9.5-9.7B²" with footnote "² Q3 2024 Earnings Call, November 7, 2024, CFO prepared remarks … Prior guidance from Q2 earnings call August 8, 2024" — **current AND prior guide, each independently dated/sourced** |
| | `references/workflow.md:300-310` | Step 8 "Guidance Analysis": if provided, "Compare new guidance to prior guidance / Compare to internal estimates and Street estimates / Assess credibility (does company have track record of sandbagging? beating?) / Identify key assumptions"; **if NOT provided: "Note this explicitly / Provide independent outlook based on results and commentary"** |
| | `references/best-practices.md:50` | "❌ Ignoring guidance: If company guides, analyze it thoroughly" |
| | `references/best-practices.md:83-84` | Checklist: "[ ] Guidance changes analyzed and quantified (if provided)"; **"[ ] If no guidance, this is explicitly noted"** |
| | `references/best-practices.md:132-135` | Citation checklist: "Current guidance cited to earnings call transcript or release"; "Prior guidance cited to previous quarter's materials"; "Both current and prior guidance sources hyperlinked" |
| **morning-note** | `SKILL.md:14,17` | Step 1 "Earnings & Guidance": "Guidance changes (raised, lowered, maintained)" |
| | `SKILL.md:70` | Step 3 quick-take table has a `Guidance` row |
| **model-update** | `SKILL.md:14` | Step 1 trigger type: "Guidance change: Company updated forward outlook" — used only as a trigger category; the numeric values then flow into the generic "assumption changes" of Step 3, no guidance-specific field list |
| **initiating-coverage** | `references/valuation-methodologies.md:35` | Revenue-projection step: "Key Considerations: Management guidance and historical growth" (one input among TAM/market-share/competitive dynamics/macro) |
| | `references/valuation-methodologies.md:63` | CapEx assumptions: "Consider industry benchmarks and company guidance" |

**Skills confirmed with no reference:** catalyst-calendar, thesis-tracker, idea-generation,
sector-overview (SKILL.md + references where applicable).

**"Good enough to rely on" — requirement shape:**
- **History depth:** earnings-analysis is the deepest consumer and needs **two data points per
  company per quarter minimum** — current-quarter guidance AND the immediately-prior quarter's
  guidance (guide-vs-guide), each independently dated and sourced. earnings-preview needs the
  **prior**-quarter guide only (it runs *before* the current quarter is reported). morning-note
  and model-update need only the latest single data point / directional change (raised/lowered/
  maintained), no history.
- **Negative case is a first-class, explicitly-required outcome, not an error state.**
  `best-practices.md:84` and `workflow.md:308-310` both require the skill to *explicitly state*
  "company did not guide" when true, and earnings-analysis must then substitute its own
  independent outlook. **This matters directly for GUIDANCE_FACTS' 0-row Apple result noted in
  map.md:14**: a promotion checklist for this product **cannot use "row count > 0" as its pass
  bar** — it needs a way to positively assert "no guidance was issued this quarter" (distinct from
  "extraction failed to find guidance that exists"), because the skill text treats that as a valid,
  required answer. Whether Apple's specific quarter is a true no-guide case or an extraction miss
  is a ticket-04 diagnosis question, not resolved here — but the checklist shape it needs is clear.
- **Grain:** specific numeric ranges with FY/quarter labels (e.g., "$9.8-10.0B"), not
  qualitative-only, for earnings-analysis; directional-only (raised/lowered/maintained) is
  sufficient for morning-note.
- **Source attribution:** mandatory + hyperlinked for earnings-analysis (current AND prior each
  cited separately); not required elsewhere.
- **Scope:** per-request/single-company everywhere it's referenced — no skill needs a
  guidance-values screen across a coverage universe.

---

### 3. EARNINGS_CALENDAR (ERDP-03)

**Skills with explicit textual need:**

| Skill | Cite | What it says |
|---|---|---|
| **catalyst-calendar** | `SKILL.md:12,15` | Step 1: "List of companies to track (tickers or names)" [Required]; "Time horizon (next 2 weeks, month, quarter)" |
| | `:22` | Step 2 "Earnings & Financial Events": "Quarterly earnings date and time (pre/post market)" |
| | `:79` | Important Notes: **"Earnings dates shift — verify against company IR pages and Bloomberg/FactSet closer to the date"** — explicit staleness caveat |
| **earnings-preview** | `SKILL.md:14` | Step 1: "Find the earnings date and time (pre-market vs. after-hours)" |
| | `:61` | Output: "Company, quarter, earnings date" |
| **morning-note** | `SKILL.md:15` | Step 1: "Any coverage companies reporting overnight or pre-market?" |
| | `:51` | "Key Events Today" template: "[Time]: [Company] earnings call" |
| **thesis-tracker** | `SKILL.md:18` | Step 1: "Catalysts: Upcoming events that could prove/disprove the thesis (**earnings**, product launches, regulatory decisions)" |
| | `:44-49` | Step 4 "Catalyst Calendar" — generic `Date/Event/Expected Impact/Notes` table, earnings is one event type among several, no pre/post-market timing field |
| **earnings-analysis** | `references/workflow.md:143` | "Understand Company's Fiscal Calendar" step (fiscal-year mapping, not a calendar *lookup* — it consumes a known release date as input, doesn't source it) |

**Skills confirmed with no reference:** model-update, initiating-coverage, idea-generation,
sector-overview.

**"Good enough to rely on" — requirement shape:**
- **Universe scope:** catalyst-calendar and morning-note need **every ticker in the coverage
  universe**, not per-request — catalyst-calendar explicitly ("List of companies to track");
  morning-note implicitly (must scan "coverage companies reporting overnight" — a daily filter
  over the whole book, not a lookup of one name). earnings-preview and thesis-tracker are
  per-request/single-company.
- **Freshness:** morning-note has the tightest same-day bar — needs to correctly answer "who
  reports today/overnight" for the whole book, every trading day. catalyst-calendar needs a
  rolling multi-week/month/quarter horizon, explicitly caveated as needing **re-verification
  close to the event** ("dates shift"). earnings-preview/thesis-tracker just need the single
  upcoming date for one name to be current as of the request.
- **Grain:** date + a pre-market/after-hours (AM/PM) timing flag is the ceiling requested anywhere
  — catalyst-calendar (:22) and earnings-preview (:14) both ask for exactly this, nothing deeper
  (no exact time-of-day beyond the AM/PM flag is requested in any skill text).
- **History:** none — all four skills that need this want the **next** occurrence only, never a
  past-dates history.
- **Explicit caveat:** catalyst-calendar's "Earnings dates shift — verify … closer to the date"
  (`:79`) is the only skill-stated data-quality caveat for this class; it treats third-party
  calendar sources as provisional and expects a re-check pass, not a single fetch-and-trust.
- **Matrix-vs-text mismatch (ticket 02):** coverage-matrix marks Earnings-calendar `Gap` for
  thesis-tracker — supportable, but the actual need is much shallower than for catalyst-calendar/
  morning-note (generic catalyst-table entry, no AM/PM grain, no universe-wide scan).

---

### 4. TRANSCRIPT_EVENTS (ERDP-04)

**Skills with explicit textual need:**

| Skill | Cite | What it says |
|---|---|---|
| **earnings-analysis** | `SKILL.md:72` | Required sources list: "✅ Earnings call transcript (with date)" |
| | `SKILL.md:91-92` | Sources-section template: "• Earnings Call Transcript (November 7, 2024) [Hyperlink to: https://seekingalpha.com/article/...]" |
| | `SKILL.md:119-134` | Phase 1 mandatory 4-step gate: "2. SEARCH FOR LATEST … 4. CHECK TRANSCRIPT DATE - Verify transcript date matches release date"; "COMMON MISTAKE: Using outdated earnings calls from training data" |
| | `references/workflow.md:153-164` | 🚨 "VERIFY THE DATE ON THE TRANSCRIPT" 🚨 — "The transcript date MUST match the earnings release date from Step 1"; **"If transcript says 'Q2 2023' but release was 'Q3 2024', WRONG transcript obtained"**; named common mistake: "Grabbing an old transcript without checking the date" |
| | `references/workflow.md:195,202` | Mandatory verification checklist: "Earnings call transcript date: _______ (MUST match release date **±1 day**)"; "OPENED actual earnings call transcript and verified date" |
| | `references/workflow.md:212-213` | RED FLAGS (stop conditions): "The transcript date does NOT match the release date"; "Materials show different quarters" |
| | `references/workflow.md:240,244` | Step 6 extraction: "Listen to or read earnings call transcript and note: … Guidance provided (raised, lowered, maintained, introduced?)" — full-text/content use, not just a date pointer |
| | `references/report-structure.md:291-293` | Optional appendix section "Call Transcript Highlights": "Key Q&A excerpts"; "Notable management quotes" — needs quotable text, not just metadata |
| | `references/best-practices.md:148` | "[ ] All earnings materials hyperlinked (release, **transcript**, presentation)" |
| **earnings-preview** | `SKILL.md:15` | Step 1: "Review the company's **prior quarter** earnings call for any guidance or commentary" — never uses the word "transcript," but functionally requires the *content* of the prior-quarter call. This is the sharpest single finding for this product: it is dual-class (feeds both GUIDANCE_FACTS and TRANSCRIPT_EVENTS) **and** it needs the **prior** quarter's call, not the latest — a real requirement TRANSCRIPT_EVENTS' current `PILOT_CIKS={320193}` + latest-only scope cannot satisfy even for Apple once a second quarter of history is needed. |
| **initiating-coverage** | `references/task1-company-research.md:27` | Task 1 data sources: "Company Website & IR: … Earnings transcripts (**last 2-3 quarters**)" — explicit multi-quarter history requirement |
| | `references/task1-company-research.md:75-77` | Step 1 workflow: "Read earnings materials: Latest earnings transcript; Most recent investor presentation; Press releases from last 12 months" |
| | `references/task5-report-assembly.md:438,991` | Sources appendix: "Earnings Calls (with transcript links)" |

**Skills confirmed with no reference:** catalyst-calendar, morning-note (its only "earnings call"
mention, `SKILL.md:51`, is a *calendar* entry — "[Time]: [Company] earnings call" — scheduling
only, not transcript content; the matrix's `Gap` label for morning-note should be read as
schedule-only, not content), model-update, thesis-tracker, idea-generation, sector-overview.

**"Good enough to rely on" — requirement shape:**
- **History depth is the key differentiator across consumers, and it varies sharply:**
  earnings-analysis needs exactly **one** transcript (the just-reported quarter's, date-matched
  ±1 day to the release); earnings-preview needs exactly **one** transcript but it's the
  **prior** quarter's, not the latest; initiating-coverage Task 1 needs **2-3 prior quarters**
  plus explicitly "latest" for the current-materials read. No single "latest transcript only"
  product design satisfies all three shapes.
- **Freshness/correctness bar (earnings-analysis):** exact-quarter match is a hard, checklist-gated
  requirement with a named failure mode ("WRONG transcript obtained") and a bounded tolerance
  (±1 day vs. the earnings release date) — this is the strictest correctness bar found for any of
  the four products in this survey.
  - **Note the implication for `PILOT_CIKS = {320193}` (Apple-only):** even fully correct,
    single-company, latest-quarter transcript data satisfies earnings-analysis and (for the
    *latest* quarter only) part of initiating-coverage Task 1 — it does **not** satisfy
    earnings-preview (needs *prior*-quarter, not latest) or the rest of initiating-coverage Task 1
    (needs 2-3 quarters of history), independent of the universe-breadth question. Ticket 06
    should treat history depth as a second, separate gating dimension from CIK coverage.
- **Grain:** full call text/quotable excerpts needed by earnings-analysis (Q&A excerpts,
  management quotes) and initiating-coverage (transcript links); a transcript *pointer*
  (URL + date, no full text) would satisfy the citation/hyperlink requirement but not the
  content-extraction requirement (guidance language, Q&A highlights) both skills also state.
- **Source attribution:** mandatory, hyperlinked, dated for earnings-analysis; initiating-coverage
  wants transcript links in its sources appendix too.
- **Scope:** single-company, per-request in every skill that needs it — no skill asks for a
  transcript sweep across a coverage universe, so `PILOT_CIKS` breadth is a smaller blocker than
  history depth for the two skills that need more than "latest."
