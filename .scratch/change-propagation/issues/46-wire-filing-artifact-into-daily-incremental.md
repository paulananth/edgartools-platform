# 46 — Wire `filing_artifact`'s gated driver into `daily_incremental`

**What to build:** Per Ticket 10's Decision 4, wire `drive-filing-discovery-for-date`
into `daily_incremental`'s existing schedule/state machine for the
`filing_artifact` family, running alongside the legacy artifact-fetch path so
Ticket 10's Decision 2 (side-by-side production-window diff) becomes
observable for the first time.

**Blocked by:** 10 — Decide baseline, migration, cutover, and rollback
sequencing (resolved)

**Status:** ready-for-agent (split from Ticket 27, 2026-08-27, after
live investigation found the mechanism more delicate than the ticket's
original framing assumed)

## Findings from investigation (do not re-derive these)

- **The daily-index-sealing prerequisite is already satisfied.**
  `daily-incremental`'s own per-date loop
  (`warehouse_orchestrator.py`'s `daily-incremental` branch, ~line 1594)
  calls `_load_daily_index_for_date` for each date in its resolved
  `business_date_start..business_date_end` range — this is the **exact same
  function** `load-daily-form-index-for-date`'s own command handler calls
  (confirmed: both call sites invoke `_load_daily_index_for_date` at
  `warehouse_orchestrator.py:5863`). `stg_daily_index_filing`/
  `sec_daily_index_checkpoint` are already sealed daily in production as a
  side effect of the existing `daily_incremental` schedule. No separate
  sealing step needs to be added — `drive-filing-discovery-for-date` can
  read this immediately for any date `daily_incremental` has already
  processed.
- **`daily_incremental`'s Step Function definition
  (`write_warehouse_mdm_gold_definition` in
  `infra/scripts/deploy-aws-application.sh`) is substantially more complex
  than a simple per-window task call**: SEC-fetch lease acquisition/release,
  identity-refresh lease acquisition, refresh-mode branching
  (`RefreshModeCheck`/`ApplyEffectiveRefreshMode`), deferred-execution
  summaries (`SecFetchDeferred`/`Deferred`), and multiple `Catch` handlers
  releasing leases on failure. This is the same state machine responsible
  for two separate incidents already documented in CLAUDE.md ("Daily
  accession-expansion 5-whys", "Gold-build memory / daily_incremental OOM
  5-whys"). Editing it requires reading the whole flow first, not a quick
  patch.
- **Open design question, not yet resolved:** how does a new
  `DriveFilingDiscoveryForDate` step know which `business_date` to pass?
  `daily-incremental`'s Python command resolves
  `business_date_start`/`business_date_end` *inside* the ECS task at
  runtime (from `get_last_successful_checkpoint_date()`/
  `_latest_eligible_business_date`), not from the Step Function's own
  input — the state machine itself doesn't know the date ahead of time.
  Two candidate mechanisms, not yet chosen:
  1. **In-process**: extract `drive-filing-discovery-for-date`'s core
     per-date logic (manifest build → ledger-gated capture → silver
     acceptance, i.e. the body of
     `_run_daily_index_driven_discovery` minus its own hydrate/publish
     wrapper) into a reusable helper, called directly from
     `daily-incremental`'s own per-date loop using the *same already-open*
     `db`/context — avoids a second hydrate/publish cycle, but means
     editing `daily-incremental`'s own function body (the risk this
     ticket's investigation flagged).
  2. **Separate Step Functions state**: have `daily-incremental`'s ECS
     task's own JSON stdout output (it already prints structured results
     for other purposes) expose the actually-processed `business_date_end`,
     wire it through `ResultSelector`/`ResultPath` into a new task state
     that calls `drive-filing-discovery-for-date` with that date — zero
     changes to `daily-incremental`'s own Python internals, but requires
     confirming the task's stdout is captured this way by the ECS
     integration pattern this state machine uses elsewhere (check how
     `AcquireSecFetchLease`'s `ResultSelector: {"parsed.$":
     "States.StringToJson($.Body)"}` pattern works and whether the same
     applies to a plain `RunTask` result).
- Should be gated behind an explicit, off-by-default execution-input flag
  (e.g. `enable_filing_artifact_gated_capture`), matching this session's own
  established pattern for new, unverified production behavior (see the
  fence-monitor schedule/alarms, also off-by-default) — so deploying the
  updated state machine definition changes nothing until an operator
  explicitly turns it on for the Ticket 10 Decision 2 observation window.

## Acceptance

- [ ] `daily_incremental`'s state machine gains a step invoking
  `drive-filing-discovery-for-date` for the same business date(s) it just
  processed, gated behind an off-by-default flag.
- [ ] The mechanism (in-process vs. separate state) is chosen with an
  explicit rationale, not accidentally by whichever was easier to type.
- [ ] Existing `daily_incremental` behavior (lease acquisition/release,
  refresh-mode branching, deferred summaries) is provably unchanged when
  the new flag is off — a real regression test or architecture test, not
  just "I read the diff."
- [ ] Real live-prod verification with the flag on for at least one
  business date, confirming both paths' outputs can be diffed (Ticket 10
  Decision 2's own requirement) before this ticket can be called done.
