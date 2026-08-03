Type: grilling
Status: resolved

Blocked by: 01, 02

## Question

Should per-CIK network+DB operations inside a single ECS task move from
today's sequential Python loop (one CIK/accession at a time, e.g.
`_capture_submission_bronze_snapshot`, the artifact-fetch loop in
`bronze_filing_artifacts.py`) to intra-task concurrency (asyncio or a
bounded thread pool), given the SEC rate-limit ceiling ticket 02
establishes?

If [Profile the real bottleneck breakdown across pipeline
stages](01-profile-pipeline-stage-bottleneck-breakdown.md) shows the
per-CIK loops are already running at the rate-limit ceiling (throughput
bound by SEC, not by Python), added concurrency inside one task buys
nothing and this ticket should resolve "no" with that evidence. If it
shows meaningful idle time between requests (DB writes, JSON parsing,
orchestration overhead not overlapped with the next fetch), concurrency
is the lever and this ticket should specify the shape (asyncio vs
threadpool, what bound, which loops).

## Done when

A decision -- yes/no, and if yes, which loops and what concurrency
primitive/bound -- backed by ticket 01's measured breakdown, not
estimation.

## Answer (2026-08-03, grilling with user)

**Yes, pursue intra-task concurrency.** Ticket 01's measured breakdown showed
the artifact-fetch loop is not rate-limit-bound today (4.27 req/sec against a
9-10 req/sec ceiling), so there's real headroom -- this isn't a case where
concurrency would just contend uselessly with the SEC limit.

**Scope: artifact-fetch loop only, for now** (`bronze_filing_artifacts.py`'s
per-accession loop, the 57.5%/119.4-min dominant cost). The submissions
bronze-capture loop (`_capture_submission_bronze_snapshot`, 23.3%/48.3 min)
was confirmed to also have headroom (1 SEC call/CIK, 3.62 calls/sec measured)
but is deliberately deferred to a fast-follow once this first pass proves the
pattern, rather than doing both loops in one first-time-concurrency change.

**Primitive: `concurrent.futures.ThreadPoolExecutor`, not asyncio.** The
parallelized work (SEC fetch, S3 write) is blocking I/O, not CPU-bound, and
`sec_client.py` already uses `httpx.Client` synchronously -- a thread pool
wraps that as-is with zero changes to `sec_client.py`/`object_storage.py`.
asyncio would require migrating the whole call chain to `httpx.AsyncClient`
and `async def` for no clear throughput benefit at this concurrency scale
(single digits, not thousands of connections), in a codebase with zero
existing asyncio precedent (confirmed via repo-wide search).

**DB writes stay serialized on the main thread.** A single `SilverDatabase`
DuckDB connection isn't safe for concurrent writes from multiple threads.
Design: thread pool covers only the network fetch (SEC call + content
download); results are collected and `db.merge_filing_attachments`/raw-object
writes happen sequentially back on the main thread, same as today.

**Worker bound: 5** -- matches the existing `BOOTSTRAP_BATCH_CONCURRENCY`
"2-5 recommended range" convention already documented in CLAUDE.md, rather
than introducing an arbitrary new number. Confirmed `pyrate_limiter`'s
`Limiter`/`InMemoryBucket` uses an internal `RLock` (source-verified,
`pyrate_limiter/limiter.py`) -- genuinely thread-safe across concurrent
`try_acquire` callers, so the shared rate limiter itself remains the actual
throughput ceiling regardless of pool size; the pool's job is closing the gap
between today's observed 4.27 req/sec and the limiter's ~9 req/sec pace by
overlapping one thread's post-processing (hashing, S3 write, DB prep) with
another thread already waiting on its next rate-limited slot.

**Test plan** (real DB-backed, matching the tickets 67-72 discipline, not
mocks):
1. Correctness equivalence -- N fake accessions through the concurrent path
   vs. the sequential path, assert identical final `SilverDatabase` state.
2. Rate-limiter compliance -- real `Limiter` at a deliberately low test rate,
   assert wall-clock throttling holds regardless of pool size.
3. DB-write serialization -- thread-id-recording test double on
   `SilverDatabase`, assert 100% of writes happen on the main thread.
4. Partial-failure equivalence -- inject a failure (e.g. an immutable-content
   conflict, matching [release-readiness ticket 74](../../release-readiness/issues/74-daily-incremental-permanent-terminal-repair-block.md)'s
   real scenario) among several concurrent accessions, assert error counting
   and `terminal_repair_required` marking match today's behavior exactly.
5. Live measurement against a real batch, confirming achieved req/sec moves
   from the 4.27/sec baseline toward the ~9/sec ceiling -- correctness tests
   prove safety, only a real run proves speedup.

**Known implementation nuance, flagged but deliberately not decided here**
(decision-spec scope, not implementation): the existing circuit breaker
(`consecutive_errors >= _CONSECUTIVE_ERROR_LIMIT`) assumes strictly
sequential completion order to define "consecutive." Under concurrent
fetching, completions arrive out of submission order, so "consecutive" needs
redefining (e.g. errors within the last N *completions* rather than the last
N *submissions*) -- left for whoever implements this.
