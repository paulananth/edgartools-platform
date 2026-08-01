# Root-cause the excessive bounded Daily Identity Refresh runtime

Type: research
Status: resolved
Blocked by: none

## Question

Why does the deployed, company-bounded Daily Identity Refresh still take long
enough to threaten its six-hour production evidence bound, and what exact
runtime contract must change before the schedule can be enabled?

## Triggering evidence

The post-fix production execution
`daily-post-txt-fix-20260801T005633Z` uses the deployed immutable warehouse
image `sha256:72d4e4aa493520dda1c9327250f64388ce2bfed1c575cabfd65cb6efd3633f4d`.
Its company-identity stage is a serialized three-item Distributed Map
(`MaxConcurrency=1`). The earlier 1,133-CIK bounded stage ran for hours, and
the present run must not be allowed to normalize that duration without an
evidence-backed explanation.

## Required investigation

- Capture per-batch CIK counts, task start/stop times, useful work, retry and
  publish timing from the active and preceding bounded executions.
- Compare those facts to the old 26,300-CIK full-universe stage and the
  accepted at-most-six-hour Daily Identity Refresh evidence requirement.
- Apply a documented 5 Whys chain that distinguishes an intentional
  serialization safety boundary from avoidable per-batch work or latency.
- Decide whether the next change is batch sizing, bounded concurrency with a
  publication-safe boundary, narrower identity work, caching/reference reuse,
  or another explicitly evidenced cause. Do not implement in this ticket.

## Done when

An evidence-backed root cause and a concrete follow-up decision are recorded;
the schedule gate explicitly remains failed until a new immutable-image daily
execution completes the whole chain within six hours.

## Answer (2026-07-31)

The CIK-universe boundary is working; the remaining latency is a **publication
unit-of-work problem**, not SEC network latency and not a reason to broaden or
further narrow the company universe.

### Live evidence

The first 500-CIK child of the immutable-image production execution
`daily-post-txt-fix-20260801T005633Z` ran from 21:14:19 to 21:56:44 EDT:

- `bootstrap-fundamentals --mode company-identity` reported **2,483.53 s**
  (41m24s) total.
- The two global SEC reference calls completed in **90 ms** and **125 ms**.
  They are not the latency source, although repeating their reference-data
  write in each batch is unnecessary work.
- Bronze/submission capture and local `silver_apply_completed` completed by
  21:23:31 EDT; the local apply itself took **52.51 s**.
- The same child did not finish `silver_database_uploaded` until 21:56:16,
  after producing a **1,071,394,816-byte** canonical DuckDB artifact. That
  final merge/stage/promote dominates the batch at about **32m45s**.
- It recorded zero submission network fetches and 914 catalog silver skips;
  the slow path is therefore not a per-CIK SEC fetch storm.
- `Stage0CompanyIdentityBounded` intentionally has `MaxConcurrency=1`, so its
  three batches serialize. At the observed first-batch rate, Stage 0 alone has
  an approximately two-hour floor before `RunWarehouseTask` and the remaining
  downstream chain begin.

### 5 Whys

1. **Why can the bounded daily run still take hours?** Three 500-CIK company
   identity batches run serially, and one measured batch consumes 41m24s.
2. **Why does one small batch consume 41m24s?** Each batch runs the generic
   `bootstrap-fundamentals` command and treats the result as a complete remote
   silver publication unit, not merely a CIK-scoped identity delta.
3. **Why is that publication expensive?** The command merges the candidate
   into the canonical `silver.duckdb`, stages, and promotes a full 1.07 GB
   database artifact. The measured publish segment is ~32m45s, versus 52.51 s
   for local silver application.
4. **Why are those publications serialized?** Concurrent writers to the same
   canonical DuckDB artifact can lose a publish; the state machine deliberately
   enforces `MaxConcurrency=1` to preserve the existing ETag-guarded
   merge/promotion safety boundary.
5. **Why does the daily path pay that cost once per batch?** The bounded daily
   map reused the generic per-batch `bootstrap-fundamentals`/canonical-publish
   shape. It changed CIK selection but did not introduce a run-scoped,
   publication-safe aggregation boundary for company-identity deltas.

**Root cause:** repeated whole-canonical DuckDB merge/upload under an
intentional single-writer constraint. SEC fetch latency is ruled out by the
measured 215 ms reference calls and zero submission network fetches.

## Decision and follow-up

Do not enable the recurring schedule or call the at-most-six-hour daily gate
passed. The next decision is [Decide a run-scoped publication boundary for
Daily Identity Refresh](58-decide-run-scoped-daily-identity-publication.md):
establish how batches can accumulate identity deltas and publish once while
retaining strict failure behavior, canonical integrity, and recovery evidence.
That decision must also determine whether a once-per-run reference refresh is
carried with the aggregate rather than repeated in every batch.
