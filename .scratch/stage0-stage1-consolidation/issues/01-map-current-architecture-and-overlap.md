# Map current Stage0/1/1B architecture, overlap, and sequencing constraint

Type: research
Status: resolved

## Question

Now that `load_history`'s Stage0CompanyIdentity was restructured to
delta-then-reduce with explicit CIK-list batches (mirroring Stage1's own
shape), is it structurally redundant with Stage1 (WindowedBootstrap) and/or
Stage1B (fundamentals)? Precisely: what does each stage actually
fetch/write, is the claimed "Stage0 must run before Stage1/1B" invariant a
real code dependency or an assumed one, and — applying `/gof-refactor
-reviewer`'s Rule 0 — is there real evidence of repeated-change cost that
justifies consolidating them now?

## Answer

**Current architecture (citations to code as of 2026-08-10):**

- **Stage0CompanyIdentity** (`deploy-aws-application.sh:2301-2340`):
  `MaxConcurrency=1`, `ToleratedFailurePercentage=0` Distributed Map over
  `cik_batches.jsonl` (written once by `ComputeWindows`,
  `warehouse_orchestrator.py:2661-2671`). Each batch:
  `bootstrap-fundamentals --mode company-identity --cik-list <batch>
  --identity-refresh-run-id <run>`. `bootstrap_fundamentals.py:246-278`
  calls `_run_submissions_bronze_then_silver(..., include_pagination=True,
  load_mode="company_identity")` with `artifact_policy`/`parser_policy`
  left at `"none"`/`"none"` (`warehouse_orchestrator.py:3018-3019`). Each
  batch persists an immutable delta (`persist_batch_outcome`,
  `bootstrap_fundamentals.py:300-324`); a single `ReduceIdentityRefresh`
  state (`deploy-aws-application.sh:2347-2361`) folds the reference
  snapshot + all deltas into canonical once, before `Stage1Parallel`.

- **Stage1 / WindowedBootstrap, Branch A** (`deploy-aws-application.sh
  :2404-2440`): same shape Map over `cik_windows.jsonl` (same underlying
  ordered CIK list as Stage0's batches — both from
  `LOAD_HISTORY_TRACKING_STATUS_FILTER`,
  `warehouse_orchestrator.py:2610`/`bootstrap_fundamentals.py:447`). Each
  window: `bootstrap-next --silver-only --cik-limit ... --cik-offset ...
  --artifact-policy <policy> --run-id <run>`.
  `warehouse_orchestrator.py:1470-1525` resolves CIKs via
  `_resolve_bootstrap_target_ciks` (`warehouse_orchestrator.py:6101-6128`,
  MDM tracking status — unrelated to Stage0's output), then calls the
  **identical function** `_run_submissions_bronze_then_silver(...,
  include_pagination=True, artifact_policy="all_attachments",
  parser_policy="configured_forms", load_mode="bootstrap_full")`
  (`warehouse_orchestrator.py:1490-1504`) — everything Stage0 does, plus
  the ownership/ADV/13F attachment fetch+parse tail
  (`_run_configured_form_artifact_pipeline`,
  `warehouse_orchestrator.py:3201-3218`).

- **Stage1B** (`deploy-aws-application.sh:2461-2577`): three sequential
  Maps over `cik_windows.jsonl` after Branch A. `entity-facts` calls SEC's
  companyfacts API directly, no dependency on Branch A's output
  (`bootstrap_fundamentals.py:15-19,192`). `per-filing`/`thirteenf` read
  `sec_company_filing` rows from silver (`source=db`,
  `bootstrap_fundamentals.py:192`; confirmed in
  `fundamentals_ingest.py:155-164`) — a genuine read-after-write
  dependency, but satisfied by Stage1 alone (Stage1 writes
  `sec_company_filing` regardless of whether Stage0 ran — see overlap
  below), not specifically by Stage0.

**Overlap: Stage0's output is a strict subset of Stage1's own capture.**
Both call `_run_submissions_bronze_then_silver` over the same ordered CIK
list, both `include_pagination=True`, both land in
`_apply_submission_snapshot_to_silver` → `db.stage_submission()`
(`warehouse_orchestrator.py:4826-4836`), which unconditionally writes
`sec_company`/`sec_company_filing`/`sec_company_address`/
`sec_company_former_name`. Stage1 additionally fetches ownership/ADV/13F
attachments. Because `sec_source_checkpoint` is in
`EXCLUDED_OPERATIONAL_TABLES` (`silver_protection.py:289-306`), Stage0's
checkpoint writes never reach canonical, so Stage1's fresh local DB always
misses the checkpoint check (`warehouse_orchestrator.py:4778-4784`) and
re-runs `db.stage_submission()` in full per CIK — **the SEC network fetch
is not duplicated** (`_resolve_submissions_main_cached_snapshot`'s bronze
glob fallback, `warehouse_orchestrator.py:5163-5169`, finds Stage0's
already-durable S3 objects), but the parse + 4-table DuckDB write is
genuinely redone. Stage1B is genuinely disjoint — not a merge candidate.

**Sequencing constraint — assumed, not enforced.**
`deploy-aws-application.sh:2252-2259` claims Stage0 must run first "since
IS_INSIDER relationship derivation already depends on resolved Company
entities." Traced: `_derive_is_insider` (`edgar_warehouse/mdm/pipeline.py
:781-792`) resolves issuer CIKs via `MdmCompany`
(`pipeline.py:1543-1550`) — an MDM Postgres/Snowflake entity, populated by
`mdm run --entity-type all` (Stage 2), which per CLAUDE.md's Phased
Pipeline diagram runs only after **both** Stage1 and Stage1B complete.
`_resolve_bootstrap_target_ciks`/`_resolve_fundamentals_ciks` derive their
CIK universe from MDM `tracking_status` (set at seed-universe time), never
from Stage0's silver output. No code path fails, skips, or reads empty
data if Stage0 never ran — by the time the invariant would matter
(Stage 2), Stage1 alone has already satisfied it. **The comment is stale
and should be corrected regardless of what this map decides.**

**GoF-refactor-reviewer verdict (Rule 0 applied):** real, evidenced
repeated-change cost exists, but it's not about the Stage0/Stage1
boundary specifically — it's a shared pattern (per-task full-canonical
hydrate + per-task full-canonical merge-publish / un-streamed
accumulation) recurring across multiple stages independently of which one
carries it. Git log shows this OOM class fixed three times for Stage0 in
one week (Aug 5-9), then hit again for Stage1's own WindowedBootstrap on
Aug 10 (`deploy-aws-application.sh:2255-2263`'s own comment: "This is a
stopgap ... the real fix ... is tracked separately" — confirmed via repo
search that no such ticket actually exists anywhere in `.scratch/`). The
duplicate Stage0-vs-Stage1 work itself is CPU-bound (no network), likely
small relative to Stage1's own artifact-fetch phase, and unmeasured —
unlike the hydrate/merge cost ticket 02 of the sibling map explicitly
quantified before acting. Evidence does not clearly clear Rule 0's bar for
the merge itself; the higher-priority, better-evidenced problem is
Stage1's own un-streamed accumulation, sharing the exact class of fix
Stage0 just proved out.

**If pursued, the mechanical shape requires no new code:** delete
Stage0Map/`ReduceIdentityRefresh`, let Branch A's own
`_run_submissions_bronze_then_silver` call (already `artifact_policy=
"all_attachments"`, a superset) stand alone. `SeedUniverse`→
`MdmSeedUniverse`→`ComputeWindows` still run (seed MDM, write
`cik_windows.jsonl`) without also pre-batching `cik_batches.jsonl`.
Biggest risks: (1) discards the Aug 5-9 delta-then-reduce machinery's only
`load_history` caller (stays alive via `daily_incremental`); (2) any
redeploy of `write_load_history_definition` re-registers the state
machine — a retry/restart after redeploy hits an unexercised shape at
exactly the moment ticket 42's backfill is trying to close out; (3) doing
this before Stage1's own hydrate/publish gets the same delta-then-reduce
treatment means the merge inherits Stage1's still-broken accumulation
instead of fixing it.
