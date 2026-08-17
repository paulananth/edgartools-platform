# Decide the Coupling Mechanism Between MDM and Silver's Write Path

Type: grilling
Status: resolved

## Question

Today, silver's write path (parse → silver DB commit, run by 5 different
commands: `WindowedBootstrap`, `bootstrap_fundamentals.py`,
`daily_incremental`, `bootstrap`, `bootstrap-batch`) has zero runtime
dependency on MDM — MDM (Stage 2) only reads silver after it's complete.
Moving MDM's resolution ahead of the silver commit introduces a new
runtime coupling that didn't exist before, and the map's first grilling
round didn't reach a decision on its shape — the user flagged
"silver will eventually move to snowflake" as a note rather than picking
an option, meaning the decision needs to account for the target
architecture, not just today's DuckDB flow.

Two shapes were on the table and neither was picked:

- **Synchronous/blocking**: parse → MDM resolve (blocking call) → silver
  commit. Simplest mental model (every committed row has a real
  `mdm_entity_id`), but couples silver's write availability to MDM
  Postgres's availability/latency for every write path this applies to.
- **Two-phase/decoupled**: parse → silver commit with `mdm_entity_id =
  NULL` → MDM resolves shortly after → `UPDATE` silver to backfill the
  column. Keeps silver's write path decoupled from MDM's availability, at
  the cost of `mdm_entity_id` being transiently NULL after commit (softens
  "ahead of silver" into "very shortly after, decoupled").

Resolve with the Snowflake migration explicitly in view: the closed
[silver-snowflake-migration](../../silver-snowflake-migration/map.md) map
already committed to an append-only Snowflake landing zone (parse →
`INSERT` into `EDGARTOOLS_SILVER_LANDING`, collapsed to current-state by
dbt) as silver's eventual architecture, live in prod today for the
ingestion path (though gold isn't cut over to read it yet — see that map's
Ticket 07 and this session's silver ER diagram). Does the coupling
mechanism decided here still make sense once "silver DB commit" means "an
`INSERT` into an append-only Snowflake table processed later by dbt,"
rather than today's DuckDB `merge_candidate_into_canonical` call? A
synchronous-blocking design bolted onto today's DuckDB flow might need to
be redesigned entirely once that migration's ingestion path is the actual
target — worth deciding now whether this map's answer should be written
for DuckDB-today, Snowflake-landing-zone-eventually, or both.

## Deliverable

A decision: which coupling shape (or a third option), and how it's meant
to interact with — survive, or be superseded by — the silver-on-Snowflake
migration's landing-zone architecture.

## Answer

**Two-phase / decoupled**, applied uniformly to both targets from a single
coupling point.

**Shape:** parse writes a row with `mdm_entity_id = NULL` immediately, to
whichever destination(s) are in scope. MDM resolves that window's batch
shortly after, then re-emits — for the Snowflake landing zone, a second
`INSERT` of the same row carrying the real `mdm_entity_id`, keyed by the
same business key; dbt's existing latest-`parse_sequence`-wins collapse
(already how the landing zone resolves any repeated write for the same
key) picks it up with no new mechanism. For DuckDB silver, the analogous
backfill is an `UPDATE` (the append-only-INSERT model is landing-zone-
specific; DuckDB already has row-level UPDATE as a normal operation via
`silver_protection.py`'s existing merge path). No new capability needs
building in the landing zone at all — it already has everything this
needs. **Rejected:** synchronous/blocking, because it would make every
in-scope write path's forward progress depend on MDM Postgres's live
availability and latency, a runtime coupling that doesn't exist today and
that two-phase avoids entirely.

**Target scope:** both, uniformly, from one coupling point. Parse already
fans out in-process to DuckDB silver and the Snowflake landing zone in
parallel (confirmed in this session's pipeline diagram — "same parse,
parallel write"); MDM resolution is inserted once, upstream of that
fan-out, and both destinations' rows carry the same `mdm_entity_id` from
the same resolution call. No separate DuckDB-specific and Snowflake-
specific coupling designs.

**Carried forward from [Confirm Match Candidate-Prefetch Behavior](
01-confirm-match-candidate-prefetch-behavior-under-per-window-batching.md)**,
which resolved in parallel with this ticket: company/person/security
resolution already does live per-row Postgres queries today, so per-window
two-phase resolution costs them nothing extra. Adviser/fund resolution
does an unscoped full-table prefetch today and — separately —
`run_advisers`/`run_funds` have no CIK-scoping parameter at all yet. Both
facts belong to [Decide Write-Path Command Scope](
03-decide-write-path-command-scope.md), not this ticket: whether adviser/
fund resolution is even ready to participate in per-window two-phase
resolution as currently built is a scope question, not a coupling-shape
question — the coupling shape decided here (two-phase, uniform) applies to
whichever entity types that ticket puts in scope.
