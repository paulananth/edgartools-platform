# Cut Over MDM's ShardedSilverReader to Snowflake

Type: task
Status: partially implemented — code shipped, flip not yet safe to trust live
Blocked by: Stage 14 (EDGARTOOLS_SILVER at real data volume). Ticket 13's refresh-trigger blocker is now resolved. The CloudWatch alarm (Ticket 10 item 3) is this ticket's own remaining deliverable, not an external blocker — corrected here (2026-08-18) after a review pass caught the earlier version making this ticket self-blocking by construction. The alarm can't actually be built until a real `verify-silver-parity` run against post-flip data exists to alarm on, so it waits on the same Stage 14 dependency, not a separate one.

## Question

[Decide Consumer Cutover Order](09-decide-consumer-cutover-order.md)
resolved: MDM's `ShardedSilverReader` moves off DuckDB first, as this
migration's first real slice. This ticket carries out that cutover — per
this map's Phase 2 mode override (Notes), resolving it means shipping the
migration, not just deciding it further.

**Scope:**

- Gate every `ShardedSilverReader` read call site in MDM behind a new
  `MDM_SILVER_READ_TARGET=duckdb|snowflake` env var (default `duckdb` until
  cutover is verified, then flipped via deploy — no image rebuild to
  revert). Per [Ticket 10](10-decide-cutover-rollback-mechanics.md)'s
  resolved mechanics: **do not delete `ShardedSilverReader`** as part of
  this ticket — it stays as the `duckdb` branch's implementation until
  gold-building's own later cutover retires the write path entirely; only
  then does deleting it become correct. Known call sites as of Ticket 09's
  resolution — re-verify current line numbers before editing, this
  session's grep is a starting point, not a guarantee nothing has shifted:
  - `edgar_warehouse/mdm/cli.py` (four `ShardedSilverReader(...)`
    instantiations — the `_build_silver_reader`-style helper plus two
    standalone call sites)
  - Any caller of `_TABLES`-scoped reads inside `mdm run` (entity
    resolution) and `mdm-backfill-relationships` (relationship derivation)
- The `snowflake` branch reads `EDGARTOOLS_SILVER` (dbt schema),
  authenticated as `EDGARTOOLS_PROD_MDM_SILVER_READER` (provisioned,
  `FUTURE`-scoped, idle since Ticket 05).
- Confirm `EDGARTOOLS_PROD_MDM_SILVER_READER`'s actual grants cover every
  table MDM's resolution/relationship logic reads — `ShardedSilverReader`'s
  `_TABLES` allowlist (`edgar_warehouse/silver_support/sharded_reader.py`)
  is the authoritative list of what must be covered; diff it against the
  role's live grants rather than assuming Ticket 05's provisioning already
  matches (that ticket provisioned the role and `FUTURE` grants, but
  `EDGARTOOLS_SILVER`'s 31 dbt-managed tables didn't fully exist yet at
  provisioning time — verify live, don't assume).
- Build a new `mdm verify-silver-parity`-style command (Ticket 10, item 2):
  runs MDM's entity resolution/relationship derivation against both
  sources for the same real CIK slice and diffs row counts per table plus
  resolved `entity_id` assignments (not just counts). Run it and confirm a
  clean parity result **before** flipping `MDM_SILVER_READ_TARGET` to
  `snowflake` in prod — this is the correctness gate the flip depends on,
  not an optional afterthought.
- New CloudWatch alarm (Ticket 10, item 3) on post-flip divergence —
  exact metric TBD at implementation time based on what
  `mdm verify-silver-parity` emits, mirroring ticket 81's alarm-coverage
  pattern (CLAUDE.md).
- **Write path is out of scope for this ticket** — `silver_store.py` /
  `_publish_shard_if_remote` keep writing to DuckDB (still needed by
  `gold_models.py`, not yet migrated) and to Snowflake silver-landing
  (already live, Ticket 07). Nothing about this ticket touches writes.
- **`gold_models.py` is out of scope** — its own cutover is a separate
  future ticket, bound by Ticket 09's 2-week deadline (starts within 2
  weeks of this ticket being verified live in prod).
- **No rollback-write-unwind logic needed** (Ticket 10, item 4) — a bad
  flip's downstream writes self-correct on the next resolution pass under
  this repo's existing idempotent-upsert posture. Don't build anything
  extra here on that account.

## Deliverable

MDM's entity resolution and relationship derivation read live from
Snowflake (`EDGARTOOLS_SILVER`) in prod via `MDM_SILVER_READ_TARGET=snowflake`,
gated on a clean `mdm verify-silver-parity` result, with the alarm live and
the `duckdb` branch (`ShardedSilverReader`, unmodified) kept in place as
the rollback path — flip the env var back, no redeploy, per Ticket 10.
Verified end-to-end against real prod data (a real `mdm run` /
`mdm-backfill-relationships` execution under the `snowflake` target, row
counts and entity_id assignments compared against the prior DuckDB-backed
run via the new parity command), not just unit-tested in isolation —
matching this map's own standing discipline (Notes: "every fix ships with
real measurements against real data/infra").

Starts the 2-week clock on `gold_models.py`'s own cutover ticket (Ticket
09's dual-write-window bound) once this is verified live.

## Progress (2026-08-18)

**Shipped, tested, committed:**

- `edgar_warehouse/silver_support/snowflake_reader.py` —
  `SnowflakeSilverReader`, duck-type compatible with `ShardedSilverReader`'s
  `.fetch()`/`.close()` seam only (deliberately no `._conn`, so the
  DuckDB-internals-reaching call sites this ticket excludes fail loudly
  instead of silently misbehaving). Handles two real Snowflake behaviors
  found live and confirmed with a real connection before writing any
  handling code: (1) the connector returns UPPERCASE column names for
  unquoted identifiers even when the SQL used lowercase — `fetch()`
  lowercases every column; (2) `?` positional placeholders need
  `paramstyle="qmark"`, which snowflake-connector-python only reads once at
  `connect()` time (not per-`execute()`) and only as a module global — the
  mutation is scoped to the single `connect()` call and restored
  immediately after, so it can't affect `mdm export`/`sync-graph`/
  `verify-graph`'s own pyformat-style Snowflake usage if they ever share a
  process.
- `_silver_reader()` in `edgar_warehouse/mdm/cli.py` gated behind
  `MDM_SILVER_READ_TARGET=duckdb|snowflake` (default `duckdb`, exact env
  var Ticket 10 specified) — the DuckDB branch extracted unchanged into
  `_duckdb_silver_reader()` so `verify-silver-parity` can hold both readers
  side by side. Confirmed via test that default/unset/any-case-of-"duckdb"
  is a complete no-op against the pre-existing path, and that "snowflake"
  short-circuits without touching `MDM_SILVER_DUCKDB`/
  `WAREHOUSE_STORAGE_ROOT` at all.
- `sec_company_sync_state` (the one table `mdm run`'s core resolution path
  reads that has no `EDGARTOOLS_SILVER` analog — see table-coverage
  finding below) now degrades gracefully under the Snowflake target,
  reusing the exact `_find_missing_source_table` pattern already
  established in this file for the identical situation.
- `edgar_warehouse/mdm/silver_parity.py` + `mdm verify-silver-parity` CLI
  command (Ticket 10, item 2's correctness gate) — compares DuckDB vs
  Snowflake per-table row counts across all 31 `EDGARTOOLS_SILVER` tables,
  plus a `sec_company` CIK-set diff (Ticket 10's own stated concern: "two
  runs could match on count and still resolve different CIKs to different
  entities" — a count-only check wouldn't catch that; the set diff does).
  Mirrors `verify-graph`'s shape (`.payload`/`.passed`, JSON output, exit 1
  on failure).
- `infra/snowflake/sql/bootstrap/12_silver_schema_and_mdm_reader.sql`
  updated and re-applied live: added the plain-VIEW grants the original
  script's `ALL/FUTURE DYNAMIC TABLES` grant structurally couldn't cover
  (`sec_guidance_fact_reject` was the one gap — 30/31 tables were already
  covered; confirmed live via `SHOW GRANTS`, not assumed), and resolved the
  script's own "NOT DECIDED BY THIS SCRIPT" credential-activation question:
  `EDGARTOOLS_PROD_MDM_SILVER_READER` granted to `ROLE ACCOUNTADMIN` — a
  literal role name, not `08_loader_role.sql`'s parameterized
  `$loader_default_grantee` session variable (correction, 2026-08-18
  code-review pass: an earlier version of this note claimed the two
  matched; they don't — that file is a per-environment template, this one
  is hand-authored and hardcoded to `EDGARTOOLS_PROD` throughout, so a
  literal grantee is consistent with its own style, not a missed
  convention). **Live-verified end-to-end**: a real connection via
  `MDM_SNOWFLAKE_SECRET_JSON`, `USE ROLE EDGARTOOLS_PROD_MDM_SILVER_READER`,
  `SELECT * FROM SEC_COMPANY` — works. Separate finding, not fixed here: the
  live secret's own `ROLE` field is `ACCOUNTADMIN`, not
  `EDGARTOOLS_PROD_LOADER` as CLAUDE.md's "one runtime role" claim
  describes — drifted from that doc at some point; the grant targets
  today's actual runtime identity.

**Two scope gaps surfaced by a `/code-review` pass (2026-08-18), disclosed
here rather than left only in source comments:**

- **Not gated: `_seed_mdm_from_silver`'s two standalone `ShardedSilverReader`
  instantiations** (`edgar_warehouse/mdm/cli.py`, the `seed-universe
  --source silver` / `seed-from-silver` paths). The Question above listed
  "four `ShardedSilverReader(...)` instantiations" as in scope; only the
  `_silver_reader()`/`_duckdb_silver_reader()` helper (used by `mdm run` and
  `mdm-backfill-relationships`, this ticket's actual stated targets) is
  gated. These two reach past `.fetch()` into `reader._conn` — a
  `SnowflakeSilverReader` connection has no such attribute by design (see
  its module docstring), so gating them today would silently break them
  rather than cut them over. Left ungated deliberately, documented inline
  at `cli.py`'s `_silver_reader()` docstring; revisit when
  `seed-universe`/`seed-from-silver` get their own cutover ticket, same as
  `gold_models.py`.
- **Not built: the CloudWatch alarm** (Ticket 10, item 3) on post-flip
  divergence. Deferred because its metric shape depends on what
  `verify-silver-parity` emits under real load, and that command has not
  yet run against `EDGARTOOLS_SILVER` at scale (blocked on Stage 14, same
  as everything else in this section) — designing an alarm against a
  metric nobody has seen fire yet would be guessing. Adding this as an
  explicit precondition on the actual flip, alongside Ticket 13 below: the
  alarm must exist and the parity command must have run clean against real
  volume before `MDM_SILVER_READ_TARGET` moves to `snowflake` in prod.

**Real blocker found during implementation, not assumed away — filed as
[Ticket 13](13-decide-edgartools-silver-refresh-trigger.md), now resolved**:
`EDGARTOOLS_SILVER`'s dynamic tables were `target_lag = 'DOWNSTREAM'` with no
downstream consumer, so nothing scheduled their refresh at all — Ticket 11's
1,506 visible rows only existed because of a manual `REFRESH`. This fell
through the gap between Ticket 09 (order) and Ticket 10 (mechanics) — neither
owned it. **Fixed (2026-08-18):** `target_lag` changed to a fixed `6 hours`
in the shared `silver_model_config` dbt macro (matching CLAUDE.md's
`SNOWFLAKE_RUN_MANIFEST_TASK` 1min→6hr precedent at the adjacent pipeline
layer), applied live to all 30 dynamic tables, verified via
`SHOW DYNAMIC TABLES`. No longer a blocker on the actual flip — see Ticket
13's own Answer for the full reasoning.

**Table-coverage finding, resolved narrowly, not a blocker**: checked
`ShardedSilverReader._TABLES` (39) against `EDGARTOOLS_SILVER`'s 31 dbt
models directly — 8 tables differ, all operational/bookkeeping
(`sec_company_sync_state`, `sec_daily_index_checkpoint`, `sec_parse_run`,
`sec_reconcile_finding`, `sec_source_checkpoint`, `sec_sync_run`,
`sec_tracked_universe`, `stg_daily_index_filing`). Grepped `pipeline.py`/
`graph.py` (the actual `mdm run`/`mdm-backfill-relationships` code) for
every `FROM`/`JOIN` — only `sec_company_sync_state` is touched, now
handled (above). The other 7 belong to `seed-universe`/`coverage-report`/
daily-index tooling, out of this ticket's scope — **already decided**, not
new fog: `duckdb-retirement` map's own Ticket 08 already sent these to
Snowflake native Postgres, not `EDGARTOOLS_SILVER`. No new ticket needed.

**`mdm verify-silver-parity` smoke-tested live end-to-end for the first time
(2026-08-19)**, against a real local `silver.duckdb` (51,888 `sec_company`
rows) and real prod Snowflake (`MDM_SNOWFLAKE_SECRET_JSON`, role
`EDGARTOOLS_PROD_MDM_SILVER_READER` reached via the runtime credential's
`ACCOUNTADMIN` role per the existing documented drift). This is the first
time the command — and `SnowflakeSilverReader` itself — has run against
anything but `_fake_snowflake.py`. Result: `passed: false`,
`cik_fetch_error: null` (the code-review-added guard held, no crash), 22/31
tables mismatched, all 51,888 DuckDB CIKs reported as `cik_only_in_duckdb`,
0 as `cik_only_in_snowflake`. This is the **correct, expected** result, not
a bug — `EDGARTOOLS_SILVER` genuinely has no real data yet (Stage 14 hasn't
run); the only non-zero live table is `sec_employment_event` (1,506 rows,
Ticket 11's known manual-`REFRESH` state). Confirms the whole comparison
path — connection, role activation, per-table counts, the CIK-set diff, the
JSON payload shape, the exit-1-on-fail contract — works correctly against
real infrastructure, not just the unit-test fakes. This is the "real metric
shape" evidence the CloudWatch alarm's earlier deferral (above) was
specifically waiting on — the alarm can now be scoped from an actual
payload instead of a guess, though building it still isn't safe to attempt
until it can be dimensioned against a post-flip run (see below).

**Not done — the actual flip.** `MDM_SILVER_READ_TARGET` stays `duckdb` in
prod. Ticket 13's refresh-trigger blocker is now resolved (all 30 tables
refresh on a real 6-hour schedule as of 2026-08-18). Still blocked on
`EDGARTOOLS_SILVER` actually holding real data at scale (Stage 14 / Task
#159, itself blocked on the `shard-0.duckdb` race — explicitly out of
Ticket 09's scope, tracked separately), then a clean `mdm verify-silver-parity`
result against real volume, then the CloudWatch alarm (this ticket's own
remaining deliverable — not buildable yet: `verify-silver-parity` has no
scheduled/dispatchable invocation wired into `deploy-aws-application.sh` at
all today, unlike `mdm verify-graph`'s existing `ecs_state` pattern, and an
alarm on "post-flip divergence" run *before* the flip exists would fire on
every single scheduled run — the exact "looks like coverage, isn't"
anti-pattern ticket 81's own write-up warns against for orphaned alarms).
Re-open this ticket to `Status: resolved` once all three land and the flip
is verified live — matching this map's own standing discipline of real
measurements over assumptions.

**Checked, not built (2026-08-19): the scheduled-invocation prerequisite for
the CloudWatch alarm is itself Stage-14-blocked, not independently
buildable.** Considered wiring `mdm verify-silver-parity` into the existing
"MDM Utility Machine" (`write_mdm_utility_definition`,
`infra/scripts/deploy-aws-application.sh`) as an 8th mode alongside
`mdm_verify_graph`, since that's a real, unblocked-looking two-line ASL
addition on its face. Rejected after checking against live state: a
scheduled parity check against today's `EDGARTOOLS_SILVER` (still
effectively empty — see the fresh Ticket 08 evidence below) would exit 1 on
every single run, which is the identical "looks like coverage, isn't"
orphaned-alarm anti-pattern already invoked two paragraphs up for the alarm
itself — the invocation and the alarm share the same Stage 14 dependency,
they aren't separable. Separately, `_handle_verify_silver_parity`
(`edgar_warehouse/mdm/cli.py`) requires `MDM_SILVER_DUCKDB`, a local
filesystem path — an ECS-hosted invocation would need either a new
Snowflake-only parity mode or a step to hydrate `silver.duckdb` into the
task first, which is real design work whose right shape depends on what a
post-Stage-14 parity payload actually looks like. Not attempted; revisit
once Stage 14 produces one.

**Stage 14 status (2026-08-19), corrected with direct evidence:** the
`bronze-seed-silver-gold-resultpathfix-retry-1787100060` execution (launched
after task #166's `ResultPath` fix, with the user's explicit accept-the-race-
risk decision) ran 20:41-21:12 EDT and failed
`States.ExceedToleratedFailureThreshold`: 166/680 `BatchSilver` batches
succeeded, 1 failed, 20 aborted in-flight, 493 never started —
`toleratedFailurePercentage: 0.0`, so a single failure was sufficient to
trip it. An earlier pass at this diagnosis (same session) used
`list-executions --state-machine-arn ... --query "?mapRunArn==..."`, which
returns `[]` for Distributed Map children and couldn't find the failed
child's own error. The correct call —
`aws stepfunctions list-executions --map-run-arn <mapRunArn> --status-filter
FAILED`, then `describe-execution`/`get-execution-history` on that one child
— found it: the same `--cik-list` batch was retried 4 times (Step
Functions' own `Retry` on `runTask.sync`, not this ticket's shard-publish
retry, which didn't exist yet at the time of this run), and **2 of the 4
attempts show `ExitCode: 137`, `"Reason": "OutOfMemoryError: container
killed due to memory usage"`** on `edgartools-prod-medium` (4096MB); the
other 2 show `ExitCode: 2` (consistent with, not directly confirmed as, the
unretried `PromotionConflictError` this ticket's fix now handles). So the
real failure shape is **both** the shard-race conflict this ticket set out
to fix **and** a pre-existing OOM risk on the same batch, independent of
any merge logic — confirmed via a real `silver_shard_hydrated` log line for
this exact execution showing an 823MB shard (`shard_index: 0,
size_bytes: 823406592`) against `bootstrap-batch`'s 4096MB medium profile.

**Fix implemented this session** (`edgar_warehouse/application/
warehouse_orchestrator.py`): `_publish_shard_if_remote` now merges via
`merge_candidate_into_canonical` (the same function the monolith path uses)
instead of blindly overwriting when a canonical version already exists, and
a new `_publish_shard_if_remote_with_retry` wrapper (mirroring
`_publish_silver_database_with_retry`'s exact env-configurable
backoff/attempts shape) retries the whole read-merge-stage-promote cycle on
`PromotionConflictError` — the actual call site
(`_execute_warehouse_bronze_capture`'s shard branch) now calls the retry
wrapper. Docstring's former "each shard is owned by exactly one writer"
claim removed — false under `BatchSilver`'s `MaxConcurrency: 20` against 4
shards, which is exactly what caused this and the two prior failures.

**Memory finding surfaced during review, addressed but not fully closed:**
an independent review pass caught that the merge branch (download canonical
~823MB, write to tmp, `merge_candidate_into_canonical`'s own canonical copy,
re-read merged bytes) adds real memory pressure on top of a profile that,
per the OOM evidence above, is *already* marginal even under the old
no-merge code. Mitigated by porting `_publish_silver_database_if_remote`'s
skip-if-unchanged fingerprint check (release-readiness ticket 79) to
`_hydrate_shard_for_window`/`_publish_shard_if_remote`: a shard whose
content is provably unchanged since hydration skips the entire merge/S3
cycle before any remote call, which should cover the dominant case during a
reprocessing pass (most batches write zero new rows — confirmed via this
same execution's own logs: `"rows_written": 0` on every sampled batch).
This does **not** fully close the memory question for batches that *do*
have real writes to merge — that risk is reduced, not eliminated, and
remains open pending a real Stage 14 rerun with this fix deployed.

**Second, related gap found by the same review pass (code-review, not
gof-refactor-reviewer):** the skip-if-unchanged fast path only protects a
provable no-op. On a shard with real conflicting writes, each
`PromotionConflictError` retry re-runs the *entire* merge branch — full
canonical re-download, full `merge_candidate_into_canonical` copy, full
re-read of merged bytes — so the per-attempt memory/time cost multiplies by
attempt count, and the retry policy is unbounded by default
(`WAREHOUSE_PUBLISH_CONFLICT_ATTEMPTS=0`). This is the most plausible way
the fix still reproduces Stage 14's `ExitCode: 137` even once deployed: a
hot shard under real concurrent writes (not the skip-path's zero-write case)
retries the full merge cost repeatedly. Test coverage is thin on exactly
this combination — of the retry-specific tests, only one exercises retry
together with an actual merge, and it uses tiny in-memory DuckDBs, not the
~823MB scale that OOM'd in prod. Not fixed in this pass (would mean
re-architecting the merge to avoid a full re-download per retry, a bigger
change than the user's chosen scope of "make the publish path safe under
concurrent writers") — logged here as an explicit, undischarged risk for
whoever verifies the real Stage 14 rerun: if it OOMs again, check whether it
was a low-write-count skip-path hit (unexpected) or a high-retry-count
merge-branch hit (this gap) before re-diagnosing from scratch.

Full test suite green (2208+ passed) including a real hydrate-then-publish
skip-path test and a two-concurrent-writers-with-injected-stale-baseline
regression test proving both writers' rows survive. **Not yet built, pushed,
or deployed** — the fix exists only as committed source as of this entry;
Stage 14 remains unresolved and this ticket's flip stays blocked — see task
#159/#70 for that thread; the shard race itself is
explicitly out of this map's scope per Ticket 09.
