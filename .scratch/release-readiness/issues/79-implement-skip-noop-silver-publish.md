Type: task
Status: in_progress

## Question

Implement [pipeline-throughput-architecture ticket 10](../../pipeline-throughput-architecture/issues/10-decide-gold-refresh-unconditional-silver-republish.md)'s
decision: skip `_publish_silver_database_if_remote`'s expensive
`shutil.copy2` + merge + promote cycle whenever no
`PROTECTED_TABLE_REGISTRY` table in the local candidate actually differs
from what was hydrated at task start.

## Why this matters

Measured live ([ticket 07](../../pipeline-throughput-architecture/issues/07-profile-gold-refresh-stage-breakdown.md)):
this step is 35.9% of `gold-refresh`'s total wall-clock (60.65s of
169.12s) for a **structurally guaranteed no-op** -- `gold-refresh` never
writes protected tables, and its only local writes
(`pipeline_run`/`sec_sync_run`) are `EXCLUDED_OPERATIONAL_TABLES`, which
the merge loop never pulls from the candidate at all. Zero bytes of real
content move, on every single run. `gold-refresh` isn't the only command
that could hit this -- any run where nothing new arrived since the last
publish (e.g. a `daily-incremental` re-run with no new filings in its
window) pays the same unnecessary cost.

## Decision already made (ticket 10)

- **General rule, not a `gold-refresh`-specific special case.**
- **Dynamic detection, not a static command allowlist.** A hardcoded
  "commands known to be read-only" list was explicitly rejected -- it
  carries a real silent-data-loss risk if a command later gains real
  writes and its list entry isn't removed. Instead: a cheap runtime check
  of whether any `PROTECTED_TABLE_REGISTRY` table's content actually
  changed, computed fresh on every run.
- **Must check only protected tables, not the whole local file.**
  `complete_pipeline_run`/`complete_sync_run` write
  `EXCLUDED_OPERATIONAL_TABLES` bookkeeping rows on every command's local
  copy -- a naive "is the local file byte-identical to what was hydrated"
  check would never trigger and defeat the whole point.

## Implementation approach (needs design during implementation, not fully specified here)

Two workable shapes, either acceptable, pick during implementation:

1. **Row-count comparison**: cheap `SELECT COUNT(*)` per
   `PROTECTED_TABLE_REGISTRY` table, taken once right after hydration and
   again right before publish. Cheapest, but a table with the same row
   count post-hydration could theoretically have had a row replaced
   (delete+insert with different content, same count) -- verify this
   can't happen given how silver writes work (append/upsert-only, per
   CLAUDE.md's "SEC data idempotency" -- likely fine, confirm during
   implementation) before relying on count alone.
2. **Lightweight hash per protected table** (e.g. a fast aggregate
   checksum over each table's rows): slightly more expensive than a
   count, closes the gap above if it turns out to matter.

Whichever is chosen, this pre-check must be **cheap relative to the full
merge it's replacing** -- if the check itself scans full table contents
at the same cost as the merge would have, it defeats the purpose. Look at
whether `SilverDatabase` already tracks anything usable (e.g. a
last-modified/dirty marker per table from existing write paths) before
adding new bookkeeping.

## Test plan

Real DB-backed tests (per this workstream's established discipline,
tickets 67-78):
1. **No-op case**: candidate identical to canonical on all protected
   tables -- assert publish is skipped (no `copy2`, no S3 staged write,
   no promote call) and the function still returns a valid result
   consistent with "nothing changed."
2. **Real-change case**: candidate differs on at least one protected
   table -- assert the full merge/publish path still runs exactly as
   today, unchanged behavior.
3. **Excluded-table-only-change case**: candidate's only diff is in
   `pipeline_run`/`sec_sync_run` (the every-run bookkeeping write) --
   assert this alone does **not** trigger the full merge (this is the
   specific case that would have defeated a naive whole-file check).
4. **Live measurement**: run `gold-refresh` post-fix, confirm the
   35.9%/60.65s cost drops to roughly the cheap-check's own cost.

## Done when

Implemented, all test cases passing, full suite green, live measurement
confirms the no-op publish cost is eliminated for `gold-refresh` without
changing behavior for any command that genuinely writes silver data.

## Progress (2026-08-03) — code + tests done, live measurement not yet run

Implemented via `compute_silver_fingerprint` (new,
`edgar_warehouse/silver_protection.py`), a local-only, no-S3-calls
fingerprint of a silver DuckDB file: the full sorted table-name set (all
tables, so a new unregistered table always changes it) plus, for every
`PROTECTED_TABLE_REGISTRY` table present, a `(row_count,
BIT_XOR(HASH(all columns)))` pair -- order-independent, catches a
same-row-count in-place content update (e.g. an authority-column-resolved
conflict), which a row-count-only check would miss (confirmed both ways
via a local DuckDB smoke test before committing to the hash approach).
`EXCLUDED_OPERATIONAL_TABLES` (`pipeline_run`/`sec_sync_run` bookkeeping)
are deliberately excluded from the content fingerprint.

Wired into `warehouse_orchestrator.py`: `_hydrate_silver_database_from_storage`
snapshots this fingerprint immediately after writing the downloaded
canonical bytes locally (before any caller opens the DB and runs schema
DDL) into a local JSON sidecar
(`<local_path>.protected-fingerprint.json`); any stale sidecar from a
reused ECS task volume is deleted up front, so "sidecar present" always
means "this process just hydrated." `_publish_silver_database_if_remote`
compares the candidate's current fingerprint against the sidecar *before*
`read_object_version`/download/`copy2`/merge/upload -- on an exact match
it skips the entire cycle and returns a `{"skipped": True, "tables_merged":
[], ...}` result with zero S3 calls. Sidecar absence (hydration didn't
run, or the very first publish with no prior canonical) always falls
through to the unchanged full-merge path -- skip requires positive proof
of a match, never a default. Both the hydration and publish-time
fingerprint calls are wrapped fail-open (`except Exception: fingerprint =
None`) so a fingerprint failure of any kind can never break hydration or
force an incorrect skip -- worst case is just no optimization, never a
correctness regression. `bootstrap_fundamentals.py`'s caller updated to
branch on `upload_result.get("skipped")` so a skip logs
`silver_database_publish_skipped_noop` and `metrics["silver_database_uploaded"]
= False`, instead of the previous code lying `True` for a no-op.

Reviewed via `advisor` before implementation, which caught a real gap in
the first draft (fingerprint scoped to registry tables only would have let
a brand-new unregistered domain table silently slip past
`merge_candidate_into_canonical`'s own fail-closed unclassified-table
guard) -- fixed by making the table-*name-set* comparison cover every
table in the file, not just registry ones, before any implementation
landed.

**Test plan items 1-3 + advisor's added 5th case**: done, all passing
(`tests/unit/test_skip_noop_silver_publish.py`, real
`SilverDatabase`-backed, not mocked): no-op skip (asserts
`read_object_version`/`write_staged_bytes`/`promote_staged` are never
called), a real protected-table change still runs the full merge
unchanged, an excluded-table-only (`pipeline_run`) write is still
correctly skipped, and a brand-new unregistered table forces the merge
and still trips `SilverPublicationError`. Confirmed via `git stash` that
2 of 4 tests fail against pre-fix code (they reach for real S3 access
under the old unconditional-merge path and hit `PermissionError`); the
other 2 (real-change, unregistered-table) correctly pass on both sides,
proving no behavior change for genuine writes. One pre-existing test
(`test_hydrate_silver_database_from_remote_storage`, which hydrates with
placeholder non-DuckDB bytes `b"duckdb-bytes"`) initially broke because
fingerprinting isn't wrapped fail-open yet at that point -- fixed by
adding the fail-open wrapping described above, not by weakening the test.
Full suite (`tests/unit`+`tests/application`+`tests/architecture`+`tests/mdm`):
1713 passed, 4 skipped, 35 subtests passed, one pre-existing unrelated
`AWS_PROFILE`-dependent `test_go_live_wizard.py` failure (same one noted
on tickets 75/76/81).

**Cost sanity check (not yet the real prod number)**: a local synthetic
6.8M-row, 4-column DuckDB table (matching `sec_thirteenf_holding`'s real
prod scale per ticket 07's profiling) fingerprints in ~0.48s. That's
per-call; the check runs twice per publish attempt (once at hydration,
once at publish) -- call it ~1s total for the single largest protected
table, against the 60.65s no-op cost it replaces. Test plan item 4 (the
actual live `gold-refresh` measurement against real prod data) is
**not yet run** -- deliberately deferred per advisor's explicit caution
not to deploy/measure while a `daily-incremental` execution was
mid-flight publishing the same canonical silver file (contention risk on
promotion). That execution has since reached a terminal state (FAILED,
OOM in `reduce-identity-refresh` -- see
[ticket 83](83-reduce-identity-refresh-oom-on-merge.md), unrelated to
this fix), so the contention window has passed, but the live measurement
itself still needs a fresh deploy + `gold-refresh` execution, not yet
triggered.
