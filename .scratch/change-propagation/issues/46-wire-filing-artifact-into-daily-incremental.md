# 46 — Wire `filing_artifact`'s gated driver into `daily_incremental`

**What to build:** Per Ticket 10's Decision 4, wire `drive-filing-discovery-for-date`
into `daily_incremental`'s existing schedule/state machine for the
`filing_artifact` family, running alongside the legacy artifact-fetch path so
Ticket 10's Decision 2 (side-by-side production-window diff) becomes
observable for the first time.

**Blocked by:** 10 — Decide baseline, migration, cutover, and rollback
sequencing (resolved)

**Status:** partial (2026-08-27) — the in-process wiring, gating, and
regression proof are done and merged; live-prod verification (acceptance
bullet 4) has not happened yet and needs its own deploy + one-off run.

## Answer

**Mechanism chosen: in-process, not a separate Step Functions state.**
`advisor()` surfaced the load-bearing reason before any code was written:
`drive_discovery_manifest` makes real SEC network fetches, and
`daily_incremental`'s ASL already wraps its whole `RunWarehouseTask` step in
the cross-command `sec_fetch_active` lease (`AcquireSecFetchLease` →
`RunWarehouseTask` → `ReleaseSecFetchLease`, confirmed live in
`write_warehouse_mdm_gold_definition`). Running the gated capture in-process
means it executes strictly inside that lease window for free. A separate
Step Functions state has no good answer here: a new state after
`ReleaseSecFetchLease` would fetch SEC data unleased (racing a concurrently
running `bootstrap`/`daily_incremental`, exactly what the lease exists to
prevent), and a state inserted before the release means editing the
lease/`Catch` region itself — the precise fragility this ticket was split
out to avoid touching. In-process also reuses daily-incremental's own
already-open Silver connection and MDM engine (no second hydrate/publish
cycle) and needed **zero changes to the Step Functions ASL** — confirmed by
checking how `write_warehouse_mdm_gold_definition` builds daily_incremental's
ECS command array first: it's a static `States.Array(...)` expression (plus
one existing cik_list Choice branch), so a second independent boolean would
have needed either nested Choice states or a default-injection Pass state —
real, working precedent exists for this (`RunWarehouseTaskWithCikList`), but
none of it was needed because the flag can simply never be threaded from
Step Functions input at all for v1.

**Acceptance bullet 1 is satisfied by a materially different but equivalent
mechanism than its literal wording assumed** (written before the mechanism
was chosen): instead of the state machine gaining a new Task state,
`daily-incremental`'s own command handler (`_capture_bronze_raw`'s
`daily-incremental` branch, `warehouse_orchestrator.py`) gains a call to
`_run_filing_artifact_gated_capture`, gated behind a new off-by-default CLI
flag (`--enable-filing-artifact-gated-capture`, default `False`). The ASL
never passes this flag today, so every real scheduled run is provably
unaffected without any state-machine redeploy — turning it on for the
Decision 2 verification window is a manual one-off `ecs run-task` command
override, the same pattern this repo already uses for
`backfill-mdm-entity-ids` (see CLAUDE.md's "MDM Postgres migration-011"
entry). This is a deliberate amendment to the bullet's wording, not a silent
divergence — recorded here as the map's own convention requires.

**Scoping decision, also from `advisor()`:** `daily-incremental` defaults
`--recurring-index-lookback-days` to 7, so a bare on/off flag would fan out
to seven gated-capture calls per run on a task with two documented OOM/
expansion incidents in CLAUDE.md. The gated capture runs **once per
daily-incremental invocation, for `business_date_end` only** — not for
every date the recurring loop just sealed — and is skipped outright if the
loop's own `sync_status` came back `"partial"` (nothing new was actually
sealed to drive discovery from in that case).

**Failure isolation, also from `advisor()`:** this is a new, unverified
side channel riding inside a task with a `MaxAttempts: 3` retry budget it
must never consume on its own account. `_run_filing_artifact_gated_capture`
raises normally (including a real `UnsupportedDiscoveryPolicy` if the
registry is misconfigured); the caller in `_capture_bronze_raw` catches
*any* exception and folds it into
`metrics["filing_artifact_gated_capture"] = {"status": "error", "error":
...}` instead of propagating. This does **not** weaken the "fails closed"
resolution in the Daily accession-expansion 5-whys (CLAUDE.md) — that gate
covers `daily_incremental`'s own accession expansion/retry/circuit
behavior; this is a new, independent, off-by-default path riding on top
of an otherwise-unchanged run, and isolating its failures is the whole
point of a side-by-side verification window that hasn't earned trust yet.

**Correction (`/code-review`'s Spec pass, 2026-08-27):** earlier drafts of
this Answer and the surrounding code comments called this an
"observation-only side channel." That's wrong about the success path —
failure isolation only isolates *failures*. A **successful** gated-capture
call is not passive: `run_gated_discovery_for_business_date` (shared by
this path and the standalone CLI command) calls
`SourceRegistryLedger.record_catchup_progress` on a completed interval,
same as it always has — the real signal Ticket 27's removal-evidence
bullets gate on. Turning the flag on for the Decision 2 verification window
deliberately advances that state for `filing_artifact`, which is the
correct and intended effect (proving the family out is the whole point),
but "observation-only" undersold it. Comments/docstrings/CLI help text
corrected to say this explicitly.

**Implementation:**
- `edgar_warehouse/application/workflows/drive_filing_discovery.py`:
  extracted `_run_daily_index_driven_discovery`'s discovery → ledger-gated
  capture → Silver-acceptance body (previously inline) into a new shared
  function, `run_gated_discovery_for_business_date` (returns a
  `GatedDiscoveryOutcome` dataclass), so both this module's own CLI
  entrypoints and the new in-process caller share one implementation. Proven
  behavior-identical: all 19 pre-existing tests in
  `test_drive_filing_discovery_command.py`/`test_drive_adv_filing_discovery_command.py`/
  `test_acquisition_command_registration.py` pass unchanged against the
  refactor (a characterization test, not a new one).
  New `run_filing_artifact_gated_capture_for_business_date` wraps that core
  for the `filing_artifact` family specifically — takes an already-open
  `db`, does no hydrate/publish/manifest-writing of its own, raises on
  failure (failure isolation is the caller's job, not this function's).
- `edgar_warehouse/application/warehouse_orchestrator.py`: new
  `_run_filing_artifact_gated_capture` module-level dispatcher (local import
  of `drive_filing_discovery`, breaking the module cycle — that module
  imports `_build_warehouse_context`/`_hydrate_silver_database_from_storage`/
  `_publish_silver_database_with_retry` from this one at its own module
  level; matches this file's existing local-import convention for
  command-branch-specific dependencies). The `daily-incremental` branch of
  `_capture_bronze_raw` calls it under the gate/isolation logic described
  above.
- `edgar_warehouse/cli.py`: new `--enable-filing-artifact-gated-capture`
  flag on the `daily-incremental` subparser, default `False`. Picked up
  automatically by `_namespace_to_payload`'s `vars(args)` — no separate
  plumbing needed.

**Diffability (Ticket 10 Decision 2's own requirement), verified real, not
just assumed:** `SourceFetchDecisionRecord.candidate_id` is deterministic
and business-date-prefixed (`filing-discovery/<business_date>/<accession>`
for `filing_artifact`'s legacy format) — proven queryable in
`tests/application/test_daily_incremental_gated_capture_integration.py` via
a plain `candidate_id LIKE 'filing-discovery/<date>/%'` filter against the
real acquisition ledger. This is the mechanism for the operator running the
Decision 2 window to diff the gated path's ledger rows against the legacy
artifact-fetch path's own Silver output for the same date — no new query
API was needed.

**Tests:**
- `tests/unit/test_daily_incremental_gated_capture.py` (5 tests, all mocked
  at the dispatcher boundary, mirroring `test_discovery_checkpoint.py`'s own
  `_capture_bronze_raw`-direct-call convention): off-by-default leaves
  metrics/behavior unchanged; runs once for `business_date_end` when
  enabled; stays scoped to one call across a 7-day recurring window; a
  raised exception is isolated into `metrics` without failing the command;
  skipped when the daily-index load itself came back partial.
- `tests/application/test_daily_incremental_gated_capture_integration.py`
  (1 test): the real end-to-end path — real SQLite acquisition ledger, real
  `SilverDatabase`, mocked only at the SEC network edge (mirrors
  `test_drive_adv_filing_discovery_command.py`'s fixture shape) — proves the
  wrapper genuinely captures a filing without doing its own hydrate/publish,
  and proves the diffability query above against real ledger rows.
- `tests/unit/test_discovery_checkpoint.py`: 2 new CLI-parsing tests for the
  new flag's default and explicit-enable cases.

Full repo suite green (`uv run pytest`, background run, see this session's
own log) alongside the 671 targeted tests above.

**Not yet done — acceptance bullet 4, honestly left open:** no image has
been built/pushed and no live-prod one-off run has happened yet. This needs
its own follow-through: rebuild+push the warehouse image (this ticket only
touched `edgar_warehouse/**` outside `mdm/`, so warehouse-only per CLAUDE.md's
rebuild table — no MDM image, no Step Functions redeploy needed since the
ASL was never touched), then a manual `ecs run-task` override adding
`--enable-filing-artifact-gated-capture` to a real `daily-incremental`
invocation for one business date, then the diff described above.

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

- [x] `daily_incremental`'s command handler gains a call running
  `filing_artifact`'s gated discovery/capture for the business date it just
  processed, gated behind an off-by-default flag. (Satisfied via an
  in-process call, not a new state machine Task state — see Answer for the
  explicit rationale and why this amends the bullet's original wording.)
- [x] The mechanism (in-process vs. separate state) is chosen with an
  explicit rationale, not accidentally by whichever was easier to type.
- [x] Existing `daily_incremental` behavior (lease acquisition/release,
  refresh-mode branching, deferred summaries) is provably unchanged when
  the new flag is off — a real regression test, not just "I read the diff."
  (Also: zero ASL changes at all, so the lease/refresh-mode/deferred-summary
  machinery this bullet worries about was never touched in the first
  place.)
- [ ] Real live-prod verification with the flag on for at least one
  business date, confirming both paths' outputs can be diffed (Ticket 10
  Decision 2's own requirement) before this ticket can be called done.
