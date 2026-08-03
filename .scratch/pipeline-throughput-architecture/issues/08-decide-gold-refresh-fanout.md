Type: grilling
Status: resolved

Blocked by: 07

## Question

Should `gold-refresh`'s ~24 independent table builders (`iter_gold_tables`,
confirmed no builder depends on a previously-built table -- see CLAUDE.md's
"Gold-build memory / daily_incremental OOM 5-whys") move from one
sequential ECS task to a fan-out model (Step Functions Distributed Map
across N tasks, each building a subset of tables), given
[ticket 07](07-profile-gold-refresh-stage-breakdown.md)'s measured
per-table cost vs. the fixed cost of N separate canonical-silver-file
copies?

Unlike [ticket 04](04-decide-cross-task-fanout-model.md)'s other candidate
(submissions-bronze-capture, resolved as "no fan-out, use intra-task
concurrency instead"), `gold-refresh` makes zero SEC network calls -- the
rate-limit compliance concern from [ticket 06](06-fix-cross-task-sec-rate-limit-compliance.md)
does not apply here. This is a pure compute/IO tradeoff: N tasks' worth of
parallel table-building time saved vs. N tasks' worth of file-copy time
spent, plus ECS task-start overhead and partial-failure/retry surface (same
operational-cost caveat ticket 04 raised).

## Done when

A decision -- fan out or not, and if so, at what granularity (how many
tasks, how tables get grouped/assigned) -- backed by ticket 07's measured
breakdown, not estimation.

## Answer (2026-08-03, grilling with user)

**No fan-out. Leave gold-refresh as a single sequential task.**

Modeled the tradeoff using ticket 07's real breakdown, adjusted for
[ticket 10](10-decide-gold-refresh-unconditional-silver-republish.md)'s
fix (which removes the 60.65s no-op publish entirely, not just shrinks
it). Post-fix baseline: hydration (13.78s) + setup (7.58s) + table build
(55.77s) + container overhead (31.34s) ~= 108.5s total. The problem for
fan-out: hydration, setup, and container overhead (~52.7s combined) are
**fixed per task** -- every additional parallel task re-downloads the full
1021.9MB canonical file and re-pays its own container startup; only the
55.77s table build actually divides. Theoretical best case at N=4 tasks:
~66.6s (39% faster); N=6: ~62.0s (43% faster) -- and that ignores real
ECS/Fargate task-launch latency (10-30s observed elsewhere this session),
which erodes the gain further and worsens with higher N. Diminishing
returns arrive fast: past ~4-6 tasks, the single largest table
(`fact_adv_private_fund`, 8.19s) plus fixed overhead sets a floor around
60s regardless of task count.

**Verdict**: real but modest savings (~35-45s off an already-sub-2-minute
task) against genuine new complexity -- a Distributed Map state, per-task
silver hydration, and reconciling N tasks' partial gold-table outputs into
one consistent manifest, with more partial-failure/retry surface. Unlike
`daily-incremental` (the actual ~3.5-hour runtime that motivated this
whole map), `gold-refresh` was never the bottleneck this workstream was
chasing. User agreed with this recommendation.

No implementation ticket needed -- this is a "leave it" verdict, same
shape as [ticket 05](05-decide-silver-merge-storage-path.md).
