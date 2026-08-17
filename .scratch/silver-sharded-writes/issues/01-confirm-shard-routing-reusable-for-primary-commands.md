# Confirm Shard-Routing Mechanics Are Reusable As-Is for Primary Ingestion Commands

Type: research
Status: resolved
Blocked by: none

## Question

`warehouse_orchestrator.py:499-503`'s `_using_shard_path` gate is `True` only
when `command_name == "bootstrap-batch" and context.storage_root.is_remote
and bool(arguments.get("cik_list"))`. Read
`edgar_warehouse/application/commands/migrate_silver_shards.py` (the CIK-range
→ shard-index routing rules: CIK-direct columns, accession→issuer-CIK join,
full replication for global tables) and `_hydrate_shard_for_window()`/
`_publish_shard_if_remote()` in `warehouse_orchestrator.py` in full.

For each of `load_history` (via `bootstrap-next`'s `WindowedBootstrap`),
`daily_incremental`, and `bootstrap`: at the point `merge_candidate_into_canonical`
is currently called, does that command already have an explicit CIK list (or
CIK range) available to resolve a shard index the same way `bootstrap-batch`
does today, or does new plumbing need to be added to derive one (e.g. from
`$.window_offset`/`$.window_limit` for `load_history`, or from whatever
`daily_incremental`/`bootstrap` currently use to scope their SEC pulls)? Cite
exact call sites (file:line) for where each command currently resolves its
CIK scope, and state plainly whether shard-index resolution is a trivial
reuse of existing data or requires new code.

## Deliverable

Answer inline in this ticket's resolution comment (no separate findings file
needed unless the investigation turns out to be large) — cite every claim to
a `file:line` reference.

## Answer

### 0. `migrate_silver_shards.py` routing rules (as built, one-time migration)

- **CIK-direct tables** (routed by the row's own `cik` column, filtered
  `WHERE cik >= cik_min AND cik <= cik_max`):
  `sec_company`, `sec_company_address`, `sec_company_former_name`,
  `sec_company_submission_file`, `sec_company_ticker`,
  `sec_company_sync_state`, `sec_company_filing`, `sec_current_filing_feed`,
  `sec_raw_object`, `sec_reconcile_finding` —
  `edgar_warehouse/application/commands/migrate_silver_shards.py:38-49,211-221`.
- **Accession-join tables** (routed by the *issuer* CIK via a join to
  `sec_company_filing.cik`, never the owner/insider CIK):
  `sec_ownership_reporting_owner`, `sec_ownership_non_derivative_txn`,
  `sec_ownership_derivative_txn`, `sec_filing_attachment`, `sec_filing_text` —
  `migrate_silver_shards.py:55-81,224-234`.
- **Global tables** (replicated identically into all 4 shards, no CIK
  filter): `sec_sync_run`, `sec_source_checkpoint`,
  `sec_daily_index_checkpoint`, `stg_daily_index_filing`, `sec_parse_run`,
  `sec_adv_filing`, `sec_adv_office`, `sec_adv_disclosure_event`,
  `sec_adv_private_fund` (+ optional legacy `sec_tracked_universe`) —
  `migrate_silver_shards.py:97-112,236-256`. ADV tables are global rather
  than CIK-routed because `sec_adv_filing.cik` is NULL for 58,598/58,599 real
  prod rows (advisers key off `crd_number`, not CIK) —
  `migrate_silver_shards.py:83-96`.
- Verification is 3-layer (row-count parity, CIK-set parity, SHA-256
  checksums) and only covers `CIK_KEYED_TABLES = CIK_DIRECT_TABLES` —
  `migrate_silver_shards.py:114-115,262-344`.

### 1. How `bootstrap-batch` resolves its shard today (the existing, working path)

Two-stage design, not one:

- **Upstream, before any ECS task runs:** `seed-bronze-batches` calls
  `_write_cik_universe_batches(..., shard_aware=True)`
  (`warehouse_orchestrator.py:5087-5133`), which calls
  `_shard_partition_ciks` (`warehouse_orchestrator.py:5136-5165`) to bucket
  the *entire* CIK universe by `band_for_cik` from the shard manifest, then
  round-robins per-shard batches into `cik_list` JSONL lines
  (`_interleave_round_robin`, `warehouse_orchestrator.py:5168-5179`). Each
  Distributed Map item therefore already receives a `cik_list` that is
  (mostly) pure to one shard band, computed with **zero DB open** — it reads
  only the shard manifest JSON.
- **At the ECS task itself:** `_using_shard_path` is gated to exactly
  `command_name == "bootstrap-batch" and context.storage_root.is_remote and
  bool(arguments.get("cik_list"))` (`warehouse_orchestrator.py:499-503`).
  When true, it re-derives `cik_min`/`cik_max` from the already-supplied
  `cik_list` (`warehouse_orchestrator.py:506-508`), calls
  `shards_for_window(manifest, cik_min, cik_max)`
  (`edgar_warehouse/application/sharding/shard_manifest.py:66-` /
  `warehouse_orchestrator.py:509,524`), and if exactly one shard overlaps,
  hydrates only that shard (`_hydrate_shard_for_window`,
  `warehouse_orchestrator.py:1211-1255`) and opens it directly via
  `open_silver_shard` (`warehouse_orchestrator.py:555`,
  `edgar_warehouse/silver_support/session.py:22`) — no monolith hydrate at
  all. If the window straddles two bands, only `overlapping[0]` is written
  and a `shard_window_crosses_band_boundary` warning is emitted
  (`warehouse_orchestrator.py:529-543`) — an accepted, imperfect compromise,
  not a full multi-shard write.
- **Publish is notably NOT `merge_candidate_into_canonical`.** The monolith
  path (`_publish_silver_database_if_remote`,
  `warehouse_orchestrator.py:1045-1133`) merges the local candidate against
  a freshly re-downloaded canonical copy via `merge_candidate_into_canonical`
  (`warehouse_orchestrator.py:1114`, imported at
  `warehouse_orchestrator.py:79`) before an ETag-guarded promote. The shard
  path's `_publish_shard_if_remote` (`warehouse_orchestrator.py:1276-1339`)
  skips that merge entirely — it does a direct ETag-guarded
  `stage_and_promote` of the local shard bytes, on the explicit design
  assumption that "each shard is owned by exactly one writer in the sharded
  architecture" (`warehouse_orchestrator.py:1290-1294`), so a conflict there
  signals a genuine invariant violation rather than something to merge past.
  **This means the ticket's literal framing — "at the point
  `merge_candidate_into_canonical` is called" — doesn't apply to the sharded
  path at all today; the sharded design deliberately replaces that merge
  with single-owner-per-shard + ETag conflict detection.** Any of the three
  primary commands moving onto shards inherits this same open question:
  either they too become single-owner-per-shard-per-run (works cleanly only
  if one run touches exactly one shard), or a shard-aware merge function
  needs to be built (new code, not reuse) for any command whose CIK scope
  can span shards within one run.

### 2. `load_history` (`bootstrap-next` per window) — MODERATE new plumbing, not trivial reuse

- `load_history`'s `compute-windows` step (Stage 0/1 setup, single-shot, not
  per-window) already computes the **full, ordered CIK universe** once:
  `ciks = db.get_tracked_ciks(LOAD_HISTORY_TRACKING_STATUS_FILTER)` where
  `LOAD_HISTORY_TRACKING_STATUS_FILTER = "active,bootstrap_pending"`
  (`warehouse_orchestrator.py:219,2705`), ordered strictly ascending by CIK
  (`SELECT cik FROM sec_company_sync_state ... ORDER BY cik`,
  `edgar_warehouse/silver_store.py:3570-3595`). It writes both
  `cik_windows.jsonl` (`{window_offset, window_limit}` descriptors,
  `warehouse_orchestrator.py:2715-2724`) and `cik_snapshot.jsonl` (the full
  ordered CIK list, `warehouse_orchestrator.py:2726-2728`) to the bronze
  root as plain files — this is the load_history analog of `bootstrap-batch`'s
  pre-partitioned `cik_list` lines, and it exists **before any window's task
  runs and without opening any silver DB**.
- Each `WindowedBootstrap` step then invokes
  `bootstrap-next --silver-only --cik-limit $.window_limit --cik-offset
  $.window_offset --tracking-status-filter 'active,bootstrap_pending' ...`
  (`infra/scripts/deploy-aws-application.sh:2463`) — same filter, same
  ordering as `compute-windows`, so in principle the window's literal CIK
  range is already recoverable from the already-written `cik_snapshot.jsonl`
  with no DB query.
- **But `bootstrap-next`'s actual runtime CIK resolution does not consult
  that snapshot.** It calls `_resolve_bootstrap_target_ciks(db=db,
  raw_ciks=None, tracking_status_filter=tracking_status_filter,
  cik_limit=arguments.get("cik_limit"), cik_offset=...)`
  (`warehouse_orchestrator.py:1565-1576`, resolver defined at
  `warehouse_orchestrator.py:6179-6206`), which independently re-queries
  `db.get_tracked_ciks(tracking_status_filter)` from an **already-open**
  silver DB and only then slices by offset/limit
  (`warehouse_orchestrator.py:6202-6205`). That DB is opened via
  `_hydrate_silver_database_from_storage` + `_open_silver_database`
  (`warehouse_orchestrator.py:558-560`) — the monolith path, which only runs
  in the `not _using_shard_path` branch. This is the chicken-and-egg problem
  bootstrap-batch avoids: shard selection must happen **before** the DB is
  opened (to know which single shard file to hydrate), but bootstrap-next's
  current CIK-resolution mechanism requires the DB to already be open.
  `bootstrap-batch` sidesteps this only because its caller
  (`seed-bronze-batches`) hands it an already-resolved literal `cik_list` in
  `arguments`, needing no DB query at all.
- **Verdict: not trivial reuse, but a bounded, moderate lift that follows an
  already-proven pattern.** The data needed (`cik_snapshot.jsonl`) already
  exists upstream of every window; what's missing is wiring bootstrap-next's
  orchestrator branch to resolve `--cik-offset`/`--cik-limit` into literal
  CIK values from that snapshot (or an equivalent pre-shard-partitioned
  artifact, mirroring `_shard_partition_ciks`) **before** touching any DB,
  then hydrating only the overlapping shard — structurally the same shape as
  `bootstrap-batch`'s existing seed step, just needing a load_history-specific
  wiring path. The existing `shard_window_crosses_band_boundary`
  single-shard-write compromise (`warehouse_orchestrator.py:529-543`) would
  also need re-evaluating for load_history windows, since a 500-CIK window
  landing on a band boundary is not a corner case here — it also needs
  `_publish_shard_if_remote`'s single-owner promote model rather than
  `merge_candidate_into_canonical` (see §1). Also note: this snapshot-backed
  path only exists for the `load_history`-driven invocation of
  `bootstrap-next`; the standalone ad-hoc invocation (no load_history
  caller, default `tracking_status_filter="bootstrap_pending"`, no
  `cik_snapshot.jsonl` written) has no precomputed CIK list at all and would
  need either an explicit `--cik-list` or a live cross-shard/global pending
  index — but CLAUDE.md's Phased Pipeline section already discourages that
  standalone usage for anything but single-company ad-hoc loads, so it's not
  the primary target.

### 3. `daily_incremental` — NOT a simple routing reuse; genuinely cross-shard per run

- `_resolve_scope` for `daily-incremental` is date-range-based only
  (`business_date_start`/`business_date_end`), with no CIK list at all
  (`warehouse_orchestrator.py:6436-6455`).
- The actual CIK scope is **discovered during the run**, from the SEC daily
  index feed: `_load_daily_index_for_date` (called at
  `warehouse_orchestrator.py:1395-1407`, defined at
  `warehouse_orchestrator.py:5614`) returns `impacted_ciks` — whichever
  companies filed on that date — accumulated across the (possibly 7-day,
  per the "Daily accession-expansion" CLAUDE.md fix)
  `_date_range(business_date_start, business_date_end)` loop
  (`warehouse_orchestrator.py:1369-1427`). This requires an **already-open**
  `db` to run at all, since it writes to the global tables
  `stg_daily_index_filing`/`sec_daily_index_checkpoint`
  (`migrate_silver_shards.py:99-100`) before any CIK is known.
- After the scan, `impacted_ciks` is deduped, tracking status is seeded,
  filtered to the active universe, and sliced by `cik_offset`/`cik_limit`
  (`warehouse_orchestrator.py:1427-1436`) — but that offset/limit slices
  the day's **impacted set**, not a CIK-contiguous shard band. Which
  companies file SEC forms on a given day is inherently scattered across the
  entire CIK numeric range — there is no reason a day's filers cluster
  inside one shard's `[cik_min, cik_max]` band.
- **Verdict: genuinely new plumbing, and of a different kind than
  load_history's.** Even with a routing function available
  (`shards_for_window`/`band_for_cik`), a single daily_incremental run
  structurally needs to write into **multiple shards in the same run** —
  partition `impacted_ciks` by shard band after the daily-index scan, then
  hydrate/open/merge/publish each affected shard separately, none of which
  exists today. This breaks the "each shard owned by exactly one writer per
  run" assumption `_publish_shard_if_remote` depends on
  (`warehouse_orchestrator.py:1290-1294`) — daily_incremental would need
  either a real shard-aware merge (not the blind ETag promote bootstrap-batch
  uses) or a redesign into shard-scoped sub-runs. It also raises an
  unresolved design question this ticket doesn't answer: whether/how the
  `GLOBAL_TABLES` writes (`stg_daily_index_filing`,
  `sec_daily_index_checkpoint`) get replicated into every shard a
  multi-shard daily_incremental run touches, since today those are written
  once per monolith and migration-time replicated into all 4 shards
  identically.

### 4. `bootstrap` — same cross-shard-per-run problem as daily_incremental in its default/typical invocation

- Production's `bootstrap` state machine invokes it two ways:
  - Default/typical: `bootstrap --run-id $$.Execution.Name` with **no**
    `cik_list` (`infra/scripts/deploy-aws-application.sh:1250`). This
    resolves via `_resolve_bootstrap_target_ciks(raw_ciks=scope.get("cik_list")`
    `= None, tracking_status_filter=arguments.get("tracking_status_filter")`
    `or "active", cik_limit=None, cik_offset=0)`
    (`warehouse_orchestrator.py:1506-1514`, resolver at
    `warehouse_orchestrator.py:6179-6206`) → `db.get_tracked_ciks("active")`
    **unsliced** → the entire active CIK universe in one run, structurally
    identical to daily_incremental's cross-shard problem (§3).
  - Optional: `bootstrap --run-id ... --cik-list $.cik_list`
    (`workflow_cik_command_expression`,
    `infra/scripts/deploy-aws-application.sh:1262-1269`) — if a caller
    supplies an explicit, single-shard-bounded `cik_list` this way, shard
    routing for that invocation is exactly as trivial as
    `bootstrap-batch`'s today (same `arguments.get("cik_list")` shape,
    same `_resolve_scope` field at `warehouse_orchestrator.py:6417-6422`).
    But this is not how `bootstrap` runs by default in prod.
- **Verdict: trivial only for the (currently unused-by-default) explicit
  `--cik-list` invocation; genuinely new multi-shard plumbing needed for the
  default/typical unscoped invocation**, same shape and same open questions
  as daily_incremental (§3) — GLOBAL_TABLES replication, multi-shard
  merge/publish, no single-owner-per-shard guarantee.

### Summary table

| Command | CIK scope available at publish time? | Reuse vs. new plumbing |
|---|---|---|
| `bootstrap-batch` (baseline) | Yes — explicit `cik_list` arg, pre-partitioned upstream by `seed-bronze-batches` | Existing, working |
| `load_history` / `bootstrap-next` per window | Data exists (`cik_snapshot.jsonl` from `compute-windows`), but the command doesn't read it — re-derives via a live DB query that requires the DB already open | **Moderate new plumbing** — wire bootstrap-next to resolve shard index from the snapshot before DB hydration, mirroring the existing `seed-bronze-batches` pattern |
| `daily_incremental` | No — CIK scope (`impacted_ciks`) is only known after an already-open DB scans the SEC daily index, and is inherently scattered across all shard bands, not one band | **New plumbing of a different kind** — multi-shard-per-run write path; single-owner-per-shard assumption doesn't hold |
| `bootstrap` (default invocation) | No — resolves the entire active universe unsliced from an already-open DB | **Same multi-shard problem as `daily_incremental`** (trivial only if an explicit bounded `cik_list` is passed, which isn't the default path) |
