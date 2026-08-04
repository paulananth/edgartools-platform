# 96 — edgartools quarter-scan forces expensive whole-market index downloads on a too-short timeout

Type: task
Status: resolved

## Question

Ticket 42's sample-artifact backfill (20 CIKs, 3,149 accessions) needed a
third retry today after tickets 88/93 fixed two earlier failure modes (OOM,
circuit-breaker tripping on immutable-object conflicts). That third retry
ran 1h47m and still failed — investigation found a third, distinct root
cause in `bronze_filing_artifacts.py`'s `get_filing()` call, not this
repo's own code.

## Root cause (5-whys)

1. Each `get_filing(accession_number)` call (`bronze_filing_artifacts.py:192`)
   took 82-85 seconds to fail with `httpx.PoolTimeout`, ~88% of the time,
   starting ~47 minutes into the run.
2. `get_filing` defaults to `edgar.get_by_accession_number` — NOT a
   lightweight single-filing lookup. It walks `(year, quarter)` pairs
   **starting at Q1 every time**, downloading and parsing SEC's full
   quarterly filing index (every filing by every registrant that quarter)
   until it finds the accession, cached via an
   `lru_cache(maxsize=8)` (`edgar/_filings.py`).
3. This sample batch spans CIKs with accessions across at least 3 different
   years; with up to 4 quarters checked per year, the 8-slot cache thrashes,
   so most calls are genuine cache misses forcing a fresh multi-MB
   whole-market index download.
4. That download goes through edgartools' shared `HTTP_MGR` client
   (`edgar/httpclient.py`), whose `httpx_params` has no `timeout` key set —
   so it inherits httpx's bare **5-second default** (connect/read/write/pool
   all 5s), not the `BULK_TIMEOUT = Timeout(300.0, connect=10.0)` edgartools
   itself already defines for exactly this "SEC files can be slow on
   congested connections" scenario (`httprequests.py:68`) — `BULK_TIMEOUT`
   is wired into exactly one unrelated async path, not this one.
5. **Root cause:** `should_retry()` treats `PoolTimeout` as retryable, and
   this path has **two nested retry decorators**
   (`decompress_gzip_with_retry` wrapping `get_with_retry`, 5 attempts
   each) — up to 5×5=25 doomed 5-second attempts plus backoff, which
   arithmetically produces the observed ~83s-per-call failures. A large
   whole-market file download inherited a small-request timeout, then got
   retried as if the timeout itself were the anomaly rather than the
   request being fundamentally too big for it.

This is an upstream `edgartools` gap, not a correctness bug (never returns
wrong data) — a timeout/retry misconfiguration on a large-file path.

## Decision (via `/grill-with-docs`, 2026-08-04)

Structural fix (not just today's retry — this same path runs in every
future backfill, including the full-universe `load_history` run ticket 42
is building toward):

1. **Root-cause fix**: `bronze_filing_artifacts.py:108`'s `get_filing`
   default swaps from `edgar.get_by_accession_number` (whole-market scan)
   to a new CIK-scoped adapter — `edgar.Company(cik).get_filings(
   accession_number=...)` → `.get(accession_number)` — using the `cik`
   already resolved in scope at the call site
   (`cik = int(filing["cik"])`, line 130). This searches only that CIK's
   own submissions data, not the whole market. No fallback to the old
   whole-market path on a miss — treated as a genuine failure, consistent
   with already trusting `cik` for the S3 partition path two lines later.
2. **Defensive floor**: `edgar.configure_http(timeout=60.0)` called once at
   module-import time in `bronze_filing_artifacts.py`. Independent of fix
   1 — covers the case where SEC connectivity is generically degraded, not
   only large-download-specific.
3. **Tests**: adapter correctness (mocked `Company`/`EntityFilings`),
   not-found→`None`/no-fallback, DI override (`get_filing=` kwarg) still
   works, timeout-applied-at-import, plus a regression guard asserting the
   whole-market `get_filings`/quarterly-index function is never called via
   the new path.
4. **Rollout**: smoke-test against 1-2 CIKs (with a per-artifact timing
   check) before the full 20-CIK/3,149-accession retry — not straight to
   the full run, given today's track record of three prior failures each
   costing real time.

## Done when

Code + tests land, full suite green, smoke test confirms real per-artifact
fetch times in the single digits (not ~83s), and ticket 42's 4th
artifact-fetch retry completes without hitting this failure mode.
