# Fix canonical silver.duckdb hydration memory usage (streaming fix + seed-universe narrow read path)

Label: `wayfinder:map`

## Destination

Two implementation-ready specs, pursued in parallel (widened from this map's
original narrow `seed-universe`-only scope -- see ticket 02/03):

1. **Shared streaming-buffer fix**: replace
   `_hydrate_silver_database_from_storage`'s non-streaming
   `read_bytes()`/`write_bytes()` full-object buffering with a streaming
   download, so peak memory for the hydrate step is a small constant instead
   of O(canonical file size) -- benefiting every command that hydrates
   canonical (`Stage0CompanyIdentity`, `ComputeWindows`, `gold-refresh`,
   `seed-universe`, and any future one), not just `seed-universe`. Reaching
   the end means: the streaming mechanism is chosen, the symmetric
   write/publish-side buffering (`write_bytes`'s remote branch, the
   checksum-then-atomic-put path) is either included or explicitly deferred
   with a reason, and the fix is verified not to change
   `merge_candidate_into_canonical`/protected-table-conflict semantics.
2. **`seed-universe` narrow read path**: `seed-universe` stops needing a
   full local copy of canonical at all for its read-only
   `get_active_ciks`-shaped work, via DuckDB `httpfs` remote `ATTACH
   (READ_ONLY)` (ticket 01, confirmed feasible). Reaching the end means the
   exact read mechanism is locked, and it's verified compatible with
   `sec_company_sync_state`'s existing protected-table conflict machinery.
   The **write** side (`upsert_company_sync_state` for newly-discovered
   CIKs) is confirmed infeasible over remote `ATTACH` at any DuckDB version
   (ticket 01) and keeps going through the full hydrate/merge/publish flow
   -- benefiting from fix #1 above, not replaced by fix #2.

Both fixes reduce or eliminate `seed-universe`'s dependence on the
`wh_large_arn` task profile (PR #391's same-day stopgap); reaching the end
of this map means deciding, for `seed-universe` specifically, whether it can
move back to a smaller profile once both are in place -- with zero change
required to any of `sec_company_sync_state`'s other ~10 call sites across
`warehouse_orchestrator.py`, MDM (`coverage.py`/`pipeline.py`/`cli.py`),
`silver_support/sharded_reader.py`, `application/commands/migrate_silver_shards.py`,
and `scripts/build_relationship_release_manifest.py`.

## Notes

- Live incident context: task #35's full-universe `load_history` run OOM'd
  twice in one session (2026-08-09) -- first on `acquire-sec-fetch-lease`
  (fixed in PR #390 by isolating the fully-self-contained `pipeline_run_lease`
  table into its own tiny store), then on `seed-universe` (mitigated same-day
  in PR #391 by moving it to `wh_large_arn`, 8192MB). This map is the
  root-cause follow-up to the second fix, informed by the first.
- **Why not repeat PR #390's exact pattern (repoint storage_root/silver_root
  at an isolated small file)?** `pipeline_run_lease` had zero other readers
  -- an isolated empty store was safe to introduce unilaterally.
  `sec_company_sync_state` does not: it's read/written by ~10 call sites
  across warehouse orchestration, MDM, sharding, and manifest-building.
  Isolating the table itself would mean repointing all of them -- a real
  migration, not a same-shaped fix. Explicitly ruled out (see Out of scope).
- **Chosen approach:** keep `sec_company_sync_state` inside canonical
  `silver.duckdb` as the single source of truth (no duplication, no other
  consumer changes) -- give `seed-universe` specifically a way to read and
  write just that one table without a full local hydrate of the other ~30
  tables. Candidate mechanism: DuckDB's `httpfs`/remote-attach extension
  against the canonical S3 object, feasibility not yet confirmed.
- Before implementation, use `/gof-refactor-reviewer` per this repo's
  standing convention (CLAUDE.md), plus the existing test/code-review gates.
  (`/gof-pattern-selector`, referenced when this map was opened, is not an
  available skill in this environment -- `/gof-refactor-reviewer` is the
  closest fit.)
- PR #391 (the `wh_large_arn` memory bump) ships and stays live regardless
  of this map's pace -- it's the safety net `load_history` needs right now.
  This map's outcome is a follow-up that later reverts `seed-universe` off
  `large`, not a blocker on task #35 proceeding.

## Decisions so far

- [Fix the publish/merge-side non-streaming buffer this map
  deferred](issues/06-publish-merge-side-streaming-fix.md) — the risk this
  map's own close-out flagged as unresolved ("real but shrinking headroom
  as canonical grows") materialized live 2026-08-22: `seed-universe`
  OOM'd again on the exact deferred boundary (canonical re-download,
  merged-file read, `promote_staged`'s internal re-read) even after an
  unrelated table-scoping fix to the merge step itself made the merge
  logic provably correct. `/gof-refactor-reviewer` adjudicated two designs
  and rejected parallel bytes/file sibling functions (the shape that
  already caused one silent regression of this exact fix, `37c3171f` →
  `dc9e6925`) in favor of widening `write_staged_bytes`/`promote_staged`/
  `stage_and_promote` to accept `bytes | Path` via `isinstance` dispatch —
  one implementation per operation, not two to keep in sync. Design
  decided, not yet implemented.
- [Move seed-universe back to a smaller task profile now that both fixes are
  live](../task-profile-consolidation/issues/07-decide-whether-to-revert-load-historys-seeduniverse-off-large.md)
  — this map's own stated destination question, closed by
  task-profile-consolidation wayfinder map tickets 06 and 07 (2026-08-20),
  not by a ticket of this map (this map's own "Frontier: None" close never
  actually recorded the answer — see task-profile-consolidation ticket 07's
  own text for that gap). Both fixes below (streaming hydrate PR #392,
  MDM-as-novelty-source PR #394) are confirmed live in prod and apply
  identically to every `seed-universe` invocation regardless of caller.
  **Answer: yes, moved back to medium, both call sites.** The standalone
  `seed_universe` workflow (`command_task_profile('seed-universe')`) was
  moved first (ticket 06); `load_history`'s own `SeedUniverse` state,
  hardcoded to `wh_large_arn` since the original PR #391 emergency bump, was
  converged onto the same `medium` answer immediately after (ticket 07) —
  both call the identical `seed-universe --run-id <execution>` command with
  identical arguments against the same shared canonical file, and no
  `load_history`-specific factor was found to justify a divergence. One
  risk remains open, not closed by this decision: the merge/publish step's
  own full-buffer read/write (this map's ticket 04 deliberately deferred
  it) — checked live 2026-08-20 at 1.5GiB canonical, comfortably inside
  medium's 4096MB, with real but shrinking headroom as canonical grows.
- [Route seed-universe's novelty detection through MDM, not
  silver](issues/05-mdm-as-system-of-record-for-novelty-detection.md) --
  MDM is the system of record for company information (user correction),
  even though mechanically downstream of silver. `seed-universe`'s "is this
  CIK already tracked" check moves from a silver point-lookup to a query
  against `mdm_company.cik` (indexed Postgres, no duckdb touch at all for
  already-known CIKs). Requires a new `INSERT ... ON CONFLICT (cik) DO
  NOTHING` seed-only write (distinct from `upsert_company_sync_state`'s
  existing unconditional-overwrite semantics, unchanged for its other
  callers) so MDM's inherent one-cycle staleness can never clobber an
  existing CIK's `tracking_status`. This supersedes both the `httpfs`
  narrow-read direction (ticket 01, rejected by user) and the small
  company-metadata-cluster duckdb-split direction explored earlier in this
  same ticket -- neither is needed. Design-complete, not yet implemented.
- [Design the streaming download fix for
  _hydrate_silver_database_from_storage](issues/04-design-streaming-hydrate-fix.md)
  -- implemented and merged into the working tree: new
  `StorageLocation.download_file()` (mirrors `upload_file`'s existing
  streaming pattern in reverse), `_hydrate_silver_database_from_storage` and
  `_hydrate_shard_for_window` both switched to it. Full test suite green
  (1138 passed). Publish/merge-side buffering (points #2/#3 from ticket 02)
  deliberately deferred, not part of this fix. Not yet committed/deployed.
- [Non-streaming read_bytes/write_bytes buffering as the shared root
  cause](issues/02-non-streaming-hydrate-buffer-shared-root-cause.md) --
  `_hydrate_silver_database_from_storage`'s download step
  (`object_storage.py`'s `read_bytes()`) buffers the entire canonical
  `silver.duckdb` into one Python `bytes` value before writing it to local
  disk, unconditionally, for every hydrate-consuming command -- not just
  `seed-universe`. This is the actual shared root cause behind all four
  `wh_large_arn` bumps this go-live (Stage0CompanyIdentity, ComputeWindows,
  gold-refresh, seed-universe); those bumps raised the ceiling but didn't
  fix the O(2x file size) pattern, which will recur as canonical keeps
  growing.
- [Scope: widen destination to the shared streaming-buffer fix, pursue both
  fixes in parallel](issues/03-scope-widen-and-pursue-both-fixes-in-parallel.md)
  -- user decision: widen this map's destination beyond `seed-universe`
  alone to include the general streaming-buffer fix, and pursue it alongside
  the `httpfs` narrow-read mechanism rather than sequencing one before the
  other.
- [DuckDB httpfs partial read/write feasibility against the canonical
  silver.duckdb](issues/01-duckdb-httpfs-partial-read-write-feasibility.md) --
  partially feasible: remote `ATTACH ... (READ_ONLY)` genuinely reads only
  `sec_company_sync_state`'s own blocks (not the 1.5GB file), confirmed via
  DuckDB docs and `single_file_block_manager.cpp` source, no version gap at
  the pinned `duckdb==1.5.2`. Write is categorically infeasible over
  HTTPS/S3 at any DuckDB version ("writing the database via the HTTPS
  protocol or the S3 API is not possible" -- DuckDB's own docs) --
  architectural (block-based local-random-access format vs. S3's
  whole-object-PUT model), not a missing feature. The write path must keep
  the existing full-hydrate -> merge -> full-file upload -> version-checked
  promote flow, unless `sec_company_sync_state` is later split into its own
  small attached file (a real, DuckDB-native option, but a separate
  structural decision, not resolved by this ticket).

## Not yet specified

- Whether `sec_company_sync_state`'s existing protected-table conflict
  detection (authority_column, `PROTECTED_TABLE_REGISTRY` policy -- the same
  machinery `pipeline_run_lease` participates in) still correctly guards
  against a concurrent writer (e.g. `bootstrap-next` or `compute-windows`
  racing a `seed-universe` narrow write) once any narrow path bypasses the
  normal full-hydrate-open-merge flow. Depends on ticket 05's design
  landing on a concrete read mechanism first.
- The `sec_company_sync_state` table-split option ticket 01 surfaced as a
  real DuckDB-native possibility for unblocking the *write* side too (attach
  it as its own small file alongside canonical `silver.duckdb`) -- distinct
  from Option A (full table isolation, ruled out for blast radius) because
  it's scoped to `seed-universe`'s two operations specifically. Whether
  this is worth pursuing depends on how much headroom ticket 04's streaming
  fix alone buys back -- if that's sufficient, the table-split option may
  not be needed at all.

## Frontier (open tickets)

None design-side. Ticket 04 (streaming hydrate fix), ticket 05 (MDM as
novelty-detection source of record), and ticket 06 (publish/merge-side
streaming fix, opened 2026-08-22 once its previously-flagged risk
materialized live) are all design-complete/decided. **Ticket 06 is now implemented** (TDD steps 1-5, full repo suite green) but
**not yet committed, deployed, or empirically re-verified against the live
OOM** (step 6). Not reopening this as a full wayfinder frontier ticket (the
decision is made, only the commit/deploy/verify tail remains) — track via
ticket 06's own Status field instead.

## Out of scope

- Full isolation of `sec_company_sync_state` into its own file (repointing
  all ~10 other call sites) -- explored via ticket 05's discussion (DuckDB's
  native multi-attach makes the blast-radius concern smaller than
  originally assessed), but superseded once MDM's system-of-record status
  eliminated the need for `seed-universe` to touch silver's read side at
  all. Revisit only if MDM's design (ticket 05) is later found infeasible.
- `httpfs` remote `ATTACH (READ_ONLY)` narrow-read (ticket 01's mechanism)
  -- explicitly rejected by the user in ticket 05's discussion ("not
  interested in adding httpfs"), superseded by the MDM-based design.
- A general narrow-hydrate mechanism for other commands with the same shape
  (e.g. CIK-scoped work in `bootstrap-next`) -- explicitly deferred to a
  future effort once this map banks a second proven instance of the pattern
  (after PR #390's lease fix).
