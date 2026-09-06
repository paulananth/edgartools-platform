# 10 — The Atomic Write-Path Cutover (Indivisible)

**What to build:** DuckDB Retirement's Ticket 01 (wayfinder decision) locked
this in as one atomic code change, no transition-window flag:
`register-task-definition` bakes a specific-revision ARN into each deploy's
Step Functions JSON, and executions already running keep using the old
revision for their whole lifecycle (confirmed AWS behavior) — so mid-flight
executions are isolated for free, without needing a feature flag.

In one deploy: the production write path stops writing `silver.duckdb`
entirely (Snowflake landing zone only). At the same moment, all consumers
that Tickets 02–03 and 05–08 already proved work against their new targets
switch over together:

- The 11 operational bookkeeping tables (checkpoints, sync-state, leases,
  run audit trail) — repointed at the live Postgres store from
  [Ticket 02](02-move-bookkeeping-tables-to-snowflake-postgres.md)/
  [Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md)/
  [Ticket 13](13-rewrite-cross-store-join-sites.md)/
  [Ticket 14](14-repoint-warehouse-orchestrator-bookkeeping-callers.md)/
  [Ticket 15](15-repoint-remaining-bookkeeping-callers.md), actually
  provisioned live by [Ticket 04](04-provision-live-bookkeeping-postgres.md)
- MDM's reader ([Ticket 05](05-cutover-mdm-reader-to-snowflake.md))
- Gold's Python builders retiring in favor of dbt `ref()`ing dbt silver
  (external `dbt-gold-silver-rewiring` chain)
- **All five** acquisition-family `*_silver_acceptance.py` modules —
  `silver_acceptance.py` (filing_artifact, the only one wired into a live
  scheduled command today) plus its four dormant siblings
  (`reference_catalog_`, `company_facts_`, `submissions_`,
  `adv_bulk_dataset_silver_acceptance.py`) — per
  [Ticket 09](../duckdb-retirement/issues/09-account-for-silver-acceptance-in-write-path-cutover.md)'s
  resolution on the wayfinder map (a different ticket set — the wayfinder
  map's own Ticket 09, not this cutover ticket set's Ticket 09)

**Do not split this ticket further along consumer lines.** Ticket 01's own
rollback answer is explicit: rolling back only the write path "would
silently starve already-cutover readers of fresh data, not error loudly."
Splitting "cut over the acquisition modules" or "cut over MDM's reader" into
separate deploy steps from the write-path flip reintroduces exactly that
failure mode. This ticket is one deploy, or it isn't the ticket the map
decided on.

**Blocked by:**
[Ticket 01](01-rewrite-daily-index-checkpoint-qualify-clause.md),
[Ticket 02](02-move-bookkeeping-tables-to-snowflake-postgres.md),
[Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md),
[Ticket 13](13-rewrite-cross-store-join-sites.md),
[Ticket 14](14-repoint-warehouse-orchestrator-bookkeeping-callers.md),
[Ticket 15](15-repoint-remaining-bookkeeping-callers.md),
[Ticket 04](04-provision-live-bookkeeping-postgres.md),
[Ticket 05](05-cutover-mdm-reader-to-snowflake.md),
[Ticket 06](06-retire-bootstrap-batch-sharding.md),
[Ticket 07](07-retire-ddl-generator-scripts.md),
[Ticket 08](08-build-table-specific-reconciliation-tooling.md), and the
`dbt-gold-silver-rewiring` map's full 7-ticket chain — every consumer must
already be proven against Snowflake before this ticket flips the write path
off DuckDB. Note Ticket 04 specifically: the bookkeeping Postgres instance
must be live, not just coded, before this deploy — the write path cannot
repoint to a store that doesn't exist yet.

**Status:** code complete (2026-09-06); deploy pending operator

All 11 listed blockers are now closed (Ticket 05 landed 2026-09-06, PR #556,
merge commit `d242144f`) — this ticket was unblocked and implemented in the
same session.

- [x] Production write path (`_run_submissions_bronze_then_silver` and every
      other DuckDB-write call site) no longer writes `silver.duckdb`
- [x] The 11 bookkeeping tables read/write the live Postgres store, not
      `SilverDatabase`/DuckDB — already true (Tickets 02–04/13–15), confirmed
      unaffected by this ticket's own changes
- [x] All five `*_silver_acceptance.py` modules (accessed through their
      `drive_*_discovery.py` workflow drivers) no longer hydrate/publish
      canonical `silver.duckdb`
- [x] MDM's reader and gold's builders are confirmed live on Snowflake
      (already true — Ticket 05, `dbt-gold-silver-rewiring` map)
- [ ] Deployed via `register-task-definition` baking a specific-revision
      ARN — **not done this session; deploy is an explicit operator step**,
      not something an autonomous implementation session performs against
      production credentials (same convention Ticket 05's own text
      established for its live-verification step)
- [ ] [Ticket 08](08-build-table-specific-reconciliation-tooling.md)'s
      tooling readiness against the post-cutover state — not re-verified
      this session; do before deploying

## What was actually implemented (2026-09-06)

Scope turned out materially larger than this ticket's own checklist named.
A full read/write call-site audit (not just the write calls the checklist
listed) found two live read dependencies on hydrated local DuckDB content,
and a second, independent write path to the same canonical object that this
ticket's own text never mentioned. All three are now part of this cutover:

**1. Two read call sites repointed at `EDGARTOOLS_SILVER` via
`SnowflakeSilverReader`** (new functions in `warehouse_orchestrator.py`,
mirroring Ticket 05's `SnowflakeSilverReader` pattern exactly):

- `SilverDatabase.get_company_identity_ciks` (`silver_store.py:2845`) — read
  `sec_company`/`sec_company_ticker` from local DuckDB directly, feeding the
  live scheduled `CaptureCompanyIdentityBatches` stage in `daily_incremental`.
  Without a fix this would have silently selected zero eligible CIKs forever
  once hydration stopped — exactly the "silently starve rather than error
  loudly" failure this ticket's own rollback section warns about. Replaced
  by `_company_identity_ciks_snowflake`; the old DuckDB method is now dead,
  left for Ticket 12's sweep.
- `fetch-adv-bulk`/`fetch-firm-roster`'s `already_ingested` idempotency
  checks (`db.fetch("SELECT DISTINCT <period_column> FROM <table> ...")`
  against `sec_adv_private_fund`/`sec_adv_firm_roster`) — live in both
  `load_history`'s and `daily_incremental`/`bootstrap`'s Step Functions
  definitions. Without a fix, every run would have re-downloaded and
  re-ingested the full ADV bulk archive/firm roster dataset every time
  (idempotent merges mean this wasn't silent data loss, but was a real,
  ongoing cost regression on whole-dataset downloads). Replaced by a shared
  `_snowflake_distinct_values(table, column)` helper.

Confirmed safe with no fix needed: `_configured_parser_accessions`'s
`db.get_filing()` reads (fed entirely by this same run's own writes,
never by hydration); `fetch_filing_artifacts`'s cache-hit check (its
bronze-key S3 LIST fallback, built for the 2026-08-10 "no-DB-row" bug,
already covers the unhydrated case without re-fetching from SEC);
`parse-ownership-bronze`/`parse-adv-bronze` (their only pipeline caller,
`ownership_mdm_gold`, was already retired by state-machine-consolidation
Ticket 08 — now reachable only via manual CLI invocation, same bucket as
`_require_duckdb_silver_reader`); `_resolve_fundamentals_ciks` (already
fully Postgres-backed via `bookkeeping.get_tracked_ciks`, confirmed by
reading its body directly rather than trusting a stale nearby comment).

**2. A second, independent write path retired:**
`identity_refresh_publication.py`'s `reduce_identity_refresh` — not
mentioned by this ticket's checklist at all. It read canonical
`silver/sec/silver.duckdb`, merged the identity-refresh reference snapshot
and every CIK-batch delta into it via `merge_candidate_into_canonical`, and
staged/promoted the result — structurally identical to the monolith path,
just built independently to survive `daily_incremental`'s ~20-way
concurrent `CaptureCompanyIdentityBatches` writers without a shared-object
promotion race (mirroring the shard-publish incident's own reasoning). Its
merge/stage/promote body (and `PromotionConflictError` retry loop) is now
retired; `load_complete_run_manifest`/`validate_complete_run_manifest`'s
manifest-completeness gate is kept, since `PublishCompanyIdentityUpdates`
still needs "every declared batch actually succeeded" as a real fan-out
failure signal, even with nothing left to merge on success.
`persist_run_manifest`/`persist_batch_outcome` are untouched — they write
run-scoped immutable objects under `identity_refresh/runs/<run_id>/...`,
never canonical.

**3. Write-path hydrate/publish calls removed** (call sites, not the shared
functions themselves — see below): `warehouse_orchestrator.py`'s
`_execute_warehouse_bronze_capture`; all five `drive_*_discovery.py`
acquisition workflow modules (`drive_filing_discovery.py` — confirmed live
today via `daily_incremental`'s default-on
`enable_filing_artifact_gated_capture`, not dormant as this ticket's own
text assumed; `drive_submissions_discovery.py`, `drive_company_facts_
discovery.py`, `drive_reference_catalog_discovery.py`, `drive_adv_bulk_
dataset_discovery.py` — confirmed dormant, no live scheduled caller, per
duckdb-retirement Ticket 09's own finding); `bootstrap_fundamentals.py`
(both the `--cik-list` and windowed cases — the windowed case's own
comment claiming it "still hydrates, since it resolves its CIK batch from
db.get_tracked_ciks()" was stale; `_resolve_fundamentals_ciks` has read
`bookkeeping.get_tracked_ciks()` — Postgres — since Ticket 14).

`_hydrate_silver_database_from_storage` itself is left in place, still
called from four read-only/operator tools this ticket deliberately does
NOT touch (see below) — only the production-write-path call sites were
edited. `_publish_silver_database_if_remote` is made a permanent no-op
(single point of change, since every one of its ~15 call sites already
handles a `None` return — it's the pre-existing `not is_remote` local-
testing path). `_publish_silver_database_with_retry` needed no change; it
delegates to the now-neutered function.

**Left alone, note only (operator/reconciliation tooling, not the write
path):** `validate_data_quality.py`, `table_reconciliation/cli.py`,
`mdm/cli.py:765`'s `_require_duckdb_silver_reader` reference, and
`silver_landing_historical_backfill.py` still call
`_hydrate_silver_database_from_storage`. Post-cutover this downloads a
**frozen** S3 object (nothing writes it anymore, so it doesn't error —
`download_file` just returns whatever content existed at cutover time), so
these tools get stale-but-valid data rather than an empty/broken result.
Same bucket as the already-established `_require_duckdb_silver_reader`
convention: noted here, not fixed — converting them to read Snowflake (or
to fail loudly instead of silently going stale) is new work, and this
repo's convention is that Ticket 12 owns dead-code/tooling sweeps, not a
cutover ticket.

**Confirmed no live shard-publish path exists:** `_publish_shard_if_remote`/
`_publish_shard_if_remote_with_retry` have zero real callers anywhere in
the codebase (only comment/docstring references) — Ticket 06's own finding
still holds; nothing needed touching there.

**Tests:** new `tests/unit/test_write_path_snowflake_reads.py` (both new
Snowflake-backed helpers); `tests/unit/test_identity_refresh_window.py`,
`tests/application/test_fetch_adv_bulk_command.py`, `tests/application/
test_fetch_firm_roster_command.py` updated to patch the new Snowflake
call sites instead of seeding local DuckDB; `tests/unit/
test_identity_refresh_publication.py` rewritten for the no-op reducer
contract (kept the 4 manifest-validation tests unaffected by this change,
replaced the merge/promote/retry tests); `tests/application/
test_warehouse_orchestrator_mdm.py`'s 8 direct merge/promote/retry tests
replaced with 2 asserting the permanent-no-op contract (zero S3 calls of
any kind); `tests/unit/test_skip_noop_silver_publish.py` deleted outright
(its entire premise — the fingerprint skip-if-unchanged optimization — no
longer exists, since there's no merge to skip); `tests/unit/test_sharding.py`
and `tests/application/test_bootstrap_company_identity.py` updated for the
new no-hydrate contract; `tests/architecture/test_sibling_path_symmetry.py`'s
monolith/shard merge-symmetry check `@unittest.skip`-marked with the same
reasoning/precedent its sibling env-var symmetry test already used (Ticket
06) — deletion deferred to Ticket 12 alongside the dead code it protects.

**Not done this session (explicitly deferred to the operator/deploy step):**
the actual `register-task-definition` deploy, Ticket 08's tooling
re-verification against post-cutover state, and retiring
`PublishCompanyIdentityUpdates`/`CaptureCompanyIdentityBatches` from
`deploy-aws-application.sh`'s state machine definitions (the reducer state
still runs, it now just validates without merging — no state-machine JSON
edit was needed to achieve that).

## Verification

Full repo suite green: 3079 passed, 7 skipped, 8 failed — the 8 failures are
exclusively in `tests/integration/test_acquisition_ledger_postgres.py`/
`test_conflict_postgres.py` (a local test-Postgres schema drift on
`source_fetch_work.captured_etag`, unrelated to acquisition ledger/conflict
tables this ticket never touches), matching the same pre-existing gap
CLAUDE.md documents repeatedly across prior, unrelated entries. mypy against
every changed production file compared line-for-line against the
pre-cutover baseline (via a temporary `git stash`): identical 24 pre-existing
errors, same classes, same files, only shifted line numbers — nothing this
diff introduced.

Three-axis `/code-review` (Standards/Spec/GoF, per CLAUDE.md's hard rule)
run against `origin/main` (`d242144f`, the just-merged Ticket 05 fix):

- **Standards**: no hard violations. One accuracy fix applied —
  `_publish_silver_database_if_remote`'s docstring overclaimed
  `compute_silver_fingerprint`/the fingerprint-sidecar helpers were now
  fully dead; they're still called from `_hydrate_silver_database_from_
  storage`, kept alive for the four read-only tools this ticket deliberately
  leaves alone. Corrected to say precisely what's dead
  (`merge_candidate_into_canonical`, now uncalled from both real call
  sites) versus what isn't. Judgment call on the 5-whys convention: not
  required here — a planned migration ticket's own incidentally-discovered
  scope gaps (caught before any live incident), not a live-observed defect
  the convention targets; the ticket file's own write-up already carries
  the equivalent root-cause detail per gap.
- **Spec**: clean. Every checklist item and every claim in the "What was
  actually implemented" section above independently verified against the
  actual diff (all ~15 `_publish_silver_database_if_remote` call sites
  confirmed to already handle `None`; all five acquisition drivers edited
  identically; `reduce_identity_refresh`'s manifest-completeness gate
  confirmed still intact and unmodified; the two new Snowflake helpers'
  SQL confirmed correct against both the reader's real column-casing
  contract and the original DuckDB queries they replace). No scope creep,
  no half-migrated state.
- **GoF**: healthy, nothing to fix. Independently re-verified the one
  design question flagged before implementation (separate
  `_company_identity_ciks_snowflake`/`_snowflake_distinct_values`
  functions vs. one shared helper) — confirmed correct to keep separate;
  the only shared code is a 4-line connect/fetch/close idiom that already
  recurs at 6+ other call sites in the codebase, below any real-duplication
  bar. Noted, not actioned (out of scope, pre-existing, not GoF-shaped):
  that same connect/fetch/close idiom could become a context manager
  repo-wide as a pure ergonomics simplification.
