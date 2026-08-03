Type: task
Status: open

## Question

Get a real, measured cost breakdown for one full `daily_incremental` run and
one full `load_history`/`bootstrap-batch` run, split into: SEC network
fetch time (rate-limit-bound, not fixable), DuckDB read/write time inside
`silver_protection.py`'s merge path (`shutil.copy2` + ATTACH +
`information_schema` introspection + per-row `_insert_row`/`_update_row`),
S3 GET/PUT time, and idle/orchestration overhead with no I/O in flight.

This is the evidence every other ticket on this map needs before deciding
where to spend restructuring effort -- without it, "make it faster" is
guesswork about which of several plausible bottlenecks (network,
DuckDB merge, S3, task sizing) actually dominates at current scale.

Reuse the `network_fetches`/cache-hit counters and event-emission pattern
already established in [release-readiness](../../release-readiness/map.md)
tickets 67-69 (`fetch_filing_artifacts`'s `network_fetches`,
`catalog_network_fetches`/`catalog_silver_skips`) -- extend that
instrumentation to the merge path and the submissions-bronze-capture loop
rather than inventing a new format. A live execution is fine as the
measurement vehicle; this doesn't need synthetic benchmarking.

## Done when

A written breakdown (percentage or absolute time per category, per
pipeline) exists, backed by real prod or prod-like execution data, that
the frontier tickets below can cite as their evidence.
