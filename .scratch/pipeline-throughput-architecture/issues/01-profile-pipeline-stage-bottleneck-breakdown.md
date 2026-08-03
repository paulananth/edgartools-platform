Type: task
Status: resolved

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

## Answer (2026-08-03)

Resolved for `daily-incremental` using real prod data already on hand from
[release-readiness ticket 74](../../release-readiness/issues/74-daily-incremental-permanent-terminal-repair-block.md)'s
investigation -- specifically `daily-incremental-ticket70-verify-1785720814`'s
**attempt 1** (ECS task `04188c2d7c554cb68b48404fa4e2c2a1`), the one attempt
that ran with a fully cold cache (0 prior succeeded/terminal accessions) and
therefore did the complete, unshortened amount of work. Every timestamp below
is either the ECS task's own `StartedAt`/`StoppedAt` or a `emitted_at` field
from the run's own structured log events -- not estimated.

Container lifetime: **12,569.4s (209.5 min)**. Breakdown:

| Phase | Duration | % of accounted time |
|---|---|---|
| Submissions bronze-capture (10,491 CIKs) | 2,901.0s (48.3 min) | 23.3% |
| Silver apply (2,394,012 rows written) | 2,032.3s (33.9 min) | 16.3% |
| Daily-index boundary + configured-form selection | 55.9s (0.9 min) | 0.4% |
| Resume/repair-ledger existence-check loop (5,097 candidates) | 307.7s (5.1 min) | 2.5% |
| **Artifact-fetch loop (5,095 accessions, 30,624 network fetches)** | **7,166.1s (119.4 min)** | **57.5%** |
| *(unaccounted: task init/teardown)* | ~106s | 0.9% |

Total accounted: 12,463.0s vs. 12,569.4s container lifetime (99.2% explained).

**The artifact-fetch loop dominates at 57.5% of wall-clock** -- this is the
loop [tickets 69/70](../../release-readiness/map.md) already improved (S3
client reuse, binary-attachment exclusion); this attempt's image already
included both fixes, so 119.4 min is the **post-fix** cost, not the
pre-fix baseline.

**Rate-limit headroom, concretely:** 30,624 network fetches over 7,166.1s =
**4.27 fetches/sec average** -- well under both the 9 req/sec in-process
limiter and the 10 req/sec SEC ceiling [ticket 02](02-research-sec-rate-limit-headroom.md)
confirmed. This loop is **not rate-limit-bound today** -- there is
real headroom (roughly 2x against the in-process limiter, ~2.3x against
SEC's real ceiling) before intra-task concurrency would even start
contending with the rate limit itself. Whatever concurrency model
[ticket 03](03-decide-intra-task-concurrency-model.md) lands on, the
ceiling isn't the limiting factor yet -- per-fetch overhead (DB writes,
hashing, immutable S3 writes, parsing) is.

**New finding, not previously known:** the resume/repair-ledger existence-check
loop (`daily_artifact_resume.py`'s `prepare_resume`, `_exists_json` called
twice per candidate -- once for `succeeded`, once for `terminal_repair_required`)
took 307.7s for 5,097 candidates (~60ms/candidate, ~10,194 sequential S3
existence checks). Smaller than the top two costs, but it's the same
unbatched-per-row-of-S3-calls shape as
[release-readiness tickets 67-72](../../release-readiness/map.md) --
filed as [release-readiness ticket 75](../../release-readiness/issues/75-batch-daily-artifact-resume-existence-checks.md)
rather than here, since it's a straightforward batching fix (like 67-72),
not an architecture decision this map is scoped to produce.

**Not covered:** `load_history`/`bootstrap-batch`'s own breakdown -- no
real run of that pipeline happened during this investigation. Left as an
explicit gap in **Not yet specified** rather than guessed at; not currently
blocking tickets 03-05, which cite `daily-incremental` and `gold-refresh` as
their primary evidence.

Submissions bronze-capture (48.3 min for 10,491 CIKs, ~0.28s/CIK) and silver
apply (33.9 min for 2.39M rows, ~1,175 rows/sec) are real, data-volume-scaling
work -- no evidence of pathological per-row overhead was found in either
(unlike the resume/repair loop above). This is relevant to the "Not yet
specified" question about whether the DuckDB-single-file storage model itself
is the right primitive: nothing here shows it isn't -- both phases scale
roughly linearly with real data volume, not with call count independent of
volume.
