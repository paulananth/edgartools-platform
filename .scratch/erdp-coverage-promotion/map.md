# ERDP coverage matrix + promotion checklist — wayfinder map

Label: `wayfinder:map`
Repo: **edgartools-platform** only. financial-services (equity-research ER skills) is consulted read-only for what each product must satisfy to be genuinely usable — never written to.

## Destination

A coverage matrix (`.scratch/er-data-plane/coverage-matrix.md`) that accurately reflects the real, pilot-scoped state of ERDP-01…04 (no row left at a stale pre-implementation "Gap"), plus a **product-ready Promotion Checklist** (`ERDP-05-04`) — one entry per ERDP-01…04 product — where each entry's acceptance criteria capture **all critical requirements** for that product to be trustworthy as "Covered" for real ER-skill consumption, not a single minimal proof query. Both informed by what the actual financial-services equity-research skill docs (catalyst-calendar, earnings-preview, morning-note, model-update, earnings-analysis, initiating-coverage, thesis-tracker, idea-generation, sector-overview) currently expect from each data class.

## Notes

- **Domain:** SEC warehouse Gold Explore products (`edgar_warehouse/explore/`) consumed by financial-services equity-research ER skills.
- **Consult each session:** this map; `docs/agents/issue-tracker.md`; `.planning/workstreams/er-data-plane/REQUIREMENTS.md` (ERDP-05-04, ERDP-COV-01/02/03); `.scratch/er-data-plane/coverage-matrix.md` and `map.md` (closed, DESTINATION REACHED — historical reference only, do not reopen); `~/projects/financial-services/plugins/vertical-plugins/equity-research/skills/*/SKILL.md` (read-only).
- **Known pilot-scope facts already gathered (2026-07-27), don't re-derive:** `TRANSCRIPT_EVENTS` is locked to `PILOT_CIKS = {320193}` (Apple only); `EARNINGS_CALENDAR`'s `finnhub` path needs a commercial license (ops gate, not yet cleared); `GUIDANCE_FACTS`'s SEC-8-K path yielded 0 rows against the one real company run so far (Apple) — open question whether 8-K is even the right primary source; `CONSENSUS_ESTIMATES`'s `yahoo` live fetch is a tested parser + network wrapper but not exercised in CI. None of the four are "Covered"-ready at coverage-universe scale today.
- **financial-services skill docs currently don't reference any of these platform products** — `earnings-preview` still says "pull consensus estimates via web search"; `earnings-analysis` treats the transcript as a manually-sourced checklist item. This map does not fix that (would require writing to financial-services); it only uses those docs to learn what each skill actually *needs*.
- **Standing instruction:** never commit/push/PR to `~/projects/financial-services` — read-only for this map and every ticket under it.

## Decisions so far

- [01 — Survey financial-services ER skill requirements per new Explore product](issues/01-survey-er-skill-requirements-per-product.md) — earnings-analysis is the hardest gate on all four products (mandatory dated+hyperlinked source citations, exact-quarter transcript match ±1 day, guide-vs-guide history); GUIDANCE_FACTS' checklist must treat "no guidance issued" as a valid explicit outcome, not a row-count failure; TRANSCRIPT_EVENTS' `PILOT_CIKS={320193}`+latest-only misses earnings-preview (needs *prior*-quarter call) and initiating-coverage (needs 2-3 quarters) on history depth independent of CIK breadth; idea-generation/sector-overview have zero textual basis for their matrix `Gap` cells on Consensus.

## Not yet specified

- Promotion criteria for the pre-existing F1–F12 coverage-matrix footnotes (older Gold/MDM/graph products, e.g. identity, filings metadata, historical financials) — the user's request that triggered this map was specifically about the 4 new Explore products (ERDP-01…04); whether the same "product-ready, all critical requirements" bar should later apply to F1–F12 is a separate, not-yet-scoped question.
- `ERDP-COV-02`/`ERDP-COV-03` (every Gap cell maps to a requirement; spec stays aligned) — likely fall out automatically once the tickets below resolve, but not confirmed.

## Out of scope

- Writing to `~/projects/financial-services` (updating the actual SKILL.md files to reference platform products) — standing repo-boundary instruction, not a scope call for this map specifically.
- Expanding pilot scope (more transcript CIKs, clearing the Finnhub license gate) — an ops/build decision downstream of this map, not a wayfinding decision itself.
- Building automated enforcement of the promotion-checklist acceptance queries — this map defines the criteria; running them is implementation.
