# Company Identity Hydrate Elimination

## Destination

A locked decision on how `Stage0CompanyIdentity`'s windowed
`bootstrap-fundamentals --mode company-identity` capture (no explicit
`--cik-list`, only `--cik-offset`/`--cik-limit`) should resolve its CIK
batch and read/write silver data **without** paying two costs it pays on
every window today:

1. **Full-canonical hydrate.** `bootstrap_fundamentals.py`'s
   `if not (mode == "company-identity" and raw_cik_list): _hydrate_silver_
   database_from_storage(context)` branch downloads and opens the *entire*
   canonical `silver.duckdb` (6.8M-row `sec_thirteenf_holding`, 4.7M-row
   `sec_company_filing`, ~1GB+ and growing) before it ever looks at the
   window bounds. This OOM-killed (exit 137) live in prod on 2026-08-05 on
   the `medium` (4096MB) ECS task, for a window of just 500 CIKs.
2. **Full-canonical merge-publish, per window.** `_publish_silver_database_
   if_remote` (called at the end of every window) runs `merge_candidate_
   into_canonical` — the same `shutil.copy2` + per-protected-table
   (~21 tables) merge pattern already reviewed this session for
   pipeline-throughput-architecture ticket 05, there measured at ~188s for
   4 candidates. `load_history`'s live Stage0CompanyIdentity run had 53
   windows — this cost likely repeats 53x, and may dwarf the hydrate cost.

This map decides the target architecture (not just "give it more memory,"
which was already shipped as a stopgap — see Notes) while preserving two
hard constraints: Stage0's fail-closed sequencing invariant (company data
must fully land before Stage1Parallel/ownership/ADV work runs, since
`IS_INSIDER` derivation depends on resolved Company entities) and SEC-fetch
idempotency (must not silently multiply real SEC API calls).

## Notes

- Repo: `edgartools-platform`. This map carries **decisions only** — once
  the architecture ticket resolves, implementation happens in a normal
  (non-wayfinder) session, not inside this map.
- Immediate unblock already shipped and live in prod (PR #359, merged
  2026-08-05): moved `Stage0CompanyIdentity`'s per-window task from
  `medium` (4096MB) to `large` (8192MB) in
  `infra/scripts/deploy-aws-application.sh`. This map is about eliminating
  the underlying waste this stopgap papers over, not re-litigating it —
  the same OOM class will recur on `large` too as canonical keeps growing.
- Key files: `edgar_warehouse/application/commands/bootstrap_fundamentals.py`
  (`execute()`, `_resolve_fundamentals_ciks`, the hydrate branch),
  `edgar_warehouse/application/warehouse_orchestrator.py`
  (`_run_submissions_bronze_then_silver`, `_capture_submission_bronze_
  snapshots`, `_resolve_submissions_main_cached_snapshot` — the SEC-fetch
  cache-skip that needs *some* local DB read access, `_publish_silver_
  database_if_remote`, `compute-windows`'s `cik_snapshot.jsonl` write),
  `edgar_warehouse/application/identity_refresh_publication.py`
  (`persist_batch_outcome`/`reduce_identity_refresh` — the existing
  delta-then-reduce pattern `daily_incremental`'s *bounded* Identity
  Refresh already uses to avoid a full hydrate, by producing a small delta
  artifact instead of merging into canonical per-batch),
  `edgar_warehouse/silver_protection.py` (`merge_candidate_into_canonical`),
  `infra/scripts/deploy-aws-application.sh` (`per_window_company_identity`/
  `stage0_company_identity` in `write_load_history_definition`, and the
  mirrored `per_batch_company_identity`/`stage0_company_identity_bounded`
  in `write_warehouse_mdm_gold_definition`'s `daily_incremental` branch —
  keep in sync per the existing duplication-convention comments in both).
- **Already found, load-bearing:** `compute-windows` (which always runs
  *before* Stage0CompanyIdentity) already writes `cik_snapshot.jsonl` — the
  exact ordered CIK list, same source (`db.get_tracked_ciks(...)`) and
  order the windowed hydrate path re-derives today. A window could slice
  that lightweight S3 text file directly instead of re-deriving via a full
  DB read — but this alone does not resolve the SEC-fetch cache-skip need
  (see next point) or the per-window publish cost.
- **Already found, load-bearing:** `daily_incremental`'s bounded
  `--cik-list` + `--identity-refresh-run-id` path looks like it "skips
  hydrate for free," but it is not simply "no hydrate" — passing
  `identity_refresh_run_id` makes `execute()` skip the normal `_publish_
  silver_database_if_remote` merge-into-canonical step entirely and instead
  call `persist_batch_outcome` to persist an immutable CIK delta, reduced
  into canonical later by a single `reduce_identity_refresh` call. It is a
  genuinely different architecture (delta-then-reduce), not a hydrate flag
  load_history's Stage0CompanyIdentity can just also pass — reusing it here
  would mean restructuring how/when Stage0CompanyIdentity's data actually
  lands in canonical, which interacts directly with Stage0's own
  sequencing invariant (Stage1Parallel currently assumes Stage0 has fully
  published to canonical before it starts).
- **Already found, load-bearing:** the local DB read access the hydrate
  provides is not purely wasted — `_resolve_submissions_main_cached_
  snapshot` (called per-CIK inside `_capture_submission_bronze_snapshots`)
  reads existing bronze/silver state to skip already-fetched SEC
  submissions. A truly empty local DB per window would not be *incorrect*
  (SEC data is additive/immutable, so a redundant fetch just re-writes
  identical rows — see CLAUDE.md's "SEC data idempotency" section) but
  would multiply real SEC API calls, the exact failure class CLAUDE.md's
  "Artifact-throttle 5-whys" and "Daily accession-expansion 5-whys" entries
  already documented and fixed elsewhere. Any fix here must not reintroduce
  that class of regression.

## Decisions so far

<!-- Closed ticket decisions — one-line gist + link; detail lives in the ticket. -->

- [Does daily_incremental's delta-then-reduce pattern generalize to load_history's Stage0CompanyIdentity?](issues/01-delta-reduce-generalization.md) — Generalizes, but not as a drop-in reuse; two required adaptations. (a) Input-shape: `bootstrap_fundamentals.execute()` hard-rejects `--identity-refresh-run-id` without an explicit `--cik-list`; Stage0 would need to emit explicit CIK-list batches instead of offset/limit windowing. (b) Bigger finding: `reduce_identity_refresh`'s merge loop has never been exercised past ~4 candidates in prod and has an un-scaled, previously-undocumented bug — intermediate `merged-{index}.duckdb` files are never deleted between iterations, so local disk grows O(candidate_count × canonical_size); at load_history's ~53-54-candidate scale that's tens-to-100+GB of local disk plus an extrapolated 40-70 min of sequential `shutil.copy2`s in one reducer task. The land-before-Stage1Parallel invariant is preserved (arguably more strictly), but at a real cost: per-window failure isolation is lost — a single failed batch blocks ALL batches' deltas from reaching canonical for that run (unverified whether SFN Distributed Map redrive rescues this). Recommends ticket 03 treat "fix reduce's per-candidate disk accumulation" as a co-requisite of adopting delta-then-reduce, not a separate follow-up.
- [What is Stage0CompanyIdentity's actual per-window cost breakdown, and would a minimal/selective hydrate be enough on its own?](issues/02-per-window-cost-breakdown.md) — No. Selective hydrate fixes the OOM (peak memory) but has zero effect on publish cost: `_publish_silver_database_if_remote` independently re-downloads canonical fresh from S3 and merges into *that* copy, never touching whatever hydrate loaded — the two are architecturally decoupled. `merge_candidate_into_canonical`'s dominant cost is an unconditional full-file `shutil.copy2` of canonical, independent of candidate size. Order-of-magnitude estimate: today's per-window shape costs ~2.1 hours of repeated full-canonical S3 I/O across 53 windows, vs. ~5-10 minutes for a delta-then-reduce restructuring (~15-25x gap, widening as canonical grows). Recommendation for ticket 03: treat selective hydrate and publish restructuring as two separable, both-necessary fixes, not a choice.

## Not yet specified

- Whatever concrete migration/rollout plan is needed once the target
  architecture is chosen (this graduates once ticket 03 resolves).
- The exact fix shape for `reduce_identity_refresh`'s per-candidate disk
  accumulation (reuse one output path vs. delete-after-each-merge) — left
  to the implementing engineer per ticket 03's progress notes, not a
  design decision this map needs to specify further.

## Out of scope

- Re-deciding the `medium` → `large` task-size stopgap (PR #359) — already
  shipped and confirmed live; not reopened here.
- `daily_incremental`'s own Stage0CompanyIdentityBounded correctness or
  performance — only referenced here as prior art for the delta-then-reduce
  pattern, not itself a target of this map.
