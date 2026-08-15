# Decide Write-Path Command Scope

Type: grilling
Status: resolved
Blocked by: 02

## Question

Five commands run silver's parse → commit write path today:
`WindowedBootstrap` (`load_history` Stage 1), `bootstrap_fundamentals.py`
(Stage 1B), `daily_incremental`, `bootstrap`, `bootstrap-batch`. Inserting
MDM resolution ahead of silver's commit means every in-scope command needs
the new coupling from [Decide the Coupling Mechanism Between MDM and
Silver's Write Path](02-decide-coupling-mechanism.md) wired in — this
ticket decides which commands actually need it now versus later.

The open [Extend Sharded Silver Writes to Primary Ingestion](
../../silver-sharded-writes/map.md) map already narrowed a structurally
similar problem (extending a per-window mechanism to silver's write
surfaces) down to exactly two commands — `WindowedBootstrap` and
`bootstrap_fundamentals.py` — because `daily_incremental`/`bootstrap`'s
default invocation are structurally cross-shard (impacted/active CIKs span
every shard band in one run, not a clean single-window slice) and would
need genuinely new engineering neither command has yet. Weigh whether that
same narrowing applies here: does per-window MDM resolution (this map's
Decisions-so-far: batch-shaped, one window at a time) have the same
cross-window problem for `daily_incremental`/`bootstrap`, or is MDM
resolution's per-window batching independent of the CIK-sharding concern
that drove that other map's narrowing (they're solving different
problems — storage sharding vs. entity resolution timing — so the same
conclusion isn't guaranteed to transfer)? Also decide `bootstrap-batch`'s
status explicitly — it's a secondary reprocessing pipeline (reprocesses
already-loaded bronze, `--artifact-policy skip`, zero new SEC calls) with
its own already-proven sharded write path; does it need MDM-ahead-of-silver
at all, given it isn't new-entity-discovery in the same sense as the other
four?

## Deliverable

A decision: which of the 5 commands are in scope for MDM-ahead-of-silver
(now vs. deferred to a future map, mirroring silver-sharded-writes'
two-surface pattern if applicable), and the specific reasoning per command
that was deferred.

## Answer

**Corrected premise, established before deciding:** the silver-sharded-
writes map's two-surface narrowing does *not* transfer here. Tracing the
actual write path (`_run_submissions_bronze_then_silver`,
`warehouse_orchestrator.py:3085`, calling `_apply_submission_snapshot_to_
silver`, `:4820`, per CIK) found that `bootstrap-next` (WindowedBootstrap),
`bootstrap`, `bootstrap-full`, `daily-incremental`, and `bootstrap-batch`
all funnel through this **one shared function** — they differ only in how
large the `ciks` list is when they call it (`bootstrap-next`: ~500,
externally windowed by Step Functions; `daily-incremental`:
`impacted_ciks` for the day, uncapped; `bootstrap-batch`: an explicit
`cik_list`). The "impacted CIKs span every shard band" constraint that
blocked `daily_incremental`/`bootstrap` for storage-sharding is a
storage-sharding-specific concern (single-owner-per-shard) — MDM's
candidate pool lives in its own Postgres, not CIK-sharded silver storage,
so that blocker doesn't apply to MDM-ahead-of-silver at all.

**Scope: four of five, uniformly — `bootstrap-next`, `bootstrap`,
`bootstrap-full`, `daily-incremental`.** Insert MDM resolution once,
around the shared `_run_submissions_bronze_then_silver` call — every
command that reaches it gets the coupling for free, with no per-command
engineering beyond that single insertion point. `daily-incremental`'s
uncapped batch size is a real but bounded tail risk (per ticket 01's
adviser/fund unscoped-prefetch cost) — one call per day, not repeated
hundreds of times sequentially like `load_history`'s ~124 windows, so the
cost-multiplication concern that motivated flagging it doesn't actually
compound the way it would for a windowed command.

**`bootstrap-batch` excluded.** It's a secondary reprocessing pipeline
(CLAUDE.md: "reprocesses already-loaded bronze... zero new SEC calls") —
its records already went through MDM resolution during their original
ingestion via one of the other four commands, so re-resolving here is
redundant, not new-entity discovery. This also sidesteps a genuine new
correctness risk unique to this command: it runs at `MaxConcurrency=3`
(up to 3 calls to the shared write site execute concurrently), and
two-phase resolution's backfill INSERT/UPDATE could race if two
concurrent batches both try to resolve the same adviser/security/CIK at
once — a hazard that doesn't exist for the other four, which never run
concurrently with each other today. Not ruled out forever if
`bootstrap-batch`'s role ever changes — just out of scope for this map,
consistent with it not needing fresh entity resolution today.
