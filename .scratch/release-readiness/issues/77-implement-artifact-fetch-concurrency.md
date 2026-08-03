Type: task
Status: open

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
