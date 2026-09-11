# Why FINANCIAL_FACTORS has only 21 CIKs

Date: 2026-09-11
Connection: `snow sql --connection edgartools-prod`
SQL: [07-why-financial-factors-21-ciks.sql](07-why-financial-factors-21-ciks.sql)
Raw: [07-why-financial-factors-21-ciks.out](07-why-financial-factors-21-ciks.out)

Ticket: [Explain why FINANCIAL_FACTORS has only 21 CIKs](../issues/07-why-financial-factors-only-21-ciks.md)

## Answer in one line

The 21 CIKs are **Apple smoke (2026-07-29) plus the Ticket 42 20-CIK sample
(2026-08-04/05)**. dbt does not drop anyone. Full-universe entity-facts never
published. Daily incremental still does not run `entity-facts`.

## Layer counts (same 21 CIKs all the way down)

| Layer | Rows | Distinct CIKs |
| --- | ---: | ---: |
| Gold `FINANCIAL_FACTORS` | 5,056 | 21 |
| Gold `FINANCIAL_DERIVED` | 5,056 | 21 |
| Gold `FINANCIAL_FACTS` | 434,805 | **21** |
| Silver `SEC_FINANCIAL_DERIVED` | 5,056 | 21 |
| Silver `SEC_FINANCIAL_FACT` | 434,805 | 21 |
| Landing `SEC_FINANCIAL_DERIVED` | 5,056 | 21 |
| Landing `SEC_FINANCIAL_FACT` | 434,805 | 21 |
| Gold `COMPANY` | 73,691 | 73,691 |
| MDM-active | 63,197 | 63,197 |

Zero fact CIKs are missing from derived. Gold factors `ref()` derived; gold
derived `ref()` silver derived; silver derived collapses landing with no
CIK filter
(`infra/snowflake/dbt/edgartools_gold/models/silver/sec_financial_derived.sql`).
The first (and only) shrink is **who `bootstrap-fundamentals --mode
entity-facts` wrote into landing**.

`INGESTED_AT` on facts and derived: **2026-07-29 20:49** through
**2026-08-04 16:25** PT. Nothing newer.

## The 21 CIKs match Ticket 42 exactly

Live gold factors CIKs: 1800, 8818, 10329, 14177, 15615, 16160, 22701,
23194, 25895, 27093, 27996, 60519, 75288, 77543, 82020, 277638, **320193**,
764180, 875355, 1064728, 1603978.

[Decide and execute the fundamentals pipeline backfill](../../release-readiness/issues/42-decide-execute-fundamentals-backfill.md):

- 2026-07-29: Apple (`320193`) entity-facts smoke, real prod write. 282
  derived rows — live factors still has **282** rows for 320193.
- 2026-08-05: the same 20-CIK sample list
  `1800,8818,10329,14177,15615,16160,22701,23194,25895,27093,27996,60519,75288,77543,82020,277638,764180,875355,1064728,1603978`.

20 sample + Apple = 21. Not a parser-success subset of a larger facts table.

## Why the rest of the universe is empty

1. **`entity-facts` is not in `daily_incremental`.** Only
   `load_history` Stage 1B (`FetchEntityFacts` → `bootstrap-fundamentals
   --mode entity-facts`) is wired for full-universe companyfacts. Confirmed
   in Ticket 41 and [Bring Missing Fundamentals Artifacts Into
   daily_incremental](../../fundamentals-daily-integration/map.md) (still
   open; retirement-conflict still blocks entity-facts writes).
2. **Full-universe Stage 1B did not publish.** [Fix Stage1BEntityFacts's
   OOM on the medium Task Profile](../../ecs-cost-sizing/issues/20-fix-stage1b-entity-facts-oom-on-medium-profile.md):
   `ticket42-task35-fulluniverse-retry7` (2026-08-14) window 1 (500 CIKs)
   fetched/parsed all 500 then OOM'd (exit 137) **in silver publish**
   (`merge_candidate_into_canonical` unchunked `.fetchall()` of ~5M cold
   `sec_financial_fact` rows). `ToleratedFailurePercentage: 0` failed the
   map; the other 52 windows never started. Consequence recorded there:
   **zero net-new entity-facts for the universe from that run**.
3. Ticket 42's own sample/full rollout stayed **claimed**; sample passed;
   full-universe Task 35 was "safe to run" after later publish fixes, but
   live landing still has only these 21 CIKs and no ingest after 2026-08-04.

A dbt `--full-refresh` of `financial_factors` adds the three missing
columns. It **cannot** add CIKs. Coverage waits on a successful
entity-facts write+publish for the rest of the universe (load_history
Stage 1B after the publish OOM fix, and/or daily_incremental once that
map ships), not on gold SQL.

## What this is not

- Not a dbt WHERE-clause dropping CIKs.
- Not derived failing while facts succeeded (same 21 at both layers).
- Not warehouse-active ∩ MDM-active (63,197 MDM-active vs 21).
- Not "only 21 issuers have companyfacts at SEC." The writer never ran
  past the Ticket 42 sample.
