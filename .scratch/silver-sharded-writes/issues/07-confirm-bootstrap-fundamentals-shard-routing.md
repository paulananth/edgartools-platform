# Confirm Shard-Routing Requirements for bootstrap_fundamentals.py's Stage 1B Writer

Type: research
Status: resolved
Blocked by: none

## Question

Ticket 02's research found a fourth primary-write surface not named in this
map's original Destination: `bootstrap_fundamentals.py:135` writes the
canonical monolith directly and is never routed through `_using_shard_path`
at all. This is the writer behind `load_history`'s `FetchEntityFacts`/
`FetchPerFilingFundamentals`/`FetchThirteenFHoldings` Maps (the same three
Maps whose `ToleratedFailurePercentage` was raised from 0 to 15 earlier the
same session this map was charted — see `.scratch/ecs-cost-sizing/issues/21-*`
— these Maps are windowed the same way `WindowedBootstrap` is, via
`$.window_offset`/`$.window_limit` per CIK window).

Answer the same question ticket 01 answered for `bootstrap-next`, but for
`bootstrap_fundamentals.py`: does this command already have its window's CIK
range/list available at the point it would need to resolve a shard index
(mirroring `compute-windows`'s already-written `cik_snapshot.jsonl`, or does
it re-derive its CIK scope independently, the same chicken-and-egg problem
ticket 01 found in `bootstrap-next`)? Read `bootstrap_fundamentals.py` in
full, and the three ASL states in `infra/scripts/deploy-aws-application.sh`
(`fundamentals_entity_facts`/`fundamentals_per_filing`/
`fundamentals_thirteenf`) that invoke it. Also confirm: does
`bootstrap_fundamentals.py` call `merge_candidate_into_canonical` directly
(same as the monolith path) or something else — cite the exact merge/publish
call site, since ticket 01 found the sharded publish path
(`_publish_shard_if_remote`) bypasses that merge function entirely, and any
command moving onto shards inherits that same open question.

## Deliverable

Answer inline in this ticket's resolution comment — cite every claim to a
`file:line` reference.

## Answer

### 1. Confirmed: `bootstrap_fundamentals.py` never touches the shard path at all

`grep` for `_using_shard_path`/`_hydrate_shard_for_window`/`_publish_shard_if_remote`/`shard`
across `edgar_warehouse/application/commands/bootstrap_fundamentals.py` returns zero matches.
The command always: hydrates the full monolith
(`_hydrate_silver_database_from_storage(context)`,
`edgar_warehouse/application/commands/bootstrap_fundamentals.py:134`, skipped only for the
`company-identity`-with-explicit-`--cik-list` case — see §4), opens it via
`open_silver_database(context.silver_root)`
(`bootstrap_fundamentals.py:135`), and — for the three windowed Stage 1B modes this ticket
asks about — publishes it back via `_publish_silver_database_if_remote(context)`
(`bootstrap_fundamentals.py:333`).

### 2. Merge/publish call site: same monolith path as `bootstrap-next`, not a new one

`bootstrap_fundamentals.py:333`'s `_publish_silver_database_if_remote` is the identical
function `bootstrap-next` uses (imported from `warehouse_orchestrator.py`, defined at
`edgar_warehouse/application/warehouse_orchestrator.py:1045-1133`). Inside it,
`merge_candidate_into_canonical` is called at `warehouse_orchestrator.py:1114` (imported at
`warehouse_orchestrator.py:79`), merging the local candidate DuckDB into a freshly
downloaded copy of canonical before an ETag-guarded promote — the exact mechanism ticket 01
describes for the monolith path (ticket 01 §1). There is no shard-specific publish call
anywhere in `bootstrap_fundamentals.py`; it is a plain, unmodified caller of the same
monolith merge/publish function every non-`bootstrap-batch` command uses.

### 3. CIK scope availability: identical chicken-and-egg problem to `bootstrap-next`

The three ASL states (`fundamentals_entity_facts`, `fundamentals_per_filing`,
`fundamentals_thirteenf` in `infra/scripts/deploy-aws-application.sh:2529-2671`) are windowed
`Map`s reading the **same S3 artifact** `WindowedBootstrap` reads:
`warehouse/bronze/reference/cik_universe/runs/{execution}/cik_windows.jsonl`
(`deploy-aws-application.sh:2549,2622,2658` — byte-identical `Key` expression to
`WindowedBootstrap`'s own `ItemReader`), written once by `compute-windows` before any window
task runs (ticket 01 §2, `warehouse_orchestrator.py:2715-2724`). Each Map item invokes
`bootstrap-fundamentals --mode <entity-facts|per-filing|thirteenf> --cik-offset
$.window_offset --cik-limit $.window_limit --run-id ...`
(`deploy-aws-application.sh:2526,2605,2643`) — **no `--cik-list`**, exactly the windowed
no-explicit-list case.

Inside the command, `_resolve_fundamentals_ciks` (`bootstrap_fundamentals.py:417-451`)
resolves the actual CIK batch: with no `raw_cik_list`, it calls
`db.get_tracked_ciks(LOAD_HISTORY_TRACKING_STATUS_FILTER)`
(`bootstrap_fundamentals.py:447`, filter constant `= "active,bootstrap_pending"` at
`warehouse_orchestrator.py:219`) — **from the already-open `db`** opened three lines earlier
at `bootstrap_fundamentals.py:135`, then slices by offset/limit
(`bootstrap_fundamentals.py:448-450`). This is the identical shape ticket 01 found for
`bootstrap-next`'s `_resolve_bootstrap_target_ciks` (ticket 01 §2,
`warehouse_orchestrator.py:6179-6206`): the data needed to resolve this window's CIK range
already exists upstream, snapshot-free-of-any-DB-open, in `cik_snapshot.jsonl` (written
alongside `cik_windows.jsonl` by the same `compute-windows` step,
`warehouse_orchestrator.py:2726-2728`) — but the command doesn't consult it, re-deriving the
same list from a live query against an already-hydrated monolith instead. The function's own
docstring confirms the two paths are meant to line up exactly: "Mirrors Branch A's
`_resolve_bootstrap_target_ciks` semantics so the two parallel branches process identical
windows for the same `{window_offset, window_limit}` Map item"
(`bootstrap_fundamentals.py:426-429`) — same tracking-status filter, same ordering, same
windowing arithmetic, just independently re-run against a second already-open DB handle.

### 4. Is the fix trivially the same as ticket 01's, or does fundamentals-fetching need something more?

**Trivially the same fix — no additional cross-shard complication**, for a stronger reason
than "same shape": the three modes' own downstream reads are provably single-shard-safe
against the window's own CIK band, not just plausibly so.

- **`entity-facts`**: `source = None` for this mode (`bootstrap_fundamentals.py:192`) — it
  calls the SEC companyfacts API directly per CIK, no read of any other silver table at all
  (`run_bootstrap_entity_facts`, `edgar_warehouse/application/workflows/fundamentals_ingest.py:360-…`,
  writes only via `db.merge_financial_facts`/`merge_accounting_flags`/`merge_financial_derived`).
  The subsequent `backfill_accounting_flags(cik=cik, silver=db)` loop
  (`bootstrap_fundamentals.py:225-229`) is also strictly per-CIK. Zero cross-shard reads.
- **`per-filing`**: reads Branch A data with `SELECT ... FROM sec_company_filing f WHERE
  f.cik IN (cik_placeholder)` where `cik_placeholder` is built directly from the resolved
  `cik_list` (`fundamentals_ingest.py:152-164`); the later `sec_filing_attachment`/
  `sec_raw_object` reads are keyed off `accession_number`s pulled from those same
  CIK-filtered filing rows (`fundamentals_ingest.py:223-224`). `sec_company_filing` is a
  CIK-direct table and `sec_filing_attachment` is an issuer-CIK-join table in ticket 01's own
  routing taxonomy (ticket 01 §0, `migrate_silver_shards.py:38-49,55-81`) — both keyed to
  exactly the filer/issuer CIKs already inside this window, i.e. the same shard band
  `bootstrap-next` would hydrate for the identical `{window_offset, window_limit}`.
- **`thirteenf`**: same pattern — `SELECT ... FROM sec_company_filing f WHERE f.cik IN
  (cik_placeholder) AND f.form IN ('13F-HR', '13F-HR/A')`
  (`fundamentals_ingest.py:500-509`), where the CIK is the 13F filer/manager itself (one of
  the window's own CIKs), then `sec_filing_attachment`/`sec_raw_object` reads keyed off those
  filings' accessions (`fundamentals_ingest.py:528-529,567-568,582-583`). Same single-shard
  guarantee as `per-filing`.
- **`company-identity`** (not one of the three windowed ASL states this ticket covers — it's
  invoked separately with an explicit `--cik-list`, `deploy-aws-application.sh:3453`, and
  guarded to require one, `bootstrap_fundamentals.py:83-88`) is out of scope here; noted only
  for completeness since the file was read in full.

Because every windowed mode's reads are `WHERE cik IN (<this window's own cik_list>)` against
tables ticket 01 already classified as CIK-direct or issuer-CIK-join, there is no scenario
where a mode needs company/filing data for a CIK outside its own window — unlike
`daily_incremental`/`bootstrap`'s cross-shard problem (ticket 01 §3-4), fundamentals-fetching
never needs to read a CIK it wasn't already assigned. The fix is therefore **the identical
fix ticket 01 recommended for `bootstrap-next`**: wire `_resolve_fundamentals_ciks` to read
`cik_snapshot.jsonl` (or an equivalent pre-shard-partitioned artifact) and resolve the
shard index **before** `_hydrate_silver_database_from_storage`/`open_silver_database` run,
then hydrate/open/publish only the overlapping shard via the existing
`_hydrate_shard_for_window`/`_publish_shard_if_remote` functions
(`warehouse_orchestrator.py:1211-1255,1276-1339`) instead of the monolith path. The same
`shard_window_crosses_band_boundary` single-shard-write compromise
(`warehouse_orchestrator.py:529-543`) ticket 01 flagged for `bootstrap-next` applies
identically here, since these Maps use the literal same window boundaries. In fact, because
`_resolve_fundamentals_ciks` is deliberately designed to reproduce `bootstrap-next`'s exact
CIK list for a given `{window_offset, window_limit}` (§3 above), a real implementation could
likely reuse the same resolved shard index/CIK list `bootstrap-next`'s fix computes for that
window rather than re-deriving it independently — worth flagging to whoever picks up the
implementation ticket, though this ticket's scope is confirmation, not design.

### Summary

| Question | Answer |
|---|---|
| Does it call `merge_candidate_into_canonical` directly? | Indirectly, via the same `_publish_silver_database_if_remote` (`bootstrap_fundamentals.py:333` → `warehouse_orchestrator.py:1045-1133` → `merge_candidate_into_canonical` at `warehouse_orchestrator.py:1114`) — identical monolith path to `bootstrap-next`, no shard-specific publish exists in this file at all. |
| Is the window's CIK range available before DB-open? | Data exists (`cik_snapshot.jsonl`, written by the same `compute-windows` step), but the command doesn't read it — `_resolve_fundamentals_ciks` (`bootstrap_fundamentals.py:417-451`) re-derives it from `db.get_tracked_ciks(...)` on an already-open DB, same chicken-and-egg gap ticket 01 found in `bootstrap-next`. |
| Is the fix the same as ticket 01's, or does fundamentals-fetching need more? | Same fix, and simpler to trust: all three windowed modes' reads are provably scoped to `WHERE cik IN (this window's own cik_list)` against CIK-direct/issuer-CIK-join tables, so there is no cross-shard read requirement to design around — unlike `daily_incremental`/`bootstrap`. |
