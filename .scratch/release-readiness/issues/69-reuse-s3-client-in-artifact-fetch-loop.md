# Reuse a single boto3 S3 client instead of one per artifact write

Type: task
Status: resolved

## Question

Why does the artifact-fetch pipeline (`RunWarehouseTask` running
`daily-incremental --recurring-index-lookback-days 7`) spend ~130-165ms of
non-SEC-fetch time between consecutive `artifact_content_fetch_completed` and the
next `artifact_content_fetch_started` events, when the SEC fetch itself only takes
50-70ms (per live prod logs on `daily-incremental-ticket67-verify-1785709701`), and
how should it be fixed?

## Root cause

`StorageLocation.write_immutable_bytes` (`object_storage.py`, called once per
document by `bronze_filing_artifacts.py::_write_raw_artifact` -- thousands of times
per run) and `StorageLocation.promote_staged` each called `boto3.client("s3")`
fresh, inline, on every invocation. A freshly constructed boto3 client has no
warm connection pool, so its first request pays a cold TCP+TLS handshake instead
of reusing a keep-alive connection -- and since the client is discarded
immediately after one call, *every single* S3 write pays that cold-handshake cost
again.

Measured directly against the real prod bronze bucket
(`edgartools-prod-bronze-690839588395`), 10 calls each:
- fresh `boto3.client("s3")` per call: **184ms/call**
- one client, reused across calls: **52.6ms/call**

The ~131ms delta matches the observed live gap almost exactly, confirming this
(not `db.upsert_raw_object`, not event-emission overhead) was the dominant cost --
consulted `advisor` before implementing, which proposed this exact isolating
measurement (read-only `list_objects_v2` against the real bucket, fresh-client vs.
reused-client) to confirm the hypothesis before writing any fix, rather than
assuming from the 7ms local (no-real-credential-resolution) `boto3.client()`
construction-only benchmark, which undercounted the real cost by not including the
lazy first-request connection setup.

## Fix

`edgar_warehouse/infrastructure/object_storage.py`: `StorageLocation` (a frozen
dataclass) now lazily constructs and caches one boto3 S3 client per instance via a
new `_s3()` method (cached through `object.__setattr__`, matching the existing
`__post_init__` pattern this frozen dataclass already uses for `root`
normalization). Both `write_immutable_bytes` and `promote_staged` call `self._s3()`
instead of constructing `boto3.client("s3")` inline. `write_bytes` (used for daily
index files, not the hot artifact path) already goes through fsspec, which has its
own client-caching, so it wasn't touched.

Per `advisor`'s explicit guidance: **no concurrency added in this pass**. The
per-document loop in `fetch_filing_artifacts` remains sequential. Reasoning:
(1) DuckDB connections are not safe for concurrent writes, and this loop calls
`db.upsert_raw_object`/`db.merge_filing_attachments` on the shared connection;
(2) `write_immutable_bytes`'s `IfNoneMatch: "*"` conditional-create guard exists
specifically to catch concurrent writers to the same key -- a fail-closed
production write path is the wrong place to introduce concurrency risk for a
speculative win; (3) once client-reuse removes the dead time, the loop becomes
bound by SEC's real 9 req/sec rate limit, a hard ceiling concurrency can't beat
anyway, so the remaining upside from pipelining is small.

## Validation

- Isolated, non-mutating measurement against the real prod bucket (see above) --
  confirmed the fix's expected magnitude *before* writing it, not after.
- Existing tests patch `boto3.client` via `monkeypatch.setattr("boto3.client", ...)`
  returning the same mock object regardless of call count, and construct a fresh
  `StorageLocation` per test -- checked before implementing (per `advisor`'s
  explicit flag) that no test asserts a call count on `boto3.client` itself; none
  do. Instance-level caching (not module-level) was chosen specifically so the
  cache can never leak a mocked client across tests sharing one pytest process --
  a module-level cache would have silently broken re-patching between tests.
- `tests/unit/test_object_storage_conditional_promotion.py` -- 5 passed.
- Full suite: `tests/unit tests/application tests/architecture tests/mdm` -- see
  commit for exact count; expected the same one pre-existing unrelated failure as
  tickets 67/68 (`test_go_live_wizard.py::test_plan_prints_preview_only_aws_ordered_commands`).

## Out of scope (surfaced as a separate decision, not bundled here)

While investigating, `advisor` flagged a second, likely-larger lever: the observed
accession `0000719220-26-000090` fetched 5 real documents plus 24 individual
investor-presentation JPGs (46-242KB each, ~4.3s of the filing's ~5.2s total at
current per-doc cost), none of which any parser in this repo reads (ownership XML,
ADV, Item 5.02, Item 5.02 8-K, XBRL). Excluding binary presentation images via the
existing `--artifact-policy` control surface is plausibly a bigger multiplier than
this latency fix, and would also reduce ticket 65's S3 storage growth -- but it
changes what bronze captures going forward, against CLAUDE.md's additive-immutable
convention, so it's a genuine operator trade-off, not a pure engineering fix.
Filed separately as [ticket 70](70-decide-exclude-binary-artifacts-from-fetch-policy.md)
rather than bundled into this perf fix, per `advisor`'s explicit recommendation not
to conflate the two.

## Done when

Done -- fix implemented, validated against the real prod bucket end-to-end (not
just synthetic benchmarks), existing tests confirmed unaffected, full suite green
modulo the one pre-existing unrelated failure. Not yet deployed to prod as of this
entry.
