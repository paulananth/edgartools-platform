Type: task
Status: in_progress

## Question

Implement [pipeline-throughput-architecture ticket 03](../../pipeline-throughput-architecture/issues/03-decide-intra-task-concurrency-model.md)'s
decision: add `ThreadPoolExecutor`-based concurrency to the artifact-fetch
loop in `bronze_filing_artifacts.py`'s `fetch_filing_artifacts`.

## Decision already made (ticket 03)

- **Scope**: the artifact-fetch loop only (not submissions bronze-capture
  -- that's ticket 78).
- **Primitive**: `concurrent.futures.ThreadPoolExecutor`, not asyncio.
  Blocking I/O work (`sec_client.py` is synchronous `httpx.Client`); zero
  existing asyncio precedent in this codebase.
- **DB writes stay serialized on the main thread** -- a single
  `SilverDatabase` DuckDB connection isn't safe for concurrent writes.
  Thread pool covers only the SEC fetch + content download; results are
  collected and `db.merge_filing_attachments`/raw-object writes happen
  sequentially back on the main thread.
- **Worker bound: 5** -- matches the existing `BOOTSTRAP_BATCH_CONCURRENCY`
  "2-5 recommended range" convention. `pyrate_limiter`'s `Limiter` is
  confirmed thread-safe (internal `RLock`, source-verified) so it remains
  the real throughput ceiling regardless of pool size.
- **Known implementation nuance**: the existing circuit breaker
  (`consecutive_errors >= _CONSECUTIVE_ERROR_LIMIT`) assumes strictly
  sequential completion order to define "consecutive." Under concurrent
  fetching, completions arrive out of submission order -- redefine as
  errors within the last N *completions*, not the last N *submissions*.

## Test plan (from ticket 03, real-data-backed per this workstream's
established discipline -- tickets 67-72)

1. **Correctness equivalence** -- N fake accessions through the concurrent
   path vs. the sequential path, assert identical final `SilverDatabase`
   state.
2. **Rate-limiter compliance** -- real `Limiter` at a deliberately low test
   rate, assert wall-clock throttling holds regardless of pool size.
3. **DB-write serialization** -- thread-id-recording test double on
   `SilverDatabase`, assert 100% of writes happen on the main thread.
4. **Partial-failure equivalence** -- inject a failure (e.g. an
   immutable-content conflict, matching
   [ticket 74](74-daily-incremental-permanent-terminal-repair-block.md)'s
   real scenario) among several concurrent accessions, assert error
   counting and `terminal_repair_required` marking match today's behavior
   exactly.
5. **Live measurement** against a real batch, confirming achieved req/sec
   moves from the 4.27/sec baseline (ticket 01) toward the ~9/sec ceiling.

## Done when

Implemented, all 5 test categories passing, full suite green, live
measurement recorded showing the artifact-fetch loop's real achieved
req/sec post-fix.

## Progress (2026-08-03)

**Implemented**, on branch `claude/artifact-fetch-concurrency` (commit
`d1c9f4d1`): `fetch_filing_artifacts` (`bronze_filing_artifacts.py`) splits
into a sequential cache-hit-resolution pass (cheap DB reads only) followed
by a `ThreadPoolExecutor` pool (default 5 workers,
`WAREHOUSE_ARTIFACT_FETCH_CONCURRENCY`) over only the documents that need a
real fetch. `_write_raw_artifact` split into `_fetch_and_store_attachment`
(worker-safe: network fetch + immutable S3 write + hash, zero DuckDB
access) and the main-thread `db.upsert_raw_object` application step, so
every `db.*` call stays off the pool threads. Results are applied and
merged in strict original `attachment_rows` order regardless of completion
order, so a failure still fails closed with zero partial merge and the
same exception type/message a sequential run would raise.

Scope note (sharpened during implementation, confirmed against real
numbers before committing to it): ticket 03's own text names
"`fetch_filing_artifacts`'s... loop" -- the *per-document* loop inside one
accession's fetch (~5 documents/accession on average, per ticket 01's
30,624 fetches / 5,095 accessions), not the orchestrator's per-accession
loop in `warehouse_orchestrator.py`. Parallelizing at the document level
collapses ~5 serial round-trips to ~1-2 per accession and leaves the
orchestrator's circuit breaker / resume-manifest / retry-with-backoff /
release-mode state machine completely untouched -- so ticket 03's flagged
"circuit breaker consecutive-errors redefinition" nuance doesn't apply;
its premise (out-of-order *accession* completion) never arises.

**Test plan items 1-4**: done, all passing, stable across repeated runs.
New file `tests/unit/test_artifact_fetch_concurrency.py` (5 tests):
correctness equivalence (concurrent vs. env-var-forced-sequential, same
merge order/raw_writes), rate-limiter compliance (a real, unmocked
`pyrate_limiter.Limiter` shared across worker threads, asserting wall-clock
throttling holds), DB-write serialization (thread-id-recording double,
100% of `db.*` calls on the main thread), partial-failure equivalence (a
real immutable-content conflict reproduced via a pre-seeded storage
object -- ticket 74's exact failure mode, not a mocked exception -- 
asserting the same classification and zero partial merge). Full
`tests/unit` + `tests/architecture` suite green (932 passed; one
pre-existing, unrelated `AWS_PROFILE`-dependent wizard test failure
confirmed present on `main` before this change too).

**Test plan item 5 (live measurement): not done.** Requires deploying this
image to prod, and prod's `daily-incremental-ticket74-repair-verify-1785752569`
(the ticket 74 repair-verify run) was still `RUNNING` at last check.
Per [pipeline-throughput-architecture ticket 09](../../pipeline-throughput-architecture/issues/09-decide-cross-command-sec-fetch-mutual-exclusion.md),
running two SEC-fetching commands concurrently is a real compliance risk
(not yet guarded by an actual lock -- that's [ticket 80](80-implement-cross-command-sec-fetch-lease.md),
still open) -- so no new prod execution should be triggered until that run
finishes. Left open pending: (a) that run completing, (b) an explicit
decision to build + push a new warehouse image and deploy it to prod.
