# Fix Stage1BEntityFacts's OOM on the `medium` Task Profile

Type: research
Status: open
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
