Type: task
Status: resolved

## Question

Now that CIK-range sharding + shard-aware batch scheduling are both live
(tickets 11/12), does `bronze_seed_silver_gold`'s `BatchSilver` still need
the shared `large` ECS task profile (2048 CPU / 8192MB), or is it now
over-provisioned on memory specifically -- and if so, what's the correct
fix given `large` is shared by 6 other commands, at least one of which
genuinely needs the 8192MB ceiling for an unrelated reason?

## Evidence (confirmed live, 2026-08-08, prod, shard-aware
`bronze_seed_silver_gold` run `bronze-seed-silver-gold-shard-aware-1786206602`,
`MaxConcurrency=4`)

Pulled real CloudWatch Container Insights metrics for the
`edgartools-prod-large` task-definition family over a 60-minute window
covering this run (4 concurrent tasks, cycling across all 4 shards):

- **Memory**: single highest 1-minute peak across all samples was
  **765MB out of 8192MB allocated (~9% utilized)**. Typical per-minute
  peaks ran 100-670MB.
- **CPU**: peak `CpuUtilized` hit **~1,556 of 2048 allocated units
  (~76%)** -- CPU is genuinely being used, not over-provisioned.

The original reason `BatchSilver` was moved onto `large` (commit
`f9fe8b3c`, this session) was `merge_candidate_into_canonical` OOM'ing on
the full ~1.6GB+ monolithic canonical file at `medium`'s 4096MB ceiling.
That reason is now gone -- each task loads exactly one shard
(80-800MB range today), never the whole canonical file.

**`large` is shared, not BatchSilver-specific.** `deploy-aws-application.sh:1176`
registers it once (`register_task_definition large 2048 8192`), and it's
also used by `daily_incremental`, `bootstrap`, `bootstrap_full`,
`targeted_resync`, `full_reconcile`, and `gold_refresh`
(`deploy-aws-application.sh:1220-1232`). Per this repo's own documented
history (CLAUDE.md, "Gold-build memory / daily_incremental OOM 5-whys"),
`large`'s memory was raised 4096->8192MB *specifically* to fix a real OOM
in `daily_incremental`'s gold-table build (`sec_thirteenf_holding`, ~6.8M
rows) -- a completely different, much heavier workload than BatchSilver's
per-shard merge. The 765MB measurement above is only valid for
BatchSilver; it says nothing about whether the other 6 callers still need
8192MB (very likely at least `daily_incremental` still does, per that
documented incident).

**Almost implemented the wrong fix live**: the naive move (lower the
shared `large` profile's memory to 4096MB) would have directly undone the
documented `daily_incremental` OOM fix for every other caller. Caught
before applying via `AskUserQuestion` rather than executed -- see session
history.

## Candidate fix (not decided, not implemented)

Register a **separate, smaller task profile used only by `BatchSilver`**
(e.g. 2048 CPU / 4096MB, matching the real ~765MB peak with real headroom)
rather than touching the shared `large` profile the other 6 commands
depend on. Needs: (a) a name/slot for the new profile alongside
small/medium/large in `deploy-aws-application.sh`, (b) confirming Fargate
allows 2048 CPU paired with 4096MB (valid range for 2048 CPU is
4096-16384MB in 1024MB steps, so yes), (c) deciding whether this is worth
the added task-profile surface area for a memory-cost saving alone, given
CPU is already near its ceiling and wouldn't change.

## Why this wasn't answered already

This map's "Not yet specified" section has carried "whether ECS task
memory/CPU sizing itself... is a limiting factor" as unmeasured fog since
ticket 01 ("folded into ticket 01's profiling pass... but did not pull
Container Insights metrics directly -- still genuinely unmeasured").
Sharding (ticket 11) and shard-aware scheduling (ticket 12) changed
BatchSilver's actual memory profile enough to make this answerable now,
but only for BatchSilver specifically -- the shared-profile risk this
ticket surfaces was not previously visible because nobody had pulled real
memory numbers post-sharding before now.

## Answer (2026-08-08)

**Leave it. Standardize on the existing three task profiles
(`small`/`medium`/`large`) -- do not add a fourth, BatchSilver-only
profile.**

Priced both options at real AWS Fargate us-east-1 on-demand rates
($0.04048/vCPU-hr, $0.004445/GB-hr): the candidate dedicated profile
(2048 CPU / 4096MB) would cost $0.0987/hr vs the current shared `large`'s
$0.1165/hr -- a 15.3% per-task-hour reduction, but only **~$0.43 total
across one full Stage-14-class run** (4 concurrent tasks x ~6h projected
runtime). Memory is priced far cheaper than CPU in Fargate
($0.0044/GB-hr vs $0.0405/vCPU-hr), so even 8GB of mostly-unused headroom
costs very little in absolute terms -- CPU (already near its real ceiling
at ~76% peak utilization) is what actually drives cost, and that stays
identical either way.

Given the savings are negligible against the real cost of a fourth task
profile (more surface area in `deploy-aws-application.sh`'s
`register_task_definition` calls, one more thing to keep in sync, one
more thing for a future session to have to re-verify against real usage),
not worth it. `BatchSilver` stays on the shared `large` profile
unchanged -- the memory headroom is real but cheap to carry, and the
shared-profile risk this ticket surfaced (the other 6 callers' own real
usage still being genuinely unmeasured) remains open as its own fog item
on the map, not blocked by this decision.
