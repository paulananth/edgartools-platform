# Phase 9: MDM And Neo4j Review Metrics - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-05-20T10:47:56Z
**Phase:** 09-MDM And Neo4j Review Metrics
**Areas discussed:** Metric Priority, Missing-edge diagnostics, Source-readiness warnings, Bounded sample detail

---

## Metric Priority

**User's choices:**
- Lead with a coverage snapshot: MDM entity counts, MDM relationship counts, Neo4j node/edge counts, and pending sync totals.
- Organize detailed metrics into MDM Overview, Neo4j Overview, and Graph Coverage.
- Show count plus simple status in the top snapshot.
- Treat sync and coverage gaps as attention-needed signals.
- Show raw counts plus percentages where meaningful.
- Keep MDM metrics usable when Neo4j is unavailable.
- Allow lightweight charts where Streamlit makes them cheap, but do not let charts complicate metric tables.
- Prefer separate refresh per section for MDM, Neo4j, and Graph Coverage.
- Let the agent choose the cleanest Streamlit refresh behavior after implementation research.
- Show last-refreshed timestamps per section.
- Gather metric failures in one warning area.
- Make that warning area grouped: blocking failures first, then non-blocking coverage warnings.
- Allow planners to refine exact labels while preserving structure and meaning.
- Use a hybrid layout: Overview has the snapshot; detailed metrics go into relevant sidebar destinations.
- Demote Phase 8 smoke output once real metrics exist.

**Options considered:**
- Coverage snapshot vs mismatch-first vs MDM-first.
- Three sections vs two sections vs one dense table.
- Count plus status vs counts only vs count plus warning text.
- Sync/coverage gaps vs any zero count vs unavailable sources only.
- Raw counts plus percentages vs raw counts only vs percentages first.
- MDM remains usable vs block metrics view vs hide Neo4j sections.
- Metric cards/tables only vs simple bars vs cheap charts.
- Phase 8 cache pattern vs always-live queries vs separate section refresh.
- Keep global refresh plus section refresh vs replace global refresh vs agent discretion.
- Per-section timestamps vs global timestamp vs no timestamps.
- Inline failures vs one warning area vs both.
- Blocking-only warning area vs all attention signals vs grouped summary.
- Locked labels vs planner-refined labels vs model names directly.
- Existing destinations vs Overview-only vs hybrid layout.
- Demote smoke output vs keep smoke output visible vs remove smoke output.

---

## Missing-edge diagnostics

**User's choices:**
- Start diagnostics with entity-domain coverage: compare company, adviser, person, security, and fund counts first, then edge types.
- Show entity-domain coverage chart-first with side-by-side MDM vs Neo4j bars, backed by a details table.
- Show relationship edge coverage in a per-type table with MDM active count, Neo4j edge count, pending sync count, missing estimate, and coverage percent.
- Define missing estimate as MDM active minus Neo4j edges, clamped at zero when Neo4j has more edges.
- Show all registered active relationship types, including zero-MDM-active rows.
- Warn when Neo4j has more edges than active MDM rows.

**Options considered:**
- Relationship-type coverage vs pending-sync first vs entity-domain coverage.
- Difference table vs status-only summary vs chart-first.
- Per-type table vs grouped status vs only problematic types.
- MDM-active-minus-Neo4j delta vs pending sync only vs separate pending and delta values.
- All registered active types vs only active types vs expected core types.
- Extra graph data warning vs no warning vs separate surplus column.

---

## Source-readiness warnings

**User's choices:**
- Show MDM readiness and graph sync readiness as separate warning groups.
- Treat missing registry data as warning/error, while zero domain counts are informational.
- Warn for pending sync, Neo4j unavailable, lower Neo4j counts, and extra graph data.
- Use three warning levels: error, warning, and info.
- Include short recommended operator action text, without mutation buttons.

**Options considered:**
- MDM readiness vs graph sync readiness vs both.
- Missing essentials only vs any zero core domain vs configurable/separated severity.
- Any pending sync vs large pending only vs pending/unavailable/mismatch.
- Three levels vs two levels vs status labels only.
- Short action text vs no action text vs only errors get action text.

---

## Bounded sample detail

**User's choices:**
- Include counts plus bounded samples for pending sync and missing/extra graph diagnostics.
- Show operator-readable names when available, falling back to IDs.
- Use per-type small limits, such as 5 rows per relationship type, capped globally.
- Prioritize samples by registry order, with oldest rows within each type.
- Do not expose raw properties JSON by default.

**Options considered:**
- Counts plus bounded samples vs counts only vs samples only for pending sync.
- Entity IDs plus relationship type vs operator-readable names when available vs minimal IDs only.
- Small fixed limits vs configurable UI limit vs per-type small limits.
- Oldest pending first vs largest mismatch first vs registry order.
- Hide properties JSON by default vs expandable JSON vs always show raw JSON.

## the agent's Discretion

- Exact Streamlit labels may be refined by the planner while preserving the agreed structure.
- The planner may choose the cleanest refresh control design after implementation research.
- Lightweight charts are optional and should not complicate the core metric tables.

## Deferred Ideas

- Phase 10 owns broader operator polish, richer filters, empty/error state design, and run documentation.
- Managed AWS-facing deployment remains future work.
- Drill-through graph visualization remains future work.
