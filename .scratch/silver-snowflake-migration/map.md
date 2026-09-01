# Silver-on-Snowflake Migration

## Destination

Silver's canonical store moves fully off S3/local-DuckDB and onto Snowflake.

**Phase 1 (closed — 7 tickets, 01-07):** a locked target architecture
(Python-populated Snowflake landing zone for SEC-document parsing, feeding
dbt-native silver transformation models) — architecture-only, no
implementation. Achieved; see Decisions so far.

**Phase 2 (reopened 2026-08-18):** a concrete, sequenced cutover plan —
Snowflake compute cost estimate, consumer cutover order, and rollback
mechanics — plus execution of the first real migration slice. Done when
DuckDB is retired as the operational engine for at least one consumer
(MDM's `ShardedSilverReader`, `gold_models.py`'s Python builders, or the
`silver_store.py` write path) with the remaining consumers' order locked
for follow-up.

## Notes

- Domain: `edgar_warehouse/silver_store.py` (4,360 lines — the real bulk of
  today's write/merge/promotion logic; `silver.py` itself is now just a
  7-line compatibility shim), `edgar_warehouse/silver_support/
  sharded_reader.py`, `edgar_warehouse/silver_protection.py` (967 lines,
  canonical merge/promotion), `edgar_warehouse/serving/gold_models.py`
  (Python gold builders reading silver's DuckDB connection directly via raw
  SQL), `edgar_warehouse/mdm/` sharded silver reads, `edgar_warehouse/
  parsers/` (`ownership.py`, `adv.py` — Python-only SEC document parsing via
  the `edgartools` package; this does not move to SQL, see below),
  `infra/snowflake/dbt/edgartools_gold/` (existing dbt project this
  migration extends with a new silver layer).
- **Settled scope, from this session's destination-naming/frontier-mapping
  grilling** (captured here since no tickets existed yet to hold them):
  - Full rewrite of the query/transform layer to Snowflake — not a
    storage-swap that keeps DuckDB as the local query engine.
  - Shape: dbt-native. A new Python-populated Snowflake landing zone holds
    parsed-but-not-yet-cleaned rows; dbt silver models (clean/dedupe/merge)
    sit between that landing zone and gold, replacing most of
    `silver_store.py`'s custom Python merge/promotion/ETag-optimistic-
    concurrency machinery with Snowflake's native `MERGE`/transactions.
  - **Refinement, not optional**: Python (via the `edgartools` package,
    confirmed live — `edgar_warehouse/parsers/ownership.py` imports
    `edgar.ownership.Ownership` directly) still does all SEC-document
    parsing (XBRL, ownership Form 3/4/5, ADV). That step is fundamentally
    Python's job and does not become dbt/SQL under any version of this
    migration — only the clean/dedupe/merge logic downstream of parsing
    moves to dbt.
  - Standing requirement: every provisioning step in this migration is a
    committed, re-runnable script — never a manual/uncommitted session —
    and ownership goes to one dedicated loader role from day one. Direct
    lesson from this repo's own documented incidents: the MDM Snowflake
    mirror schema was silently lost because it was provisioned by an
    uncommitted manual session; a later `GRANT OWNERSHIP ... REVOKE CURRENT
    GRANTS` step separately stripped an unrelated role's grants. Both are
    in CLAUDE.md under "MDM Snowflake mirror schema lost on cutover" and
    "Manifest-pipeline ownership + cursor-syntax incident" — read before
    drafting Ticket 05's checklist.
  - **Sequencing: `load_history`'s retry6 (ticket 42's full-universe
    backfill) is blocked on this map** — specifically on
    [Design the Snowflake-Native Silver Layer's Model Structure](issues/01-design-snowflake-native-silver-model-structure.md)
    reaching a locked answer, not on the full migration being built. This
    is the priority ticket on this map.
- **Relationship to prior maps** (read before assuming either is settled
  counterevidence or duplicate work):
  - [pipeline-throughput-architecture](../pipeline-throughput-architecture/map.md)
    (closed) already grilled "should the silver-merge storage path change"
    (its ticket 05) and concluded "leave it" — but that measurement was
    against `ReduceIdentityRefresh`, a stage removed entirely by PR #396's
    Stage0 consolidation. Stale, not counterevidence for this map. That
    same map's ticket 12 built and deployed a real, measured CIK-sharded
    hydrate/publish mechanism for `bootstrap-batch` (76s → 3.2s per batch) —
    likely obsolete once silver lives natively in Snowflake (no more local
    monolith/shard split to reason about at all), but not yet confirmed —
    see Ticket 06.
  - [ecs-cost-sizing](../ecs-cost-sizing/map.md) (active) is where this
    migration's trigger surfaced: `load_history`'s `WindowedBootstrap`
    monolith-hydrate cost (found live, `bootstrap-next` never got
    `bootstrap-batch`'s sharding treatment) and the $22.40 month-to-date S3
    cost line (largest single AWS cost this month). Treat as evidence
    input; don't re-derive it.
- Use `/gof-refactor-reviewer` before any ticket proposing to restructure
  `silver_store.py` or `silver_protection.py` — matches
  `pipeline-throughput-architecture`'s own standing preference for this
  exact code.
- **Mode, Phase 2 only:** overridden from the wayfinder default. Phase 1
  (tickets 01-07) was decision-spec only. Phase 2 (tickets 08+) carries
  **execution** into the map itself — once [Decide Consumer Cutover
  Order](issues/09-decide-consumer-cutover-order.md) resolves, the
  consumer it names gets an actual migration ticket, not just a spec.
- **Motivating evidence for Phase 2 (don't re-derive — captured live,
  2026-08-18):** the exact write path Phase 1 would retire
  (`_publish_shard_if_remote` in `warehouse_orchestrator.py`, the
  sharded-DuckDB S3 publish under `bronze_seed_silver_gold`) failed twice
  in a row in real prod runs on the same conflict class: an ETag-guarded
  optimistic-concurrency race on `shard-0.duckdb` under
  `MaxConcurrency=20` against only 4 shards. First occurrence: execution
  `bronze-seed-silver-gold-1787078879`, 171/680 batches succeeded then
  aborted (`ToleratedFailurePercentage: 0`). Second: the resume attempt
  (`bronze-seed-silver-gold-resume-1787081736`), same shard, same error
  class, on all 3 Step-Functions retry attempts of the same batch. The
  function's own docstring asserts "each shard is owned by exactly one
  writer... a conflict signals a genuine invariant violation, not an
  expected race" — contradicted by `deploy-aws-application.sh`'s own
  `batch_map` comment, which already predicted multiple concurrent Map
  slots landing on the same shard file at this concurrency. One earlier
  historical run (`bronze-seed-silver-gold-medium-20-retry-1786214600`,
  2026-08-08, sharding confirmed active) completed 680/680 cleanly — so
  this is a real but probabilistic race, not a deterministic failure,
  which is exactly the kind of fragility a fully Snowflake-native silver
  layer (no local sharded-file publish step at all) structurally
  eliminates rather than patches. **Third occurrence, 2026-08-19**
  (`bronze-seed-silver-gold-resultpathfix-retry-1787100060`, 166/680
  succeeded then aborted): direct evidence this time (via
  `list-executions --map-run-arn`, not the state-machine-level query that
  returns nothing for Distributed Map children) showed the failing batch's
  4 retried attempts split 2 `OutOfMemoryError` (`ExitCode: 137`,
  `edgartools-prod-medium`, 4096MB, against an 823MB shard) and 2
  `ExitCode: 2` (consistent with the unretried conflict) — a real,
  independent OOM risk on the same batch, not just the ETag race. **Fixed
  (2026-08-19, code only, not yet deployed):** `_publish_shard_if_remote`
  now merges via `merge_candidate_into_canonical` and a new
  `_publish_shard_if_remote_with_retry` wrapper retries on
  `PromotionConflictError`, mirroring `_publish_silver_database_with_retry`
  exactly; the added merge's memory cost is mitigated (not eliminated) by
  porting `_publish_silver_database_if_remote`'s skip-if-unchanged
  fingerprint check to the shard hydrate/publish path, avoiding the new
  merge machinery entirely for the dominant zero-write-batch case. See
  [Ticket 12](issues/12-cutover-mdm-sharded-silver-reader-to-snowflake.md)'s
  own account for full detail. Stage 14 of the live install provisioning
  run (Task #159) remains blocked pending a real rerun with this fix
  deployed, tracked separately from this map.

- **Current frontier (2026-08-19):** [Cut Over MDM's ShardedSilverReader to
  Snowflake](issues/12-cutover-mdm-sharded-silver-reader-to-snowflake.md) is
  partially implemented — the reader adapter, env-var flip, and correctness-
  gate command are shipped, tested, and committed, and its refresh-trigger
  blocker is now resolved (see [Ticket 13](issues/13-decide-edgartools-silver-refresh-trigger.md)
  below). The actual prod flip is still blocked on `EDGARTOOLS_SILVER`
  actually holding real data at scale (Stage 14, blocked separately, see
  motivating evidence above), a clean `mdm verify-silver-parity` run against
  that volume, and the CloudWatch alarm on post-flip divergence (not yet
  built). Checked live (2026-08-19): the alarm's own scheduled-invocation
  prerequisite is *not* independently buildable ahead of Stage 14 either — a
  cron'd parity check against still-empty `EDGARTOOLS_SILVER` would exit 1
  on every run, the same orphaned-alarm anti-pattern one layer down. Stage 14
  itself failed a third time this session (`bronze-seed-silver-gold-
  resultpathfix-retry-1787100060`, 166/680 `BatchSilver` batches succeeded,
  `States.ExceedToleratedFailureThreshold` at `toleratedFailurePercentage:
  0.0`) — pattern-consistent with, but not directly confirmed as, the same
  `shard-0.duckdb` race (stack trace unrecoverable from CloudWatch this
  pass). See Ticket 12's own "Progress" section for the full account before
  picking this back up.

- **Update (2026-08-19, later same day):** confirmed the shard-publish fix
  (`eb0a60cb`) live in prod *before* rerunning anything — `warehouse-prod`
  (digest `sha256:33a6f1e9...`, tag `warehouse-sha-85ab9e65a599`) and
  `mdm-prod` (digest `sha256:3ad1dba8...`, same commit `85ab9e65`) both
  descend from `eb0a60cb`, confirmed via `git merge-base --is-ancestor`, and
  the registered task-def revisions the state machine actually references
  (`edgartools-prod-medium:208`, `edgartools-prod-mdm-medium:178`) point at
  those exact digests — so no rebuild/redeploy was needed, just a rerun. The
  most recent execution before this (`relderiv-fix-verify-1787165186`,
  started 14:46:28) had already independently proven the shard fix at real
  scale: `BatchSilver`'s `MapRunSucceeded` at 15:51:57 (~64 min,
  `MaxConcurrency:20` against 4 shards, the exact race condition) — it then
  failed 4x at `MdmRun` on the separate, already-diagnosed migration-011
  `UndefinedColumn` gap (see CLAUDE.md's "MDM Postgres migration-011 schema
  drift" 5-whys), fixed same-day via `edgartools-prod-mdm-migrate`. Rather
  than repay the proven ~64-minute `BatchSilver` cost, started a fresh
  execution (`migration011-fix-verify-resume-1787189893`) with
  `resume_from_run_id: relderiv-fix-verify-1787165186` to reuse that run's
  already-succeeded batch state and go straight to `MdmRun` onward,
  confirmed routing through `ComputeRemainingBatches` as designed. Also
  confirmed live: the deployed MDM image already contains `534d40e7` (the
  relationship-derivation multi-threading fix) and `7ffda2d7` (migration-
  011's own model change), so `MdmRun` this time exercises the fixed,
  concurrent path, not the old single-threaded one. In progress as of this
  entry — outcome not yet known.

## Decisions so far

<!-- Closed ticket decisions: one-line gist and link; detail stays in the ticket. -->

- [Design the Snowflake-Native Silver Layer's Model Structure](issues/01-design-snowflake-native-silver-model-structure.md) — new append-only `EDGARTOOLS_SILVER_LANDING` schema (reuses SOURCE's native-pull apparatus, simplified to plain INSERT); final silver tables are uniformly `dynamic_table` (current-state, window-function collapse) rather than a per-table incremental/snapshot mix — chosen specifically because it needs zero new dbt-run trigger infrastructure, unlike `incremental` models; CIK-partitioning and the operational/lease tables' disposition are explicitly deferred to Tickets 06 and 02 respectively.
- [Decide the Concurrent-Writer Model for Snowflake-Native Silver](issues/02-decide-concurrent-writer-model.md) — there's no promotion-race conflict class left to replace at all (append-only per-row INSERT, confirmed-disjoint CIK windows); the whole ETag/promote-with-retry/candidate-canonical-merge apparatus retires outright. `sec_fetch_active`/`pipeline_run_lease` is a separate, unrelated mechanism and stays. `parse_sequence` is a row-level Snowflake `SEQUENCE`. `MaxConcurrency:1` stays for now, pending live-tested (not assumed) evidence at rollout.
- [Decide the Replacement Path for Direct Silver Consumers](issues/03-decide-direct-silver-consumer-replacement.md) — `gold_models.py`'s ~20 Python builders retire entirely in favor of dbt gold `ref()`-ing dbt silver directly, which also retires `EDGARTOOLS_SOURCE`'s current gold-mirror purpose and structurally moots the `iter_gold_tables` OOM-mitigation concern; `validate_data_quality.py`'s separate `build_gold` call becomes SQL assertions against live Snowflake gold; MDM's `ShardedSilverReader`/`_TABLES` allowlist retires in favor of Snowflake-native GRANTs on a dedicated reader role, fixing the exact silent-gap failure shape that caused the `INSTITUTIONAL_HOLDS`/`EMPLOYED_BY` incidents.
- [Decide the Ad-Hoc Reprocessing Story](issues/04-decide-ad-hoc-reprocessing-story.md) — today's "one workflow" is really five distinct mechanisms, resolving into three capability classes: SEC-fetching reprocessing (targeted-resync/full-reconcile/--force) is unaffected; bronze-only re-merge (parse-*-bronze) becomes a CLI re-parse into the append-only landing zone, simplified not downgraded; manual diagnosis (diagnose-silver-anomalies.py) keeps its read/print-remediation shape but its remediation output shifts from UPDATE/DELETE to a corrective INSERT or a re-parse pointer, since landing is append-only.
- [Confirm Relationship to `pipeline-throughput-architecture`'s Sharding Work](issues/06-confirm-relationship-to-sharding-work.md) — confirmed obsolete: the whole local-file sharding mechanism (checksums, hydrate/publish, UNION ALL reconstruction) has no analog in Snowflake. What survives as a concept, now decided: no explicit `CLUSTER BY` for now (rely on natural CIK-ordered load correlation), and the accession-join taxonomy gets an explicit `cik` column materialized in silver rather than left as a join every consumer must rediscover. Cross-reference note left on the closed `pipeline-throughput-architecture` map.
- [Draft the Cutover Script and Ownership Requirements](issues/05-draft-cutover-script-and-ownership-requirements.md) — landing/silver schemas owned by the existing `EDGARTOOLS_PROD_LOADER` (no new pipeline-object owner minted); MDM gets a brand-new, minimally-scoped `EDGARTOOLS_PROD_MDM_SILVER_READER` role with `FUTURE`-scoped grants (no allowlist to drift). Shipped as real, tested artifacts, not prose: `infra/scripts/generate_silver_landing_ddl.py` (a genuine reflection-based generator, via DuckDB introspection since `silver_store.py`'s schema isn't SQLAlchemy) plus its committed snapshot and a second bootstrap file for the future dbt-managed `EDGARTOOLS_SILVER` schema and the MDM reader role. Caught a real bug while building it: `pipeline_run_lease` doesn't belong in the append-only landing zone despite being listed in `PROTECTED_TABLE_REGISTRY`.

- [Decide the Silver-Landing Ingestion Mechanism](issues/07-decide-silver-landing-ingestion-mechanism.md) — a new, isolated apparatus (not an extension of `native_pull`'s live SOURCE pipeline); a scheduled `COPY INTO` task, not Snowpipe+stream+manifest. Decided, built, and applied live to prod in the same session: `13_silver_landing_ingest.sql` created (loader-owned, not ACCOUNTADMIN — a real policy violation caught before applying), the storage integration and its AWS IAM counterpart both widened for the new prefix, and three live-only bugs fixed (`COPY INTO`'s `MATCH_BY_COLUMN_NAME` doesn't apply column `DEFAULT`s — `parse_sequence`'s `NOT NULL` dropped, backfilled via a follow-up `UPDATE`; `getColumnValue` by name throws, needs positional index; the zero-files result set has a different column count than the loaded-files one). Verified end-to-end against real prod Snowflake with a hand-built test file before trusting it; all test data cleaned up, task confirmed `started` in a verified-clean state. The AWS IAM policy follow-up (Terraform source not committed) is now also closed — `runtime_access` gained an `additional_export_prefixes` variable mirroring `native_pull`'s pattern, verified via `terraform plan` showing 0 changes against live state (PR #411).

**Map closed again — seven tickets resolved.** The Snowflake ingestion-path
gap discovered while deploying the six original tickets' first
implementation pass (`claude/silver-snowflake-implementation`) is now fully
live in prod, including the last deferred piece: `SILVER_LANDING_EXPORT_ROOT`
was flipped on (PR #412) and prod redeployed, so real bronze-capture runs now
populate the silver-landing zone end to end.

- [Estimate Snowflake Compute Cost for Native Silver](issues/08-estimate-snowflake-compute-cost.md) — real steady-state numbers unobtainable (the live account, `PRJEDJU-QJB05385`, was rebuilt 2026-08-17/18, everything is 0 rows); surfaced that Ticket 07's `LOAD_SILVER_LANDING_TASK` was never re-applied to this account at all (not suspended — absent), which is why nothing has ever refreshed on a schedule here. Delivered a bottom-up floor estimate (~$4/month at 6hr lag to ~$96/month at 15min lag, before an unmeasured and plausibly-dominant marginal cost from the 6 FULL-mode ownership/financial tables) and flagged a live, currently-accruing `SNOWFLAKE_RUN_MANIFEST_TASK` 1-minute-schedule drift as a likely bigger cost lever than silver's own TARGET_LAG choice. See new [Ticket 11](issues/11-reprovision-missing-bootstrap-sql-on-rebuilt-account.md).

- [Reprovision Missing Phase 1 Bootstrap SQL on the Rebuilt Account](issues/11-reprovision-missing-bootstrap-sql-on-rebuilt-account.md) — `13_silver_landing_ingest.sql` reapplied live (storage integration/IAM allowlist and `SILVER_LANDING_EXPORT_ROOT` had already survived the rebuild correctly; only the task itself was missing); `SNOWFLAKE_RUN_MANIFEST_TASK` schedule fixed 1min→6hr. Found and fixed a second, previously-unknown bug in the process: Snowflake implicitly forces `NOT NULL` on any `PRIMARY KEY` column regardless of its own declaration, so Ticket 07's original "drop NOT NULL" fix only ever worked via an undocumented live-only ALTER that didn't survive the rebuild — now a committed, idempotent `ALTER TABLE ... DROP NOT NULL` in the generator itself (`generate_silver_landing_ddl.py`), with a regression test. Verified end-to-end live: a real `bootstrap-batch` run → `LOAD_SILVER_LANDING()` → manual dynamic-table `REFRESH` chain, 1,506 real rows landed in `EDGARTOOLS_SILVER.SEC_EMPLOYMENT_EVENT`. Genuine `SCHEDULED`-triggered refreshes still require Ticket 09/10's cutover (no downstream consumer yet on `DOWNSTREAM`-lag tables) — out of this ticket's scope.
- [Decide Consumer Cutover Order](issues/09-decide-consumer-cutover-order.md) — **MDM's `ShardedSilverReader` first, then `gold_models.py`'s Python builders, then the write path retires.** Checked directly (not assumed): gold's ~20 builders read zero MDM-derived fields, so MDM-first carries no risk to gold — order was decided by surface area (one class vs. twenty functions) and existing idle runway (`EDGARTOOLS_PROD_MDM_SILVER_READER`, provisioned by Ticket 05, unused) rather than risk. Dual-write window bounded: gold-building's cutover must start within 2 weeks of MDM's cutover being verified live. Stage 14's write-path race kept explicitly out of scope (operational unblock, not a sequencing decision). Graduates into [Ticket 12](issues/12-cutover-mdm-sharded-silver-reader-to-snowflake.md).
- [Decide Cutover/Rollback Mechanics](issues/10-decide-cutover-rollback-mechanics.md) — for MDM's cutover specifically: flip via a toggleable `MDM_SILVER_READ_TARGET=duckdb|snowflake` env var (deliberate exception to the map's "committed script, not toggleable state" preference, scoped to this first-slice read selector only); correctness gate is a new `mdm verify-silver-parity` command mirroring `mdm verify-graph`'s strict-parity precedent, run clean before flipping; rollback trigger is a new CloudWatch alarm (ticket-81 pattern), rollback window rides Ticket 09's existing 2-week deadline rather than a new clock; no downstream-write unwind needed (resolution logic is unchanged, only the read source is — self-corrects on next pass under existing idempotent-upsert posture). Threaded into [Ticket 12](issues/12-cutover-mdm-sharded-silver-reader-to-snowflake.md)'s scope as concrete requirements.
- [Decide EDGARTOOLS_SILVER's Refresh Trigger](issues/13-decide-edgartools-silver-refresh-trigger.md) — fixed `target_lag = '6 hours'` (not `DOWNSTREAM`, not a dedicated `TASK`), changed in the single shared dbt macro every silver model already flows through (`silver_model_config.sql`) rather than a new bootstrap SQL file. Matches CLAUDE.md's already-documented `SNOWFLAKE_RUN_MANIFEST_TASK` 1min→6hr precedent at the adjacent pipeline layer, and Ticket 08's own cost estimate (~$4/month at this cadence). Applied live to all 30 dynamic tables immediately (as `EDGARTOOLS_PROD_DEPLOYER`, the tables' real owner role — not `EDGARTOOLS_PROD_LOADER`), verified via `SHOW DYNAMIC TABLES`. Unblocks [Ticket 12](issues/12-cutover-mdm-sharded-silver-reader-to-snowflake.md)'s refresh-trigger gap; the actual flip still waits on Stage 14 data volume, a clean parity run, and the CloudWatch alarm.
- [LOAD_SILVER_LANDING_TASK Suspended Since 2026-08-13 — Landing Zone Has Zero Rows](issues/14-load-silver-landing-task-suspended-zero-rows.md) — a real structural bug (`replace_company_tickers` decorated with a landing-row tracker that recorded the raw 3-column caller input instead of the enriched 7-column row actually written, so any `sec_company_ticker` export aborted the whole load procedure on `COPY INTO`'s `NOT NULL` violation). Fix (`11f81229`) confirmed both committed and live: the deployed `edgartools-prod-medium` image (rev 204, digest `sha256:13ba01c5`) descends from the fix commit, and `LOAD_SILVER_LANDING_TASK` has run clean every 5 minutes for 4+ hours on the current (`PRJEDJU-QJB05385`) account, surviving the account rebuild that came after this fix originally shipped. One inference flagged, not verified: why two initial post-rebuild failures self-cleared isn't directly confirmed (likely a stale S3 file purged by the ticket-22 lifecycle rule). Real at-scale proof — a fresh `sec_company_ticker` export landing clean — still rides on Stage 14, same as Ticket 12.
- [Root-Cause the Per-Table Snowflake Silver Ingestion Gap](issues/15-root-cause-per-table-silver-landing-ingestion-gap.md) — the identical "content predates the landing-zone write path" shape Ticket 14 found for company metadata alone, widened: most non-company tables (ADV, 13F, ownership transactions, financial facts) sat at or near 0% coverage in `EDGARTOOLS_SILVER`. Generalized Ticket 14's own one-time backfill mechanism (`_BACKFILL_TABLES` now = `PARITY_TABLES` minus `sec_company_ticker`) rather than building a new one. First live run OOM'd (surfaced two implementation bugs — stale/retired shard hydration, full-table Python materialization — fixed in duckdb-retirement-cutover Ticket 05's own follow-on commit `2a6836fe`); second run succeeded, then hit a **third, genuinely separate, pre-existing bug**: a raw SEC XBRL footnote marker (`[F2]`) leaked into an `exercise_date` field via the *ongoing incremental* capture path (not this backfill), blocking `LOAD_SILVER_LANDING_TASK` for every table the same way Ticket 14's `sec_company_ticker` bug once did. Quarantined (not deleted) the one offending file; left the incremental-capture root cause itself as an explicitly open, unfiled follow-up. **Result: 25 of 31 `PARITY_TABLES` at exact 100% parity**, remaining 6 (company-metadata family) within 97.6%-105% — real-time snapshot-timing drift against a live pipeline, not a coverage gap.

**Phase 1's "live in prod" claims above describe a prior account
(`pijjxma-ppb32800`), not the current one.** The account was rebuilt again
to `PRJEDJU-QJB05385` on 2026-08-17/18 — after this map's own Tickets 05/07
verified their work live, and after this session's earlier, separate task
history (#147/#153/#154 in the session's task list) had already fixed and
verified `LOAD_SILVER_LANDING_TASK` once before on the account that
preceded this one. That fix did not survive the rebuild. Treat every "built
and applied live to prod" claim in Tickets 05-07 as historically true but
not currently verified on `PRJEDJU-QJB05385` until Ticket 11 re-confirms
it.

## Not yet specified
- `gold_models.py`'s own cutover ticket — not written yet, deliberately
  deferred until [Cut Over MDM's ShardedSilverReader to Snowflake](issues/12-cutover-mdm-sharded-silver-reader-to-snowflake.md)
  is verified live (Ticket 09's 2-week dual-write-window clock starts
  then, not before).

## Out of scope

<!-- none identified yet; fog resolves into tickets or here as the map advances -->
