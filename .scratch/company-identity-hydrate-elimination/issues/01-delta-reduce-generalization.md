# Does daily_incremental's delta-then-reduce Identity Refresh pattern generalize to load_history's Stage0CompanyIdentity?

Type: research
Status: resolved

## Question

`daily_incremental`'s bounded Identity Refresh (`--cik-list` +
`--identity-refresh-run-id`) avoids `load_history`'s Stage0CompanyIdentity
problem (full-canonical hydrate + full-canonical merge-publish per window)
by using a different architecture entirely: each batch calls
`persist_batch_outcome` (`edgar_warehouse/application/identity_refresh_
publication.py`) to write an immutable CIK-scoped delta artifact instead of
merging into canonical directly, and a single later `reduce_identity_
refresh` call folds all deltas into canonical once.

Investigate, reading the actual code (not just the docstrings/comments):

1. Trace `persist_batch_outcome` and `reduce_identity_refresh` end to end.
   What does a delta artifact actually contain? What does the reduce step
   actually do to merge deltas into canonical — is it the same `merge_
   candidate_into_canonical` cost, just paid once instead of N times, or
   something cheaper?
2. What does `reduce_identity_refresh` require to have already happened
   before it runs (e.g. does it need ALL batches to have completed first,
   like a barrier)? How is that barrier currently implemented/orchestrated
   for `daily_incremental`?
3. `load_history`'s Stage0CompanyIdentity has a hard sequencing invariant:
   Stage1Parallel (ownership/ADV work) must not start until company data
   has actually landed in canonical, because `IS_INSIDER` derivation skips
   unresolved issuers. If Stage0CompanyIdentity switched to delta-then-
   reduce, would inserting a single reduce step between all windows
   completing and Stage1Parallel starting preserve that invariant exactly,
   or does something about the current per-window-publish shape provide a
   guarantee delta-then-reduce would lose (e.g. per-window failure
   isolation, partial progress visibility)?
4. Are there any other differences between load_history's Stage0
   (`ToleratedFailurePercentage=0`, strict, no Catch-and-proceed) and
   daily_incremental's bounded Identity Refresh that would make reusing
   this pattern unsafe or need adaptation — e.g. does `persist_batch_
   outcome`/`reduce_identity_refresh` have any built-in tolerance for
   partial/missing batches that would conflict with Stage0's strictness?
5. Does `reduce_identity_refresh` itself carry a `merge_candidate_into_
   canonical`-shaped cost that would scale with load_history's 53-window
   scale the same way (i.e. does batching 53 windows' worth of company
   data into ONE reduce still touch all ~21 protected tables once, or does
   the delta's small size make the per-protected-table walk itself cheaper
   than what Stage0 pays today)?

Report a clear verdict: does this pattern generalize to load_history's
Stage0CompanyIdentity, with what adaptation if any, or does it not fit and
why not.

## Answer

**Verdict: it generalizes, but not as a drop-in reuse.** The pattern's real
win — eliminating N separate network hydrate-downloads and N full-canonical
network re-uploads — is genuine and would carry over cleanly to
`load_history`. But two things currently block a straight copy: (a)
`bootstrap_fundamentals.py`'s own input-validation hard-rejects the exact
shape Stage0 uses today (offset/limit windowing with no `--cik-list`), so
adopting the pattern requires Stage0 to switch to explicit CIK-list batches,
not just pass a new flag; and (b) `reduce_identity_refresh`'s merge loop has
an un-scaled, previously-unexercised local-disk cost (detailed in Q5) that
has only ever run against ≤4 candidates in production — scaling it to
`load_history`'s 53-window universe without addressing that cost risks
trading one resource failure mode (network-bound OOM/timeout, the current
symptom) for another (local ephemeral-disk exhaustion inside the reducer
task). Recommend ticket 03 treat "fix reduce_identity_refresh's per-candidate
disk accumulation" as a co-requisite of adopting delta-then-reduce for
Stage0, not a separate follow-up.

### Q1 — What does a delta contain, and is the reduce cost "paid once" or something cheaper?

Neither, exactly — it's the same per-call cost, paid the same number of
times, just relocated and reshaped.

- **Delta contents:** `persist_batch_outcome` (`identity_refresh_publication.py:129-156`)
  uploads the batch task's entire local `silver.duckdb`
  (`context.silver_root.join("silver","sec","silver.duckdb")`, referenced at
  `bootstrap_fundamentals.py:315`) as an immutable `delta.duckdb` object, plus
  a small JSON outcome envelope (`batch_id`/`ciks`/`status`/`sha256`). This
  "whole local DB" is small in practice: `bootstrap_fundamentals.execute()`
  skips `_hydrate_silver_database_from_storage` exactly when
  `mode == "company-identity" and raw_cik_list` (`bootstrap_fundamentals.py:133`),
  and `open_silver_database`/`SilverDatabase.__init__` creates a fresh,
  schema-only local file when none exists (`edgar_warehouse/silver_support/
  session.py:12-16`) — so the uploaded delta is just DDL plus whatever rows
  this batch's CIK list wrote to `sec_company`/`sec_company_filing`/
  `sec_company_address`/`sec_company_former_name`, not a full-canonical-sized
  file. Reference data (`sec_company_ticker` etc.) is **not** in the delta:
  `_sync_reference_data` is explicitly gated on `if not identity_refresh_
  run_id:` (`bootstrap_fundamentals.py:253`), so an identity-refresh batch
  skips it entirely — reference data reaches canonical only via the separate
  `reference` candidate `compute-identity-refresh-window` produces (see
  below), never via a per-batch delta.
- **`reduce_identity_refresh` is NOT "merge once instead of N times."** It
  calls `merge_candidate_into_canonical` once *per candidate* in a loop
  (`identity_refresh_publication.py:266-289`), where `candidates` is the
  global reference snapshot plus every batch delta
  (`identity_refresh_publication.py:247` or `:255`), chaining
  `current = merged` between iterations (line 279). Every one of those N+1
  calls still pays `merge_candidate_into_canonical`'s
  `shutil.copy2(canonical_path, output_path)` (`silver_protection.py:595`),
  and because `canonical_path` there is `current` — already canonical-sized
  after the first merge — that copy2 is O(canonical size), repeated N+1
  times. The genuinely cheap part is the *per-table walk* inside each call:
  it skips any protected table the delta doesn't touch
  (`silver_protection.py:636`, `if table_name not in cand_tables: continue`),
  and for tables it does touch, the delta-row query and canonical lookup are
  both scoped to the delta's own keys, not a full-table scan
  (`silver_protection.py:449-514`) — that part scales with delta size.
  `shutil.copy2` does not; it scales with canonical size, unconditionally,
  on every one of the N+1 iterations.
- **The "reference" candidate is itself full-canonical-sized.**
  `compute-identity-refresh-window` runs through the general orchestrator
  path (not `bootstrap-fundamentals`), whose sole
  `_hydrate_silver_database_from_storage` call site
  (`warehouse_orchestrator.py:472-475`) always fires for it — so
  `persist_run_manifest`'s `reference_snapshot_file`
  (`warehouse_orchestrator.py:660-668`, captured right after that command's
  own full hydrate + `_sync_reference_data`) is the fully-hydrated canonical
  DB at run start. Reduce's *first* merge (`reference` → freshly-downloaded
  canonical) therefore pays close to the same cost as today's existing
  per-window merge, once, before any of the genuinely cheap small-delta
  merges run.
- **What actually changes:** network I/O shape, not merge-call count. Today,
  each of Stage0's N windows separately pays a network hydrate-download
  *and* a network merge-publish-upload. Under delta-then-reduce, batches pay
  no hydrate at all and upload only their small delta; the reducer pays
  exactly one network canonical download (`identity_refresh_publication.py:237,
  243-244`) and one network upload/promote at the end
  (`identity_refresh_publication.py:299-302`), with the N+1 `shutil.copy2`
  merge passes happening locally, on ephemeral disk, inside one task — see
  Q5 for why that local cost is not itself free at scale.

### Q2 — What barrier does `reduce_identity_refresh` require, and how is it wired for `daily_incremental`?

Two independent barriers, stacked:

1. **SFN-native Map barrier.** `stage0_company_identity_bounded`'s Map
   (`infra/scripts/deploy-aws-application.sh:3247-3276`) has
   `"Next": "ReduceIdentityRefresh"` (line 3274) with
   `"ToleratedFailurePercentage": 0` (line 3251). A Step Functions Map state
   only transitions to `Next` after every item completes (subject to the
   tolerance threshold); at 0% tolerance, any single failed batch blocks the
   transition entirely. This is a platform-native mechanism, not custom
   code in this repo.
2. **Code-level manifest-completeness barrier.** Independent of the SFN
   barrier, `reduce_identity_refresh` calls `load_complete_run_manifest`
   (`identity_refresh_publication.py:159-183`), which calls
   `validate_complete_run_manifest` (`identity_refresh_publication.py:349-393`).
   That function re-reads the batch list `persist_run_manifest` originally
   declared and requires *every* declared batch to have a matching outcome
   object with `status == "succeeded"` (`identity_refresh_publication.py:380-381`),
   a matching batch/CIK identity (`:384-387`), and a valid checksum
   (`:388-389`) — raising `WarehouseRuntimeError` otherwise. So even if the
   SFN-level barrier were somehow bypassed, the reducer independently
   refuses to touch canonical on an incomplete run.

Both barriers are exactly how `daily_incremental` already orchestrates this
— no additional "wait for all batches" machinery exists beyond the Map's own
semantics plus this manifest check.

### Q3 — Does a single reduce step preserve Stage0's land-before-Stage1Parallel invariant?

**Yes, and arguably more strictly** — but at a real cost to partial-progress
visibility.

Preserved: reduce only durably promotes canonical via one atomic
`storage_root.promote_staged` call with an optimistic-concurrency
`expected_etag` check (`identity_refresh_publication.py:299-302`); the
manifest is only marked `"succeeded"` after that promotion
(`identity_refresh_publication.py:328-343`). If `Stage1Parallel`'s `Next`
were wired to follow `ReduceIdentityRefresh` the same way it follows
today's Map, ownership/ADV work still cannot start until company data is
verifiably promoted into canonical — the invariant holds exactly.

Lost: **per-window failure isolation / partial-progress durability inside
canonical.** Today, each of Stage0's N windows calls
`_publish_silver_database_if_remote` individually
(`bootstrap_fundamentals.py:328-352`, gated on `not identity_refresh_run_id`)
— a successfully-completed window's company data lands in canonical
immediately, regardless of whether a *later* window in the same run
eventually fails. If window 40 of 53 permanently exhausts its retries today,
canonical already durably has windows 1–39's data (the overall run still
fails per `ToleratedFailurePercentage=0`, but that prior work is not lost).
Under delta-then-reduce, `validate_complete_run_manifest` requires *all* 53
declared batches to show `status == "succeeded"` before *any* of them can be
merged (`identity_refresh_publication.py:380-381`) — so if batch 40
permanently fails, none of the other 52 successful batches' deltas reach
canonical for that run_id, even though they already exist as durable,
checksummed, immutable S3 objects.

Whether that run is genuinely unrecoverable is a real open question I did
not find settled in code: each batch's delta is durable and
content-addressed, and the manifest check is idempotent to *when* a batch
succeeds, so AWS Step Functions Distributed Map's platform-level "redrive"
capability (re-executing only failed child items of a Map Run, not the
already-succeeded ones) looks architecturally compatible with this shape —
but nothing in this repo exercises or tests that, so treat it as plausible,
not verified.

### Q4 — Other differences that would make reuse unsafe or need adaptation?

**Strictness itself is not the blocker — it's already identical.** Both
Maps use `MaxConcurrency: 1` and `ToleratedFailurePercentage: 0`
(`deploy-aws-application.sh:2246-2247` vs. `:3250-3251`), and both per-item
ECS states get the same default Step Functions Retry envelope
(`MaxAttempts: 3`, `BackoffRate: 2.0` — `ecs_state()`'s default at
`deploy-aws-application.sh:2780-2781`, used unmodified by both
`per_window_company_identity` and `per_batch_company_identity`).
`ReduceIdentityRefresh`'s own SFN-level Retry is deliberately capped to
`MaxAttempts: 1` (`deploy-aws-application.sh:3243-3244`) because
`reduce_identity_refresh()`'s `max_attempts=3` CLI argument already performs
a bounded, promotion-conflict-only retry internally
(`identity_refresh_publication.py:213,233,316-327`) — so there's no
retry-envelope mismatch to reconcile.

**The actual blocker is input shape.** `bootstrap_fundamentals.execute()`
explicitly rejects the combination Stage0 uses today:
`identity_refresh_run_id and (mode != "company-identity" or not raw_cik_list)`
fails with exit code 2 (`bootstrap_fundamentals.py:83-85`) —
`--identity-refresh-run-id` requires an *explicit* `--cik-list`, and Stage0's
current `per_window_company_identity` only ever passes
`--cik-offset`/`--cik-limit` (`deploy-aws-application.sh:2240`). Reuse is
not a flag flip; it requires Stage0 to emit explicit CIK-list batches (the
same shape `compute-identity-refresh-window` already produces via
`_identity_refresh_batches`, `warehouse_orchestrator.py:2617-2620`) instead
of relying on offset/limit windowing over `compute-windows`'s
`cik_windows.jsonl`.

**A second, load-bearing difference, already flagged in this workstream's
own `map.md` and confirmed here by code:** the full hydrate isn't purely
wasted today. `_resolve_submissions_main_cached_snapshot`
(`warehouse_orchestrator.py:4871-4911`) uses the local hydrated DB as its
first idempotency check (`_read_bronze_if_cached`) before falling back to a
remote-bronze glob check (`_read_bronze_by_glob_if_present`, no local DB
needed — `warehouse_orchestrator.py:4905-4911`) to avoid a redundant SEC
submissions.json fetch. Skipping hydrate (as delta-then-reduce requires)
does **not** reintroduce the SEC-fetch-multiplication class of regression
CLAUDE.md already documents (the glob fallback exists precisely to prevent
that) — but it does trade "local DB read" for "one S3 list call per CIK,"
every batch, for every CIK. `daily_incremental`'s bounded refresh only ever
exercises this at ~1,194-CIK scale (the daily-index-impacted intersection,
per CLAUDE.md's ticket-73 entry); `load_history`'s Stage0 would exercise it
across the *entire* tracked universe on every run — 53 windows × 500
CIKs/window (both the `compute-identity-refresh-window` `--batch-size`
default, `cli.py:958`, and Stage0's existing window size) implies roughly
~26,500 CIKs, a figure I derived from those two defaults rather than
measured directly against a live tracked-CIK count. Whatever the exact
count, it is an order of magnitude larger S3-call volume than this pattern
has actually been proven out at. Not a correctness blocker, but a real,
previously-unquantified cost this generalization would introduce.

### Q5 — Does reduce's own cost scale with load_history's 53-window scale the same way?

**Yes — and this is the single most important finding for ticket 03.**
`reduce_identity_refresh`'s per-table walk is cheap and delta-scoped (Q1),
but its `shutil.copy2` cost is a full canonical-sized copy *per candidate*,
not per protected table, and not reduced by delta size. At `load_history`
scale (53 batches, using the same 500-CIK `--batch-size` default
`compute-identity-refresh-window` already uses, `cli.py:958`, which matches
Stage0's existing 500-CIK window size), reduce would perform 53–54
sequential `shutil.copy2`s of the canonical file (~1GB+ and growing per
`map.md`).

**Worse, and not previously documented anywhere in this codebase's
comments:** none of the intermediate `merged-{index}.duckdb` files are
deleted between iterations. `current = merged`
(`identity_refresh_publication.py:279`) only reassigns the Python variable
— the prior file stays on disk inside the same
`tempfile.TemporaryDirectory` (line 239) for the entire reducer attempt.
Local ephemeral-disk usage inside the reducer task therefore grows as
**O(candidate_count × canonical_size)**, not O(canonical_size). For 53+
candidates against a multi-GB canonical, that's tens to 100+ GB of local
disk coexisting simultaneously in one ECS/Fargate task before the attempt
completes — a materially different resource profile than what this pattern
has actually been measured against. `map.md`'s cited figure (~188s for 4
candidates, from pipeline-throughput-architecture ticket 05) and
release-readiness ticket 83's fix (which addressed an *in-memory* OOM from
holding every candidate's bytes in a dict — see
`identity_refresh_publication.py:201-211`'s docstring) both predate and do
not address this on-disk accumulation, because it has never been exercised
past ~4 candidates in production.

**Wall clock is a second, independent scaling axis ticket 03 needs, not just
disk.** Naively extrapolating map.md's ~188s/4-candidate figure linearly to
54 candidates (reference + 53 batches) gives roughly 40–70 minutes of purely
sequential local copy+merge inside one reducer task attempt — before
accounting for canonical having grown since that measurement, and before any
promotion-conflict retry (`max_attempts=3`, each retry re-running the whole
merge loop from a freshly re-read baseline canonical,
`identity_refresh_publication.py:233-327`). Disk may not even be the binding
constraint first; both belong in ticket 03's evaluation, and only disk is
named as a scaling limit above.

One part of the cost shape does *not* scale with candidate count and is
worth ruling out explicitly so ticket 03 doesn't re-derive it:
`payload = current.read_bytes()` (`identity_refresh_publication.py:290`),
read once after the merge loop exits, followed by `write_staged_bytes`,
holds exactly one full canonical-sized buffer in memory — not one per
candidate. This is the same shape release-readiness ticket 83 already fixed
(candidate/reference *inputs* are streamed to local files via
`_read_verified_to_path`, not held as bytes — `identity_refresh_
publication.py:220-230`); only this single final read remains, and it is
O(canonical size), not O(candidates × canonical size).

## Not yet specified

- The concrete fix shape for reduce's O(candidate_count × canonical_size)
  disk growth (e.g. reuse a single output file across candidates instead of
  allocating `merged-{index}.duckdb` per candidate, or delete the prior
  `current` file immediately after each merge completes) is a design
  decision for ticket 03, not answered here — this ticket only establishes
  that the cost exists and has not been exercised at load_history's scale.
- Whether AWS Step Functions Distributed Map redrive genuinely provides
  batch-level resumability for a failed Stage0 run under delta-then-reduce
  (Q3) is plausible from the manifest's design but not verified against any
  actual redrive in this repo.

## Done when

Done — all five questions answered from direct code reading with file:line
citations, and a clear verdict given: the pattern generalizes with two
required adaptations (explicit CIK-list batching, and a fix to reduce's
per-candidate disk accumulation before it is safe at 53-window scale), not
as a drop-in reuse.
