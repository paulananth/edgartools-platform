# 02 — Reclassify the 4 stale Gap rows in the coverage matrix

Type: grilling
Status: resolved
Blocked by: 01

## Question

`.scratch/er-data-plane/coverage-matrix.md` still marks **Transcript**, **Guidance values**, **Consensus + as-of**, and **Earnings calendar date/time** as **Gap** for every applicable ER skill column, even though ERDP-04/02/01/03 now exist as real platform products. Given the pilot-scope limits already known (see this map's Notes) and ticket 01's skill-by-skill requirements survey, what should each of the 4 rows' cells become — stay Gap, move to Partial, or (for any skill where the pilot scope genuinely already satisfies that skill's stated needs) move straight to Covered — and does the answer differ per skill column rather than being uniform across the row?

## Answer

Applied directly to `.scratch/er-data-plane/coverage-matrix.md` (new footnotes F16–F19). No cell reached **Covered** — none of the four products yet pass their own ERDP-05-04 promotion checklist (CONSENSUS_ESTIMATES has zero promoted rows in prod as of ticket 03; GUIDANCE_FACTS yielded 0 rows on its one real run; EARNINGS_CALENDAR's `finnhub` path is license-gated; TRANSCRIPT_EVENTS is single-CIK).

**Mechanical reclassification (13 cells, no judgment call):** every `Gap` cell with a real textual need found in ticket 01, and a real platform product now backing it, moved to `Partial` — the matrix's own definition ("platform product exists with useful fields, but ER-complete contract missing"). Applies across Consensus + as-of (6 cells), Guidance values (5 cells), Earnings calendar date/time (4 cells), Transcript (2 cells: earnings-preview, earnings-analysis).

**3 corrections (confirmed with the user):**
1. **Consensus + as-of, idea-generation + sector-overview: Gap → N/A.** Ticket 01 found zero textual basis in either skill for consensus data — no real need to leave labeled Gap or promote to Partial.
2. **Transcript, morning-note: Gap → N/A.** morning-note's only "earnings call" mention is a scheduling entry, already covered by the separate Earnings-calendar row — not a distinct transcript-content need.
3. **Transcript, initiating-coverage: N/A → Partial.** Ticket 01 found a real, previously-missed need (`references/task1-company-research.md:27`, "earnings transcripts (last 2-3 quarters)") — the matrix undercounted this cell.

Final rows:
- `Transcript`: `N/A | Partial | N/A | N/A | Partial | Partial | N/A | N/A | N/A`
- `Guidance values`: `N/A | Partial | Partial | Partial | Partial | Partial | N/A | N/A | N/A`
- `Consensus + as-of`: `Partial | Partial | Partial | Partial | Partial | Partial | N/A | N/A | N/A`
- `Earnings calendar date/time`: `Partial | Partial | Partial | N/A | N/A | N/A | Partial | N/A | N/A`

Columns in order: catalyst-calendar, earnings-preview, morning-note, model-update, earnings-analysis, initiating-coverage, thesis-tracker, idea-generation, sector-overview.
