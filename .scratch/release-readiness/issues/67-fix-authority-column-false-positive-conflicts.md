# Fix authority-column false-positive conflicts in silver merge

Type: task
Status: resolved

## Question

Why did the `daily-incremental-postdeploy-1785701660` production execution's `ReduceIdentityRefresh`
step run for 55+ minutes on a workload (3 small identity-refresh batches, 500/460/250 CIKs) that
should have taken well under a minute, and how should it be fixed?

## Root cause

Found via direct code reading, then confirmed empirically by downloading real prod data
(canonical `silver.duckdb`, 1021.8MB / 3,375,440 `sec_company_filing` rows; the live run's actual
batch-1 delta, 500 CIKs) and reproducing the merge locally:

`sec_company_filing`'s `ProtectedTablePolicy` (`silver_protection.py:92-94`) declares
`authority_column="last_synced_at"` but leaves `provenance_columns` empty. The delta computation
(`_delta_rows_as_dicts`, SQL `EXCEPT` over *all* columns) and the in-loop `differing` check both
compared the authority column itself — which is bumped to "now" on every re-sync regardless of
whether the filing's real data changed. Result: **every previously-seen row in every re-synced
CIK's filing history registered as "different," forever**, even when every real column (`form`,
`filing_date`, `size`, `primary_document`, ...) was byte-identical — confirmed by diffing a live
row where only `last_sync_run_id`/`last_synced_at` differed.

Measured on real data: batch-1's delta (500 CIKs) produced **452,996 of 452,996** `sec_company_filing`
candidate rows flagged "different" — 100% noise, zero genuine content change. Real single-row
`UPDATE` cost (measured): 1.664ms/row → **~753s (12.6 min) for this one table, in this one batch,
alone**. With 4 candidates (reference + 3 batches) across 31 protected tables, this fully explains
the observed 55+ minute runtime without any other contributing cause.

## Fix

`edgar_warehouse/silver_protection.py`:
- Added `_comparable_columns(policy, all_columns)`: the columns that determine whether two
  same-key rows are *meaningfully* different — excludes business keys, `_PROVENANCE_COLUMNS`,
  `policy.provenance_columns`, **and the table's own declared `authority_column`**. Generic
  across all 31 `PROTECTED_TABLE_REGISTRY` policies (all 17 declared authority columns are one of
  `last_synced_at`/`fetched_at`/`extracted_at`/`ingested_at`/`updated_at` — confirmed via grep —
  so one exclusion rule covers the whole registry, not a per-table patch).
- Rewrote `_delta_rows_as_dicts` from a full-row `EXCEPT` to a `NOT EXISTS` anti-join keyed on
  `business_keys` and scoped to `comparable_columns` (`IS NOT DISTINCT FROM` for null-safety) —
  a row whose only change is a provenance/authority column now never even reaches Python, let
  alone triggers `_resolve_conflict`/`_update_row`.
- `differing` in `merge_candidate_into_canonical`'s per-row loop now reuses the same
  `comparable_columns` set (was duplicating the exclusion logic inline) — one source of truth.
- Preserved accurate `rows_unchanged` accounting: rows filtered by the anti-join are counted via
  a cheap `COUNT(*)` (not fetched) so the report still sums to the candidate's true row count,
  including the case where *every* candidate row for a table is provenance-only-different (the
  loop now still records `tables_merged`/`rows_unchanged` in that case instead of skipping the
  table's accounting entirely).
- Added `_emit_table_merge_event`: one `{"event": "silver_table_merged", "table", "rows_inserted",
  "rows_updated", "rows_unchanged"}` JSON line per table to stderr, matching `gold_models.py`'s
  existing event-logging convention. `merge_candidate_into_canonical` previously emitted nothing
  at all — this exact incident was invisible in CloudWatch and required downloading prod data
  locally to diagnose. Complements (does not duplicate) [ticket 64](64-add-identity-refresh-reducer-progress-logging.md)'s
  broader reducer-stage logging gap.

## Validation

- Local reproduction against real prod data before writing any code: old `EXCEPT` delta =
  452,996 rows; new anti-join delta = **542 rows** (99.88% reduction), query itself faster
  (1.75s vs 9.93s — anti-join can use the primary-key index; `EXCEPT` had to hash/compare the
  whole table).
- Real end-to-end run of the actual (fixed) `merge_candidate_into_canonical` against real prod
  canonical + the live run's real batch-1 delta: **11.04s total** for all 5 tables the candidate
  touches, versus an extrapolated ~753s for `sec_company_filing` alone under the old code.
  `sec_company_filing`: 0 inserted, 542 genuinely updated, 452,454 correctly unchanged.
- Existing test suite: two pre-existing tests
  (`test_merge_only_reads_canonical_rows_the_candidate_touches`,
  `test_merge_only_reads_candidate_rows_that_actually_changed`) had encoded the bug as intended
  behavior — their "existing key, updated value" fixture only changed `last_synced_at`, asserting
  it should count as a real update. Both fixed to make a genuine content change (matching this
  repo's established precedent for correcting tests that lock in a bug, e.g. the ADV Firm Roster
  fix documented in `CLAUDE.md`), plus their `rows_unchanged` assertions updated to the new,
  more complete accounting.
- Three new regression tests added (`tests/application/test_warehouse_orchestrator_mdm.py`):
  authority-column-only change → `unchanged`, zero writes, canonical's original timestamp
  preserved; a genuine content change still updates and advances the authority column correctly;
  `NULL`-vs-`NULL` on a comparable column is not a false-positive difference.
- Full suite: `tests/unit tests/application tests/architecture tests/mdm` — 1676 passed, 1
  pre-existing unrelated failure (`test_go_live_wizard.py::test_plan_prints_preview_only_aws_ordered_commands`,
  confirmed via `git stash` to fail identically on `main` before this change — an environment/AWS-profile-dependent
  test, not caused by this fix).

Reviewed via `/gof-refactor-reviewer` and `advisor` before implementation (per explicit user
request) — the advisor caught that fixing only the `differing` check (not `_delta_rows_as_dicts`'s
comparison) would have left the 452,996-row materialization/lookup cost in place, and that
`sec_company_sync_state`/`sec_source_checkpoint`/`discovery_checkpoint` (not
`sec_company_filing.last_synced_at`) are the platform's actual freshness/idempotency gate —
confirmed via `warehouse_orchestrator.py:5161-5180` and a repo-wide grep finding no code path
reads this column as a staleness signal, so skipping its write on a no-op row is safe.

Implemented on branch `claude/fix-silver-merge-authority-column-noise` — PR #330
(https://github.com/paulananth/edgartools-platform/pull/330), merged to `main` as `4e78725d`
(squash). CI green (Application/MDM/Unit py3.11+py3.12/Shell lint/dbt compile all pass). The
prior stalled execution (`daily-incremental-postdeploy-1785701660`) was manually stopped
(superseded, still running old code) and its `pipeline_run_lease` explicitly released via
`release-identity-refresh-lease --run-id daily-incremental-postdeploy-1785701660` (exit 0) so it
doesn't block the next run.

**Deployed to prod 2026-08-02** (digest `sha256:393e8157c4e0b34a76161ac456ef2513d0bbce6ea3f3a8cd96059b8fe8dae57c`,
via `deploy-aws-application.sh --env prod`), then verified live with a fresh execution,
`daily-incremental-ticket67-verify-1785709701`. **Confirmed fixed**: `ReduceIdentityRefresh`
(id 39-44 in the execution history) ran from `TaskSubmitted` 18:57:45.358 to `TaskSucceeded`
19:02:18.507 -- **4 minutes 33 seconds total** (ECS provisioning + image pull + hydrating the
1021.8MB canonical `silver.duckdb` + all 3 identity-refresh batches + republish), versus 55+
minutes with zero forward progress in the pre-fix execution. Live `silver_table_merged` events
matched the pre-deploy local reproduction almost exactly: `sec_company_filing` batch 1 (500
CIKs) showed `rows_updated: 542, rows_unchanged: 452454` -- the identical 542 figure predicted
by the local dry run against the same real data before this was ever deployed. Batches 2/3:
208/195472 and 362/26323 respectively. No stalling, no timeout, no false-positive noise. This
is the real production timing evidence tickets 49/61/63 were waiting on.

## Done when

Done — fix implemented, tested against real production data end-to-end (not just synthetic
fixtures), regression tests added, full suite green modulo one confirmed-pre-existing unrelated
failure.
