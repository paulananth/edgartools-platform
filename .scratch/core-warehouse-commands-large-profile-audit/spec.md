Status: ready-for-agent

Parent: [Ticket 02 — Audit bootstrap-full/targeted-resync/full-reconcile/bootstrap/daily-incremental/bootstrap-next for the unscoped-load shape](../large-profile-unscoped-load-audit/issues/02-audit-core-warehouse-commands-large-profile.md), a child of the [Large-profile unscoped-load audit](../large-profile-unscoped-load-audit/map.md) wayfinder map.

## Problem Statement

Tonight, a live production Step Functions execution OOM-killed on the
`MdmRun` state because `GraphSyncEngine.prime_relationship_type` loaded
every active MANAGES_FUND relationship row (563,631 rows, ~2GB of ORM
objects) into memory before the code knew which advisers the run actually
needed — an unscoped full load of a shared table before scoping is known.
The same shape was found and pre-emptively fixed for INSTITUTIONAL_HOLDS.

Six commands (`bootstrap-full`, `targeted-resync`, `full-reconcile`,
`bootstrap`, `daily-incremental`, `bootstrap-next`) all run on the `large`
Fargate profile and funnel through shared `warehouse_orchestrator.py` code
paths. Most of their known OOM history is already fixed by other, already-
resolved maps (gold-build-memory-reliability's streaming fix,
task-profile-consolidation's sizing fixes, the artifact-throttle and
bronze-recovery 5-whys) — but none of those fixes targeted *this specific*
shape (unscoped ORM/DB hydration before scoping), and one concrete,
previously-unaudited instance of it was found while writing this spec:
`edgar_warehouse/mdm_entity_backfill.py`'s `_fetch_pending_rows()` runs
`SELECT * FROM {table} WHERE mdm_entity_id IS NULL` against 6 Snowflake
silver tables and calls `cursor.fetchall()` unconditionally — no `LIMIT`,
no pagination, no per-run scoping — on every `daily_incremental`/
`bootstrap` execution. In steady state this stays small (most rows are
already resolved day to day), but nothing bounds it if resolution ever
falls behind or a large backfill leaves a big pending set — the exact
"safe until it isn't" shape MANAGES_FUND had.

The shared bronze/silver capture path itself
(`_run_submissions_bronze_then_silver`, the one function all 6 commands'
submission-processing funnels through) has never been formally checked for
this shape either — it already takes a caller-bounded `ciks` list, but
whether anything it calls loads some *other* shared dataset unscoped
(rather than filtered to that bounded CIK set) is an open question.

## Solution

Audit both the confirmed finding and the broader shared capture path
against the MANAGES_FUND shape, using real measured evidence (row counts,
table sizes) rather than estimates. Fix the confirmed
`mdm_entity_backfill.py` gap using the same pattern MANAGES_FUND and
INSTITUTIONAL_HOLDS were fixed with: batch-scope the read, process a
bounded amount at a time, add a red-before-green regression test. Audit
`_run_submissions_bronze_then_silver` and what it calls for the same
shape; fix any genuine gap found the same way, or record a clean bill of
health with the evidence checked if none is found.

## User Stories

1. As the platform operator, I want `mdm_entity_backfill.py`'s
   `_fetch_pending_rows()` to read pending rows in bounded batches (e.g.
   CIK-range chunks, mirroring INSTITUTIONAL_HOLDS's CIK-range batching)
   instead of one unbounded `SELECT * ... WHERE mdm_entity_id IS NULL` per
   table, so a large pending backlog (a fresh table added to
   `MDM_ENTITY_ID_TABLES`, resolution falling behind, a big backfill) can't
   reproduce the MANAGES_FUND OOM on `daily_incremental`/`bootstrap`.
2. As the platform operator, I want real, current row counts for each of
   the 6 tables' `mdm_entity_id IS NULL` pending set measured against live
   Snowflake before concluding how urgent this fix is — not an assumption
   that "it's probably fine because it usually resolves fast."
3. As the platform operator, I want `_lookup_entity_ids`'s existing
   500-row chunking (the Postgres-side lookup, already correctly bounded)
   left untouched — this ticket is about the unbounded Snowflake-side read
   in `_fetch_pending_rows`, not the already-correct Postgres side.
4. As the platform operator, I want `_run_submissions_bronze_then_silver`
   and everything it calls (`_capture_submission_bronze_snapshots`, the
   downstream silver-write path) audited for whether anything loads a
   shared table/dataset unscoped rather than filtered to the caller's
   bounded `ciks` list — the function itself is already CIK-scoped by its
   signature, so the risk (if any) is one level deeper.
5. As the platform operator, I want each of the 6 commands' actual call
   site into `_run_submissions_bronze_then_silver` checked for whether it
   passes a genuinely bounded `ciks` list in practice, not just in
   signature — e.g. confirming `bootstrap-full`/`full-reconcile` (which
   sound universe-wide by name) don't defeat the function's own scoping by
   passing an unbounded list every time.
6. As a future engineer, I want a written record distinguishing "already
   covered by an existing resolved map" from "genuinely new finding" for
   each of the six commands, so nobody re-investigates the same OOM
   history gold-build-memory-reliability/task-profile-consolidation
   already closed.
7. As a future engineer, I want any fix built here to follow the exact
   pattern already proven twice tonight (batch by natural key, release
   each batch's state before the next, red-before-green regression test),
   so this codebase doesn't accumulate a third, slightly different variant
   of the same fix.
8. As a future engineer, I want any genuinely new risk found outside
   `mdm_entity_backfill.py` and `_run_submissions_bronze_then_silver`
   (e.g. inside a specific command's own pre/post-processing) to graduate
   into its own ticket on the parent map, per wayfinder's fog-of-war
   convention, rather than be folded into this one.
9. As the on-call operator, I want to know whether the
   `mdm_entity_backfill.py` gap is already live-risky at today's data
   volumes or a pre-emptive fix (like INSTITUTIONAL_HOLDS was), so I know
   whether to treat this as urgent or routine.

## Implementation Decisions

- **Two seams** (confirmed with the user before writing this spec):
  - **`mdm_entity_backfill.py`**: `backfill_pending_rows(connection,
    session, landing_export)` — the existing entry point
    `tests/mdm/test_entity_backfill.py` already tests, using its existing
    `_FakeConnection`/`_FakeCursor` test doubles (mimicking
    snowflake-connector-python's `.description`/`.fetchall()` cursor
    shape). This is the single, already-correct seam for the confirmed
    finding.
  - **Bronze/silver capture path**: `_run_submissions_bronze_then_silver`
    (`edgar_warehouse/application/warehouse_orchestrator.py`) — the one
    function all 6 commands' submission processing funnels through (6 call
    sites), already exercised by `tests/unit/test_discovery_checkpoint.py`,
    `test_submission_phase_order.py`, `test_batch_silver_resume.py`, and
    `test_submissions_fetch_concurrency.py`.
- **`mdm_entity_backfill.py` fix pattern, if the audit confirms the risk
  is real at some plausible scale**: replace `_fetch_pending_rows`'s
  unbounded `SELECT * FROM {table} WHERE mdm_entity_id IS NULL` with a
  CIK-range-batched read (mirroring INSTITUTIONAL_HOLDS's
  `_INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE`-style `WHERE ... AND cik BETWEEN ?
  AND ?` pagination) — every one of the 6 target tables in
  `MDM_ENTITY_ID_TABLES` is CIK-keyed (directly or via a joined filing),
  so CIK-range batching is the natural key here, same as it was for
  INSTITUTIONAL_HOLDS. `backfill_pending_rows` should process one CIK
  range at a time, writing each batch's resolved rows to `landing_export`
  before moving to the next, rather than materializing every pending row
  across all 6 tables before writing anything.
- **`_run_submissions_bronze_then_silver` audit**: this function already
  takes a caller-bounded `ciks: list[int]` — confirm each of the 6
  commands' call sites (lines ~1614, 1681, 1711, 1751, 2278, 3227 as of
  this spec's writing, subject to drift) actually pass a bounded list in
  practice (windowed for `bootstrap-next`, daily-impacted-only for
  `daily-incremental`, etc.), not an unbounded full-universe list that
  would defeat the function's own scoping. Then check
  `_capture_submission_bronze_snapshots` and the downstream silver-write
  path it calls for any load of a *different* shared dataset (not the CIK
  list) that isn't itself filtered to the current run's scope.
- **No changes to any of the 6 commands' Step Functions definitions**
  (task profile, retry/timeout config, windowing strategy) are in scope —
  this ticket is about the Python-level load shape inside each command's
  shared code paths, not the orchestration around them.
- **A clean bill of health is a valid outcome** for
  `_run_submissions_bronze_then_silver` — if the audit confirms every call
  site is genuinely bounded and nothing unscoped is loaded downstream,
  record that explicitly with the evidence checked (which call sites, what
  each passes) rather than treating "no fix needed" as incomplete.

## Testing Decisions

- The `mdm_entity_backfill.py` fix (if built) must be proven **red without
  the fix** first — reproduce the current unbounded-read behavior with a
  `_FakeConnection`/`_FakeCursor` seeded with a pending set spanning
  multiple CIK ranges, and a spy or count on how many rows are fetched per
  `cursor.execute()` call. Green after the fix means the fetch is
  demonstrably chunked (multiple bounded `execute()` calls, not one), and
  the resolved-row counts and `landing_export` contents match the
  pre-fix single-pass behavior exactly (no correctness regression, only a
  memory-shape change) — mirroring
  `test_backfill_pending_rows_resolves_matched_and_leaves_unmatched_out`'s
  existing assertion style.
- Assert on the **scoping being real**, not just that the code runs —
  same discipline as tonight's MANAGES_FUND/INSTITUTIONAL_HOLDS tests:
  multiple bounded reads, each covering a disjoint CIK range, together
  covering every pending row.
- For `_run_submissions_bronze_then_silver`, if the audit finds a genuine
  gap, add a test at the same seam the 4 existing test files already use
  for this function — do not introduce a new, lower-level seam without
  first exhausting whether the existing ones can express the finding.
- If either seam's audit concludes no fix is needed, no new test is
  required, but the evidence checked (row counts, which call sites were
  inspected and what they pass) must be recorded in the ticket's
  resolution.
- Full `tests/unit/` and `tests/mdm/` suites, plus the full repo suite,
  must stay green — matching tonight's baseline (2320 passed, 4 skipped,
  only the 2 pre-existing unrelated
  `test_bootstrap_dbt_snowflake_secret.py` failures documented in
  CLAUDE.md).

## Out of Scope

- The other 3 tickets on the Large-profile unscoped-load audit map
  (`residual_holds_graph`'s mdm-large steps, gold-refresh's streaming-fix
  completeness, `load_history`'s internal `large`-profile states) — each
  is its own separate spec/session.
- Re-fixing anything already covered by gold-build-memory-reliability,
  task-profile-consolidation, the artifact-throttle 5-whys, or the
  bronze-recovery-with-no-DB-row 5-whys — this spec only adds a check for
  the unscoped-ORM/DB-hydration shape on top of that already-closed work,
  not a re-litigation of it.
- Any change to `daily_incremental`/`bootstrap`'s `BackfillMdmEntityIds`
  Step Functions state wiring, retry config, or scheduling.
- Deploying or restarting any production pipeline as a result of this
  work — build the fix (if needed) and its tests; deployment is a
  separate, explicit follow-up decision.

## Further Notes

- The `mdm_entity_backfill.py` finding was discovered while writing this
  spec, by direct code inspection, not by live measurement — its
  real-world urgency (how large does the pending set actually get in
  practice) is unconfirmed and is this ticket's first job to establish
  before deciding whether the fix is urgent (like MANAGES_FUND) or
  pre-emptive (like INSTITUTIONAL_HOLDS).
- Per the parent map's Notes: if the `_run_submissions_bronze_then_silver`
  audit surfaces a genuine gap inside a deeper-nested function this spec
  doesn't name, graduate it as a new ticket on the map rather than fold it
  in here, per wayfinder's fog-of-war convention.
