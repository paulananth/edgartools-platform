Type: task
Status: resolved

## Question

Get a real, measured per-table timing breakdown for one full `gold-refresh`
run: how long each of the ~24 `iter_gold_tables` builders takes, plus the
fixed cost of copying/reading the canonical silver file (currently 1GB+,
same local-copy pattern `silver_protection.py` uses) before any table build
starts.

Split off from [ticket 04](04-decide-cross-task-fanout-model.md): that
ticket's `gold-refresh` fan-out question can't be answered responsibly
without this data. Ticket 01 profiled `daily-incremental` only (the
pipeline that happened to be running live during that investigation) --
`gold-refresh` has never been profiled this way.

The real tradeoff [ticket 08](08-decide-gold-refresh-fanout.md) needs
numbers for: fanning out table builds across N ECS tasks means N separate
copies of the canonical silver file, not one. Whether that's worth it
depends entirely on how expensive the table builds themselves are relative
to that fixed copy cost -- guessing either way would break this map's own
standing rule (every decision backed by real measured data, not structural
reasoning alone).

## Done when

A written per-table (or reasonably grouped) timing breakdown from a real
`gold-refresh` run, plus the measured file-copy/read cost, that
[ticket 08](08-decide-gold-refresh-fanout.md) can cite as evidence.

## Answer (2026-08-03)

Both historical `gold-refresh` executions (2026-07-26/27) predated the
streaming (`iter_gold_tables`) and large-task-profile fixes from CLAUDE.md's
"Gold-build memory / daily_incremental OOM 5-whys" (deployed 2026-07-30),
and their CloudWatch logs had already expired (7-day retention). Rather
than profile stale data, triggered a fresh run
(`ticket07-profile-gold-refresh-1785757940`) -- safe, idempotent
(read-silver, rebuild-gold, doesn't touch bronze/silver content),
independent of the concurrently-running `daily-incremental` execution.
Confirmed on the current `large` task profile (2048 CPU / 8192MB).

**Breakdown** (container lifetime 169.12s):

| Phase | Time | Share |
|---|---|---|
| Silver DB hydration (1021.9MB download) | 13.78s | 8.2% |
| Setup/checkpoint gaps | 7.58s | 4.5% |
| Gold table build (27 tables) | 55.77s | 33.0% |
| **Silver merge/publish (unconditional)** | **60.65s** | **35.9%** |
| Container init/pull/shutdown overhead | 31.34s | 18.5% |

Gold table build itself is already efficient and dominated by a few larger
tables: `fact_adv_private_fund` 8.19s, `sec_thirteenf_holding` 5.67s,
`dim_private_fund` 4.65s, `dim_filing` 2.68s, `fact_filing_activity` 2.60s
-- everything else under 1s. 27 tables in 55.77s sequentially.

**The real finding: the largest single cost (35.9%) is a genuine no-op.**
Traced `silver_publish_started`/`_completed` to
`_publish_silver_database_if_remote`
(`warehouse_orchestrator.py:854-904`): this runs **unconditionally after
every command**, including `gold-refresh`, which never modifies silver
content at all -- it only reads silver to build gold. The observed run's
own event confirms this: `canonical_version == source_version ==
staged_checksum` (all identical) -- the merge ran the full
`shutil.copy2`(1021.9MB) + reattach + 22-table walk cycle (the exact
mechanism [ticket 05](05-decide-silver-merge-storage-path.md) reviewed and
left alone) purely to re-confirm nothing had changed. The function's own
docstring states this is deliberate: "There is no `--force` parameter on
this path -- it cannot bypass the merge or the concurrency check."

This is a bigger, more clearly evidenced finding than a simple fan-out
question -- filed separately as
[ticket 10](10-decide-gold-refresh-unconditional-silver-republish.md) since
it involves a real safety-vs-speed tradeoff (why the no-`--force` design
exists) that should be decided with the user, not assumed.

[Ticket 08](08-decide-gold-refresh-fanout.md) can now proceed using the
**gold table build's own 55.77s/27-table breakdown** above -- but note its
fan-out cost/benefit calculus should be re-evaluated once ticket 10
resolves, since a 35.9%-of-runtime fixed cost sitting *after* the table
build changes the payoff math for parallelizing the build phase alone.
