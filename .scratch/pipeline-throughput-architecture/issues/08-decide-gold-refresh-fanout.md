Type: grilling
Status: open

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
