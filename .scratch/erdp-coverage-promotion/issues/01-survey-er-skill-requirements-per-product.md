# 01 — Survey financial-services ER skill requirements per new Explore product

Type: research
Status: claimed
Blocked by:

## Question

For each of the four new Explore products — `CONSENSUS_ESTIMATES` (ERDP-01), `GUIDANCE_FACTS` (ERDP-02), `EARNINGS_CALENDAR` (ERDP-03), `TRANSCRIPT_EVENTS` (ERDP-04) — survey every financial-services equity-research skill (`catalyst-calendar`, `earnings-preview`, `morning-note`, `model-update`, `earnings-analysis`, `initiating-coverage`, `thesis-tracker`, `idea-generation`, `sector-overview`; `~/projects/financial-services/plugins/vertical-plugins/equity-research/skills/*/SKILL.md`, read-only) that touches that data class, and report:

- Which skills actually reference/need this data class, and in what form (exact fields, grain, freshness expectations) — quote the relevant workflow steps.
- What "good enough to rely on" looks like from the skill's own workflow (e.g. does it need every ticker in a coverage universe, or is per-request lookup fine? Does it need same-day freshness or is week-old acceptable? Does it need history or just latest?).
- Any explicit skill-stated caveats about estimate/guidance/calendar/transcript data quality (e.g. earnings-preview's note that "consensus estimates change — always note the source and date").

Report findings grouped by product (4 sections), each listing the skills that need it and the concrete requirements extracted. This survey directly feeds tickets 02–06 (matrix reclassification + per-product promotion checklists) — write findings so each of those tickets can be resolved by reading this ticket's answer plus its own product-specific detail, not by re-reading all 9 skill docs from scratch.
