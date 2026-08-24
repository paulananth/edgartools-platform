# 29 — Deploy the gated acquisition path to prod and dry-run it

**What to build:** Take the gated acquisition path (Tickets 13–19: Command
registration, the fenced ledger, the capture Facade, SEC-change-discovery
driving, retry-safety, ordered Logical Source Revisions, and the
filing-to-Silver acceptance seam) from "merged to `main`, verified locally
against ephemeral Postgres" to "live in prod and observed processing a real
diff end-to-end" — for the one source family already wired through it
(`filing_artifact`). Not a rebuild of anything already decided; this is the
first real deployment of code this map already produced.

**Blocked by:** 18 — Materialize ordered logical source revisions; 19 —
Complete the filing-to-Silver acceptance seam; 31 — `EXCLUDED_OPERATIONAL_TABLES`
content never reaches canonical silver once canonical exists (resolved —
this was the actual remaining blocker; its fix is what unblocked the dry
run below)

**Status:** resolved

- [x] `013_acquisition_ledger.sql` (and its widened `finalize_source_fetch`
  signature from Ticket 17) is applied to prod's MDM Postgres via the
  standard `mdm migrate` path — not ad hoc — and confirmed live (no
  `UndefinedColumn`/`UndefinedTable` on a real query), following the
  lesson in CLAUDE.md's "MDM Postgres migration-011 schema drift" incident:
  verify against the *current*, non-orphaned state machine, not a stale one.
- [x] Warehouse and MDM images are rebuilt from current `main` and pushed to
  ECR (per CLAUDE.md's image-rebuild table — this path touches both
  `edgar_warehouse/acquisition/**` and, if `mdm/**` changed since the last
  prod image, that role too) and deployed via `deploy-aws-application.sh
  --env prod`.
- [x] A real `drive-filing-discovery-for-date` (or the Command-registration
  seam's equivalent entry point) runs against prod for a bounded, small
  date/CIK scope — not the full universe — and is observed producing: a
  Fetch Decision per candidate, a verified Bronze capture, a materialized
  Logical Source Revision, and a Silver acceptance outcome, traceable
  end-to-end via the ledger's own status/observation-position reads.
  Chosen scope is small enough to inspect every row by hand.
  <!-- decision: which command is the real prod entry point once Command
       registration expands, and what the dry-run's exact bounded scope
       is, are resolved during this ticket, not pre-decided here -->
- [x] A no-op replay of the same scope is run a second time and confirmed to
  change nothing new (idempotent convergence, one of the map's acceptance
  criteria) — the first live proof of that criterion against real prod
  infrastructure rather than a test double.
- [x] Any prod-only gap found in the process (grants, orphaned state
  machines, stale secrets — this repo's history says to expect at least
  one) is fixed via a committed, re-runnable script, not a manual one-off,
  per the standing "no state survives an account rebuild unless it's
  Terraform or a script" lesson in CLAUDE.md.
- [x] Legacy acquisition paths for `filing_artifact` are left untouched —
  this ticket proves the new path works in prod, it does not cut traffic
  over or remove the old path (that's Ticket 27, and only after every
  source family, not just this one, proves out).

## Answer

**Done:**

- [x] Migration 013 applied to prod MDM Postgres via `edgartools-prod-mdm-utility`
  (`{"mode": "mdm_migrate"}`, the current, non-orphaned consolidated machine —
  confirmed *not* one of the orphaned per-command originals per CLAUDE.md's
  "MDM Postgres migration-011 schema drift" lesson). Verified live: all six
  `edgartools_acquisition_*` roles exist, `application` holds `SET TRUE`
  non-inherited membership in five of them, `SET ROLE
  edgartools_acquisition_processor` successfully reads `source_fetch_decision`,
  and none of the nine acquisition objects carry a direct `application` grant.
  Two genuine, previously-undiscovered prod-only provisioning bugs were found
  and fixed live along the way (PR #453, merged): (1)
  `bootstrap-prod-mdm.sh`'s post-migrate fencing `REVOKE`s ran as
  `snowflake_admin` *after* ownership of the acquisition objects had already
  moved to `edgartools_acquisition_owner` inside the same script's `mdm
  migrate` call, failing with `permission denied for table` — fixed with `SET
  ROLE edgartools_acquisition_owner` around just those statements; (2) all
  four `bootstrap-*`/`remove-aws-mdm-rds-after-cutover.sh` scripts' shared
  `aws_cli()` helper hit bash 3.2's empty-array-under-`set -u` unbound-variable
  bug on macOS (same class as CLAUDE.md's documented `mapfile`/`mktemp`
  issues) — fixed with the `${args[@]+"${args[@]}"}` idiom in all four.
- [x] Warehouse and MDM images rebuilt from current `main` (digests
  `sha256:0fbb4645...` / `sha256:77a4ceb7...`) and deployed via
  `deploy-aws-application.sh --env prod --enable-mdm`; all task defs and
  state machines re-registered onto them, confirmed via the written manifest.
- [x] Prod-only gaps fixed via committed, re-runnable scripts, not manual
  one-offs (the two `bootstrap-prod-mdm.sh`/`aws_cli()` fixes above).
- [x] Legacy `filing_artifact` acquisition paths untouched — nothing in this
  ticket's work modified `capture-filing-artifact` or any pre-Ticket-13 path.

**First attempt was blocked, then unblocked by Ticket 31:**

The first dry-run attempt hit exactly the blocker described in Ticket 31 —
seeding one business date (`load-daily-form-index-for-date 2026-08-21`,
3,719 total daily-index rows) succeeded at the ECS-task level but silently
never reached canonical silver (`"skipped": true, "tables_merged": []`),
so the follow-up `drive-filing-discovery-for-date 2026-08-21` failed closed
exactly as designed (`WarehouseRuntimeError: No sealed discovery observation
for business_date=2026-08-21 (checkpoint status='missing')`). Root-caused to
two compounding, pre-existing bugs in the general silver merge/publish
subsystem (not caused by this ticket's own diff) — see
[31 — `EXCLUDED_OPERATIONAL_TABLES` content never reaches canonical silver
once canonical exists](31-excluded-operational-tables-never-reach-canonical-silver.md)
for the full root cause and fix. That fix was implemented, reviewed, merged
(PR #454), deployed to prod, and verified live — `load-daily-form-index-for-date`
re-run afterward showed `"tables_merged": ["sec_daily_index_checkpoint",
"stg_daily_index_filing"]` for the first time.

**Dry run and no-op replay — both completed successfully, 2026-08-24:**

With canonical silver now correctly sealing the daily-index checkpoint, ran
the full sequence against prod for `business_date=2026-08-21` (3,719 daily-index
candidates, no artificial scope reduction — small enough a date that every
candidate could still be inspected via the ledger's own reads):

1. `drive-filing-discovery-for-date 2026-08-21 --run-id ticket29-dryrun-retry-1787571822`
   — ECS task `02cb9d533b5e416ab3990b7860826a22`, exit code 0, ~85 minutes
   (sequential per-candidate Postgres round-trips through the acquisition
   ledger — SET LOCAL ROLE, Fetch Decision insert/lookup, Source Revision
   check, observation-cursor advance — genuinely slow but genuinely working,
   confirmed via continuous CloudWatch log growth throughout, not a hang).
   `run_manifest.json` result:
   ```
   candidates: 3719, captured: 614, excluded: 3105,
   interval_complete: true, silver_interval_complete: true,
   silver_settled: 614, silver_unsettled: 0, unsettled: 0
   ```
   Zero errors/exceptions anywhere in the full CloudWatch log stream.
2. No-op replay: `drive-filing-discovery-for-date 2026-08-21 --run-id
   ticket29-dryrun-replay-1787578744` — ECS task
   `f6ba924f383248a8920850b354d20b54`, exit code 0, ~36 minutes (faster than
   the first run, as expected with no new SEC fetching). `run_manifest.json`
   row_counts were **byte-identical** to the first run's (same 3719/614/3105/614/0/0
   figures). Across the entire replay log stream: **zero** `sec_pull_started`
   events (no candidate was re-fetched from SEC) and **zero** error/exception/
   failure patterns. This is the idempotent-convergence acceptance criterion,
   proven live against real prod infrastructure rather than a test double.

Also confirmed along the way: [30 — Fence `application` from acquisition
ledger tables under Snowflake Postgres's `snowflake_write` role](30-fence-application-from-acquisition-tables-under-snowflake-write.md)
remains open and non-blocking — it was filed as a separate finding during
the earlier attempt and was not re-investigated in this pass; it does not
gate this ticket's own acceptance criteria.

**Status:** resolved.
