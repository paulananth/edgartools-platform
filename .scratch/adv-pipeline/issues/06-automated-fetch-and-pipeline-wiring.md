# 06 — Automated Fetch and Pipeline Wiring Shape

Type: grilling
Status: resolved
Blocked by: 02, 03, 04
Blocks: none

## Question

With the parser/private-fund strategy (ticket 02), cadence semantics
(ticket 03), and a manually-validated pipeline (ticket 04) all settled,
decide the concrete shape of automated ingestion:

1. What component scrapes the IAPD bulk-data listing page for the current
   month's (non-predictable) filenames, downloads, SHA-256s, and stages to
   S3 — a new `edgar-warehouse` CLI subcommand (mirroring the
   `ingest-relationship-sources --kind iapd_adv_bulk` manifest-based
   pattern), or something else?
2. How does it plug into `load_history` — a new Stage, or a step within an
   existing stage? (Company Identity's precedent in
   `.scratch/company-master-pipeline/issues/05-bulk-mode-state-machine-shape.md`
   wove itself in as a strict Stage 0 before Branch A; decide whether ADV
   should mirror that shape or stay a standalone invocation per this map's
   "Not yet specified" note on first-class-phase promotion.)
3. How does it plug into `daily_incremental` given ticket 03's monthly
   cadence answer — same state machine, gated by a cheap
   already-ingested-this-month check so it no-ops on every day that isn't a
   new snapshot month?
4. What CLI flags/state-machine inputs thread the `dataset_period`
   idempotency key through, mirroring how `artifact_policy` was threaded
   through `load_history`'s SM input for the artifact-throttle fix?

## Answer

Grilled with the user 2026-07-27, one question at a time. All four settled:

1. **Fetch component: new `edgar-warehouse` CLI subcommand (`fetch-adv-bulk`),
   manifest as its own artifact.** Fetches `reports_metadata.json`,
   determines which `dataset_period`s in the rolling window aren't yet
   ingested (per ticket 03's immutable-once-ingested rule), downloads only
   those, computes SHA-256, stages to S3, writes a manifest file — mirrors
   the existing `mdm build-relationship-release-manifest` precedent (build
   the manifest as reviewable evidence, keep `ingest-relationship-sources`
   unchanged as the separate consuming step) rather than fetching and
   ingesting in one opaque step.
2. **`load_history` wiring: new sequential Stage, not a parallel Map.**
   Company Identity's Stage 0 precedent
   (`.scratch/company-master-pipeline/issues/05-bulk-mode-state-machine-shape.md`)
   used a Distributed Map because it fetches many small per-CIK submissions;
   ADV bulk fetch is a handful of sequential monthly archive downloads (13
   for baseline, not CIK-windowed at all), so the parallel-Map machinery
   doesn't apply. A single ECS task step (same execution pattern as
   `gold-refresh`), placed between Stage 1 (bronze/silver) and Stage 2 (MDM
   entity resolution) so `mdm run`/`derive-relationships` sees fresh ADV
   silver data in the same execution.
3. **`daily_incremental` wiring: daily invocation, cheap check inside the
   command, no state-machine-level day-of-month gate.** The same
   `fetch-adv-bulk` subcommand runs every day; its own logic checks local
   silver first (zero network cost on a hit — the current month's
   `dataset_period` already ingested) before ever polling
   `reports_metadata.json`. Explicitly rejected a fixed day-of-month
   trigger: ticket 01's research found SEC's actual publish-day pattern is
   grounded in only 2 real data points so far ("not an established
   long-run track record") — a fixed-day gate risks silently missing a late
   publish, whereas a daily poll with a local-first check costs almost
   nothing on the ~29 no-op days and self-heals if SEC's timing drifts.
4. **SM-input threading: optional `dataset_period` + `force` fields,
   mirroring `artifact_policy`'s Check→Default Pass-state pattern.** Unlike
   `artifact_policy` (a meaningful operator choice on every run),
   `dataset_period` isn't something an operator needs on the normal path —
   the subcommand auto-detects it. The two fields exist for the manual
   repair/backfill case: `dataset_period` forces a specific month instead of
   auto-detecting the window; `force` allows re-ingesting an
   already-ingested period, mirroring CLAUDE.md's platform-wide `--force`
   repair-flag convention. Both default to unset via the same Check/Default
   pair `artifact_policy` uses, interpolated into the command via
   `States.Format` the same way.

Implementation status (same session, after this grilling settled the design
per explicit user choice "Grill it first"):

- **Done, fully tested:** decision 1, the `fetch-adv-bulk` CLI subcommand —
  pure logic (`edgar_warehouse/application/adv_bulk_fetch.py`), orchestrator
  dispatch, CLI registration, command registry, manifest-path registration,
  scope resolution, and SEC host allowlisting for
  `reports.adviserinfo.sec.gov`. `force` without `dataset_period` is rejected
  (was only a documented claim, now enforced) and filenames from the SEC
  metadata payload are matched with `fullmatch`, not `search`, before being
  used in a storage path.
- **Done (2026-07-28), fully tested:** decisions 2, 3, and 4 — the Step Function JSON
  wiring in `infra/scripts/deploy-aws-application.sh`, via
  `/to-spec` + `/to-tickets` + `/implement` on the
  [ADV fetch pipeline wiring spec](../../adv-fetch-pipeline-wiring/spec.md). A new
  `AdvBulkFetch` Stage (`DatasetPeriodCheck`/`DatasetPeriodDefault` → `ForceCheck` →
  `FetchAdvBulk`/`FetchAdvBulkForced` → `IngestAdvBulkSources`) runs after
  `Stage1BThirteenF`/`RunWarehouseTask` and before `MdmRun` in both `load_history` and
  `daily_incremental`, with `dataset_period`/`force` SM-input threaded via the
  Check→Default pattern exactly as decided here. Structural tests added to both
  `tests/architecture/test_load_history_state_machine.py` and
  `test_daily_incremental_state_machine.py`. Code review caught and fixed two real bugs
  (Stage1BThirteenF's own lenient Catch bypassing the new stage; missing `ResultPath: null`
  reintroducing this file's documented D-15 bug class). Committed on
  `claude/adv-pipeline-t04-t05` (`28a343e`); not yet pushed/merged.
- The `ingest-relationship-sources` empty-manifest relaxation (a
  fail-closed check loosened to treat `{"sources": []}` as a valid no-op) is now
  load-bearing for the shipped SM wiring above.
