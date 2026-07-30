# 04 — Manual End-to-End Validation

Type: task
Status: resolved
Blocked by: 02
Blocks: 06

## Task

**Corrected 2026-07-27 (ticket 02's resolution):** this task originally named
the July 2026 "registered + exempt archives" (`ia07012026.zip`/
`ia07012026-exempt.zip`) — that is the sec.gov Firm Roster CSV, the *wrong*
SEC product per ticket 01's finding (aggregate-only, doesn't match the
parser's target shape at all). The correct target, per ticket 02's resolved
decision, is the **13-month rolling window of `advFilingData` monthly
archives**, `ADV_Filing_Data_20250601_20250630.zip` through
`ADV_Filing_Data_20260601_20260630.zip` (June 2025 – June 2026 inclusive;
July 2026 not yet published as of this session) — fetched from
`reports.adviserinfo.sec.gov/reports/foia/advFilingData/<year>/<fileName>`,
per the manifest at `reports.adviserinfo.sec.gov/reports/foia/reports_metadata.json`.

Before any automated fetch is built, manually validate ticket 02's decision
against real data end-to-end: stage all 13 monthly archives to S3, hand-build
an `ingest-relationship-sources` source manifest listing all 13 as separate
`iapd_adv_bulk` sources (one `dataset_period` per month, e.g. `2025-06`
.. `2026-06`, matching the format used in
`tests/application/test_adv_bulk_ingest.py`), run it as an ECS task
(requires the full `silver.duckdb` — must run in AWS, same lesson as the
Ticket 20 freeze rebuild that motivated the `mdm
build-relationship-release-manifest` S3-streaming command; `scripts/ops/sync-pipeline.py`'s
`ecs_task_config()`/`run_ecs_task()` already derive cluster/subnet/security-group
from the live Step Function definitions rather than hardcoding them — reuse,
don't hand-construct `aws ecs run-task`), and confirm:

- `sec_adv_filing` / `sec_adv_office` / `sec_adv_disclosure_event` row counts
  jump from the current near-zero baseline to thousands, matching the new
  parser's target format.
- `mdm run --entity-type adviser --entity-type fund` →
  `mdm derive-relationships` → `mdm sync-graph` →
  `mdm verify-graph --skip-native-app` → `mdm graph-activate` → final
  `mdm verify-graph` produce real adviser/fund nodes and (if ticket 02 kept
  `MANAGES_FUND`) real edges in the graph — not just the placeholder 112
  nodes / 1 edge counts left over from this session's Ticket-20-driven graph
  refresh.

## Answer

**Ran in prod (explicit operator decision — dev was reported not viable; see
ticket's governance note below), 2026-07-27.** Result: this validated the
pipeline is genuinely working end-to-end, but **not** via a fresh load —
the 13-month window was already loaded before this session ran anything.
Recording what actually happened, not the originally-expected "near-zero to
thousands" jump.

**Governance note:** this ticket's process (hand-built manifest, single
ad-hoc ECS task) is deliberately lighter than `.scratch/release-readiness`
ticket 20's formal Release-Owner-gated strict-load process, which governs
production relationship/graph writes with sealed evidence and 0%-failure
strict Step Function executions. That process exists for a reason this run
concretely hit (see below) — do not treat this ticket as a substitute for
it if a real fresh ADV load is ever needed against prod.

### What was run

1. Fetched all 13 real monthly `advFilingData` archives (June 2025 – June
   2026, the ticket 02-decided window) directly from
   `reports.adviserinfo.sec.gov`, verified byte counts against the live
   manifest, computed SHA-256 for each.
2. Staged all 13 to `s3://edgartools-prod-bronze-690839588395/warehouse/bronze/reference/adv_bulk_validation/ticket04-20260728T004524Z/`.
3. Hand-built an `ingest-relationship-sources` manifest (13 `iapd_adv_bulk`
   sources, `dataset_period` `2025-06`..`2026-06` matching the format in
   `tests/application/test_adv_bulk_ingest.py`).
4. Ran `ingest-relationship-sources --source-manifest <manifest>` as a real
   ECS task against `edgartools-prod-medium:85` (cluster/subnet/security-group
   discovered live via `scripts/ops/sync-pipeline.py`'s `ecs_task_config()`,
   not hand-constructed) — **exit 0**.
5. Ran `mdm run --entity-type adviser` then `mdm run --entity-type fund` as
   ECS tasks against `edgartools-prod-mdm-medium` — both **exit 0**.
6. Ran `mdm counts` (read-only) to get final MDM state.
7. **Did not run** `backfill-relationships`, `sync-graph`, or
   `graph-activate` — see "Why the chain stopped" below.
8. Ran two read-only Snowflake queries against the live graph
   (`snow sql --connection edgartools-prod`) instead.

### The real finding: this was an idempotency verification, not a fresh load

The ingest task's own log is decisive:
```
silver_publish_completed:
  source_version:    32ef432524892e101daf80b15e89638c
  staged_checksum:   32ef432524892e101daf80b15e89638c
  canonical_version: 32ef432524892e101daf80b15e89638c
```
`source_version` (canonical's ETag *before* this run), `staged_checksum` (md5
of the merged payload), and `canonical_version` (ETag *after* promotion) are
all identical. A merge that genuinely added new rows cannot produce a
byte-identical file — **this ingest was a content no-op.**
`silver_table_counts` reported `sec_adv_filing: 55436` /
`sec_adv_private_fund: 374299` — real numbers, but they were already there
before this run, not added by it.

This is corroborated by every other number collected:
- `mdm run --entity-type adviser` / `--entity-type fund`: `mdm_adviser` and
  `mdm_fund` counts were **identical** immediately before and after each run
  (24,226 advisers / 129,992 funds both times — confirmed from the
  pre-insert `SELECT` logged at the start of `resolve_advisers_bulk`/
  `resolve_funds_bulk` vs. the post-run `mdm counts` output).
- `mdm counts`' `relationships_by_type.MANAGES_FUND` already showed
  `"active": 138585, "pending_graph_sync": 0` — fully resolved and already
  synced, despite this session never having run `backfill-relationships` or
  `sync-graph`.
- 129,992 existing funds and the `adv_bulk_ingest.py` code comment citing
  "the real March-2026 archive (19,675 filings × 130,189 funds)" are the
  same event, not a coincidence.
- The map's own Notes (written before this ticket was worked) already said
  as much: "Confirmed already working (validated live against Ticket 20's
  graph work, 2026-07-23/24): `mdm run`... `mdm derive-relationships`,
  `mdm sync-graph`, `mdm verify-graph`, `mdm graph-activate`, and
  `ingest-relationship-sources --kind iapd_adv_bulk`."

**Conclusion: a prior session already ran this exact validation successfully
against prod (per the map's own Notes, around 2026-07-23/24) with a 13-month
`advFilingData` window that resolves to the same content this session
independently re-fetched from SEC.** Today's re-run correctly did nothing
new — silver's merge-with-ETag-guard-and-retry design (traced before this
run per this ticket's own item-3 prep) behaved exactly as designed, and
`mdm run`'s CRD/PFID-keyed upsert logic correctly found nothing new to
resolve. This is genuinely useful evidence in its own right: it demonstrates
the exact "no-change rerun … zero new relationship identities" idempotency
bar ticket 20's own Done-when criteria require, on the corrected SEC source,
independently reproduced from a fresh SEC fetch rather than replayed
artifacts.

**Process lesson for next time:** a pre-run `mdm counts` baseline should
have been captured before the ingest, which would have made this visible
immediately instead of requiring after-the-fact log archaeology.

### Why the chain stopped before backfill-relationships/sync-graph/graph-activate

`mdm counts` showed other relationship types with real pending-sync backlogs
that are **not** this ticket's to touch: `INSTITUTIONAL_HOLDS` (50,000
active, 50,000 pending — ticket 20's in-flight backfill), `EMPLOYED_BY`
(9,722 pending), `HOLDS` (5,061 pending), `COMPANY_HOLDS` (1,690 pending).
`sync-graph` is not ADV-scoped — running it would sweep all of that pending
work into a new graph generation, and `graph-activate` would point the live
graph (including the `MDM_GRAPH_DASHBOARD` shipped this session, GH-252)
at a generation containing someone else's un-attested in-flight work. Since
`MANAGES_FUND`'s `pending_graph_sync` was already `0`, there was nothing of
this ticket's own to sync anyway — the correct action was to stop and verify
read-only instead.

### Read-only graph verification (proves real data, not the placeholder 112/1 counts)

```sql
-- s3://edgartools-prod... via snow sql --connection edgartools-prod
SELECT COUNT(*) FROM EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION.GRAPH_EDGE_MANAGES_FUND;
-- 138585  (exact match to MDM's active MANAGES_FUND count)

SELECT label, COUNT(*) FROM EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES
WHERE label IN ('Adviser','Fund') GROUP BY label;
-- Adviser: 121503   Fund: 649971
```
`GRAPH_EDGE_MANAGES_FUND` has no `generation_id` column (confirmed via
`DESCRIBE TABLE`) — it is a live per-type materialized compatibility view
(per CLAUDE.md's "Graph storage" note), not gated by
`GRAPH_ACTIVE_POINTER`/generation-scoping the way GH-251's newer
`MDM_GRAPH_REVIEW` schema is. The 138,585 edge count is real and matches
MDM exactly — **this decisively confirms ADV data is live in the production
graph**, not the placeholder 112 nodes / 1 edge counts the map's Notes
describe from before this data existed.

**Open discrepancy, not resolved here:** `MDM_GRAPH_NODES` reports far more
Adviser (121,503) and Fund (649,971) nodes than MDM's own entity counts
(24,226 / 129,992). Not investigated further — outside this ticket's scope
(validating the ADV pipeline decision, not auditing graph node-count
reconciliation) — flagging for whoever next touches `MDM_GRAPH_NODES`.

### Verdict on ticket 02's decision

**Validated.** The correct SEC source (`advFilingData`, not the Firm Roster
CSV), the 13-month rolling window, and the full silver → MDM → graph chain
all work end-to-end on real data, confirmed via an independent fresh fetch
from SEC. No findings from this run change ticket 02's decision.
