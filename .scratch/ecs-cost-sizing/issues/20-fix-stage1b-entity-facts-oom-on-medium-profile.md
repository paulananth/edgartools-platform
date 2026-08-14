# Fix Stage1BEntityFacts's OOM on the `medium` Task Profile

Type: research
Status: resolved
Blocked by: none

## Question

`load_history`'s `Stage1BEntityFacts` map (`bootstrap-fundamentals --mode
entity-facts`, `edgar_warehouse/application/warehouse_orchestrator.py` via
`deploy-aws-application.sh`'s `fundamentals_entity_facts` state) runs on the
`medium` task profile (1024 CPU / 4096MB). Should it move to `large` (matching
the precedent set by `Stage0CompanyIdentity`'s own OOM fix — task #51 in this
session's history, and the `gold_table` streaming + 8192MB bump documented in
CLAUDE.md's "Gold-build memory / daily_incremental OOM" 5-whys), or does the
per-window workload need to shrink (smaller `--cik-limit` per window) instead
of a bigger machine?

## Evidence — live incident, `ticket42-task35-fulluniverse-retry7`, 2026-08-14

During `load_history` retry7's full-universe backfill (`ticket42-task35-fulluniverse-retry7-1786673391`),
`Stage1BEntityFacts` window 1 (`--cik-offset 0 --cik-limit 500`,
run-id `db8f945d-1be3-311f-b1f2-2c7f5f5003fe`) OOM-killed on **all 3** configured
attempts (`ecs_state()`'s default `MaxAttempts: 3`), each on the `medium`
profile:

| Attempt | Task ARN | Started | Stopped | Duration | Exit code |
|---|---|---|---|---|---|
| 1 | `7bee782366784360b998cdf880df84dd` | 2026-08-14T01:55:05-04:00 | 2026-08-14T02:48:32-04:00 | ~53 min | 137 (SIGKILL/OOM) |
| 2 | `43e9b63106db4d838258ecd26daa8867` | 2026-08-14T02:51:11-04:00 | 2026-08-14T03:41:43-04:00 | ~50 min | 137 |
| 3 | `75fab0bd1d4d44e28136e6e03987470d` | 2026-08-14T03:46:15-04:00 | 2026-08-14T04:35:50-04:00 | ~49.5 min | 137 |

Remarkably consistent ~50-minute duration across all 3 attempts before the
kill — strong evidence this is a deterministic memory ceiling being hit at a
roughly fixed point in the window's CIK iteration, not a transient/flaky OOM.
CloudWatch logs (`/aws/ecs/edgartools-prod-warehouse`) confirm steady,
successful SEC XBRL `companyfacts` fetches up to the kill point (`bytes` per
company ranging ~0.5MB-5.7MB, e.g. `CIK0000014272.json` at 5,690,382 bytes) —
the task was making real progress, not stuck, when it ran out of memory.

**Consequence in this run**: `Stage1BEntityFacts`'s `ToleratedFailurePercentage: 0`
meant window 1's permanent failure failed the entire 53-window map immediately
(only window 1 had been dispatched; the other 52 never started). The map's
`Catch` correctly routed to `Stage1BPerFiling` per the deliberate AD-13
graceful-degradation design (confirmed live: `MapRunFailed` → `MapStateFailed`
→ `MapStateExited` → `Stage1BPerFiling` entered cleanly, execution did not
crash) — but the practical effect is **zero XBRL entity-facts data
(`sec_financial_fact`, `sec_financial_derived`, `sec_accounting_flag`) for the
entire CIK universe from this run**, deferred to a future idempotent backfill
per that same design.

## Not yet answered

- Whether `large`'s 8192MB ceiling (per the `gold_table` precedent) is
  sufficient headroom for a 500-CIK entity-facts window, or whether the
  per-CIK JSON payload accumulation pattern needs the same *streaming* fix
  `iter_gold_tables()` got (i.e. a code fix, not just a bigger box) — this
  ticket only diagnoses; it does not decide which lever to pull.
- Whether shrinking `--cik-limit` per window (e.g. 500 → 100) trades
  memory headroom for more, shorter windows at the same total sequential cost
  (`MaxConcurrency: 1`), and whether that's cheaper than a profile bump.
- Whether this same shape (large-payload-per-item, sequential-window
  accumulation) also threatens `Stage1BPerFiling`/`Stage1BThirteenF`, the two
  other Branch B modes sharing this same `medium`-profile, per-window-Map
  design — not yet observed failing in this run, but architecturally
  identical risk surface.

Relates to [Decide the Machine Profile for Every Workflow Stage](16-decide-machine-profile-per-workflow-stage.md),
which this evidence directly feeds, but that ticket is broader/blocked and
this finding is actionable on its own (mirrors task #51's standalone
`Stage0CompanyIdentity` OOM fix, done outside any wayfinder map).

## Answer

Root cause is **not** the entity-facts fetch/parse/merge loop — that loop
(`run_bootstrap_entity_facts`, `fundamentals_ingest.py:360-459`) already
streams per-CIK straight into the local DuckDB file via `_merge_rows_bulk`,
and CloudWatch confirms it completes cleanly for all 500/500 CIKs on every
attempt. The OOM happens **afterward**, in the one-time silver-publish step
every `bootstrap-fundamentals` mode shares:
`_publish_silver_database_if_remote` → `merge_candidate_into_canonical`
(`silver_protection.py:585-794`). Its `_delta_rows_as_dicts` helper
(line 481) does an unchunked `.fetchall()` — fine for a steady-state resync
where the anti-join against canonical filters out most rows, but for a
**cold-start table** (canonical `sec_financial_fact` was ~empty going into
this run) the anti-join returns essentially the whole candidate set. Grounded
estimate (measured via `tracemalloc` against a real SEC companyfacts payload,
extrapolated via CloudWatch's own per-company byte counts): ~5.03M candidate
rows ≈ ~2.3GB Python list, stacking with DuckDB's own explicit 2GB bound
(`_connect_bounded()`) — ~4.3GB before process baseline, comfortably over a
`medium` (4096MB) task's ceiling, matching all 3 attempts dying within
seconds of the identical `silver_table_merge_started` log line for
`sec_financial_fact`.

**Q3 (shared risk):** confirmed by code, not inference — `Stage1BPerFiling`
and `Stage1BThirteenF` funnel through the identical publish/merge call on the
same `medium` profile. `per-filing`'s row fan-out is low-risk; `thirteenf`'s
is not — `sec_thirteenf_holding` already has 6.8M rows at full-universe
maturity (per CLAUDE.md), so a cold-start window containing a large 13F
filer is structurally exposed to the identical failure, just not yet
observed.

**Decision — do both, not one or the other:**
1. **Stopgap now:** move `Stage1BEntityFacts`, `Stage1BPerFiling`, and
   `Stage1BThirteenF` to the `large` profile (8192MB) — the ~4.3GB estimate
   fits with real headroom, and Q3's finding means all three should move
   together rather than waiting for `per-filing`/`thirteenf` to independently
   OOM in a future window.
2. **Structural fix before the next full-universe attempt at scale:** chunk
   `_delta_rows_as_dicts`'s row materialization and replace
   `merge_candidate_into_canonical`'s row-by-row `_insert_row`/`_update_row`
   loop with a bulk insert, mirroring `_merge_rows_bulk`'s existing
   Arrow-based approach — the profile bump only moves the ceiling (a wider
   `--cik-limit`, denser XBRL history, or a large 13F filer can reproduce the
   same failure at 8192MB just as deterministically). Rejected: shrinking
   `--cik-limit` alone — it doesn't fix the underlying ~1.5ms/row insert cost
   and doesn't remove the risk for a future window with unusually dense
   companies, only reduces this specific window's odds.

Full evidence, code citations, and CloudWatch timing:
[`stage1b-entity-facts-oom-root-cause-2026-08-14.md`](../research/stage1b-entity-facts-oom-root-cause-2026-08-14.md).
Neither the stopgap nor the structural fix has been implemented — this
ticket is diagnosis + decision only, per this map's planning-only Notes.
