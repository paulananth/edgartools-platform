# Bootstrap-Fundamentals Crash-Resume

## Destination

Every per-CIK write loop in `bootstrap-fundamentals`'s Branch B modes
(`entity-facts`, `per-filing`, `thirteenf`) durably records per-CIK
completion in `BookkeepingStore` (Postgres) as it happens, so a retry of
the same task/window resumes from the next un-recorded CIK instead of
re-processing the whole window from its starting offset. Reaching the
destination means: a mid-task crash (OOM or otherwise) partway through a
CIK window no longer re-pays the full window's SEC-fetch/parse cost on
retry.

## Notes

This effort **carries execution into the map**, per wayfinder's override —
the root cause and fix locus are already concretely identified (see
Decisions so far), so tickets here are build slices, not open decisions,
except where noted `grilling`.

- Consult `/gof-refactor-reviewer` before any production-code edit
  (CLAUDE.md hard rule).
- Run the full 3-axis `/code-review` (Standards/Spec/GoF) before any PR is
  ready (CLAUDE.md hard rule).
- Relevant existing prior art to model against, not reinvent:
  the mdm-relationship-versioning-gap map's resumable cursor/watermark
  (`.scratch/mdm-relationship-versioning-gap/`) — a persisted,
  resumable cursor decoupled from a "sweep complete" watermark, for the
  identical "capped run can't make forward progress" shape in a different
  subsystem.
  release-readiness Ticket 74's manifest/outcome-status resume check
  (`.scratch/release-readiness/issues/74-daily-incremental-permanent-terminal-repair-block.md`)
  — a narrower, already-shipped precedent for "read a prior attempt's
  progress before redoing expensive work," in `daily_incremental` specifically.
- Adjacent, NOT this effort: fundamentals-daily-integration map's Phase
  3/Ticket 04 (wiring these same 3 modes into `daily_incremental` for the
  first time) touches the same code area but is a different destination
  (new capability, not resumability). Sequence-aware, not blocking either
  way — check for conflicts before either lands.

## Decisions so far

- [Design the per-CIK durability mechanism](issues/01-design-per-cik-durability-mechanism.md) — the marker moves into `BookkeepingStore`/Postgres (cheap per-row commits), not periodic re-upload of the local SilverDatabase file (cost scales with file size x flush count, and fights the post-DuckDB-retirement direction where Postgres bookkeeping is already the durable source of truth for tracking state). Decided 2026-09-12.

## Not yet specified

- Whether this generalizes to `run_bootstrap_fundamentals_per_filing`/
  `run_bootstrap_thirteenf` (near-certain yes, same entry point and
  end-of-task publish shape as `entity-facts`, but each mode's own
  skip-check semantics need individual confirmation before assuming the
  fix ports unchanged).
- Whether `load_history`'s Branch A (`bootstrap-next`) shares the identical
  local-db-buffered-then-published-once shape — it writes to the same
  `silver.duckdb` convention, so plausibly yes, not yet investigated.
- Whether `daily_incremental`'s own per-CIK submission loop (which already
  got a "batch once, not per-CIK" throughput fix on 2026-09-04 — see
  CLAUDE.md's "daily_incremental per-CIK checkpoint round trips" entry) has
  the same crash-fragility this map is fixing, or whether Ticket 74's
  coarser manifest-based resume already covers it adequately for that
  command specifically.
- How the new per-CIK marker interacts with `has_companyfacts_at_version`'s
  existing "one-time-per-parser-version" skip check (Ticket 03 of the
  duckdb-retirement-cutover/fundamentals-daily-integration lineage) — same
  concept extended, or a genuinely separate mechanism answering a
  different question ("done this run" vs. "done ever at this parser
  version")?

## Out of scope

<!-- none yet -->
