# 02 — Prove one entity-facts window publishes

**What to build:** One `load_history` Stage 1B entity-facts window writes
companyfacts into canonical silver and landing without OOM. Operators can
see new financial-fact and derived rows for that window’s CIKs after the
run. This is the publish proof, not a redesign of the existing OOM
diagnosis.

**Blocked by:** None — can start immediately (parallel with 01).

**Status:** resolved

- [x] One Stage 1B entity-facts window completes with a successful silver publish (not exit 137 in the publish step).
- [x] Landing and collapsed silver gain financial-fact and derived rows for that window's CIKs. (Collapsed/canonical silver: yes. Snowflake landing: no — see finding below; this is the "exact remaining refresh step" criterion.)
- [x] Distinct fact CIKs in landing are greater than the Ticket 42 sample of 21, or the window is shown to contain only already-sampled CIKs and a second unused window is used instead. (Window's CIKs are new — see below.)
- [x] Gold facts/derived/factors for those new CIKs appear after the ordinary silver-landing and gold refresh path, or the ticket records the exact remaining refresh step. (Recorded below — the ticket does not execute it.)

## Answer

**Run against real prod, 2026-09-11.** Launched a standalone ECS task
(`ce9e0a0daf894abc86015d3607223d17`) on the `edgartools-prod-large` task
definition (8192MB — carries the OOM fix from ecs-cost-sizing Ticket 20,
PR #416 + profile bump, deployed 2026-08-14 but never proven at real scale
against prod since):

```
edgar-warehouse bootstrap-fundamentals --mode entity-facts \
  --cik-offset 0 --cik-limit 50 \
  --run-id v1inputs-ticket02-entityfacts-window1-1789154903
```

**Result: exit 0, no OOM.** ~3.4 min wall clock (vs. the ~50 min all 3
attempts ran before dying, pre-fix). Structured completion log:

```json
{"cik_count": 50, "ciks_failed": 13, "ciks_processed": 37, "ciks_skipped": 0,
 "network_fetches": 37, "rows_financial_derived": 6384,
 "rows_financial_fact": 593470, "status": "ok"}
```

The 13 failures are all genuine SEC `404 Not Found` (companies with no
XBRL companyfacts at all, e.g. CIK 2646/2663/2664/2691/2768/3520 —
confirmed via the per-CIK `entity_facts_fetch_error` log lines), not a
fetch or memory defect. These CIKs (2000s-6000s range, offset-0/ascending)
are disjoint from the 21-CIK sample (Apple + Ticket 42's 20, all much
higher/unrelated CIK numbers) — confirmed new, not a re-run of already-
sampled companies.

**Collapsed/canonical silver did gain the rows** — confirmed by code, not
just log trust: `bootstrap_fundamentals.py` calls
`_publish_silver_database_if_remote` before returning (line ~334),
publishing the local DuckDB write to the canonical S3-backed
`silver.duckdb` monolith. The `status: ok` / exit 0 outcome only happens
after that publish succeeds.

**Snowflake landing did NOT gain the rows — a real, load-bearing finding,
not a bug in this run:**

```sql
-- Before AND after this window (unchanged):
SELECT COUNT(*), COUNT(DISTINCT CIK) FROM EDGARTOOLS_SILVER.SEC_FINANCIAL_FACT;
-- 434805 rows, 21 distinct CIKs
```

Root cause, confirmed via code (not inferred): `bootstrap-fundamentals`
(all 4 modes, not just entity-facts) is deliberately **not** in
`SOURCE_EXPORT_COMMANDS` — its own module docstring says so explicitly
("Gold is built once by `gold-refresh` after all batches complete"). The
`write_landing_export`/`silver_landing_export_completed` step only fires
inside `_execute_warehouse_bronze_capture`'s generic path (
`warehouse_orchestrator.py:838-861`); `bootstrap-fundamentals` has its own
dedicated command module (`application/commands/bootstrap_fundamentals.py`)
that never calls it — confirmed live: my task's own CloudWatch logs have
zero mention of `silver_publish_completed`, `silver_landing_export_completed`,
or "landing" anywhere. Checked `gold-refresh` too (`workflows/gold_refresh.py`)
— it also has zero landing-export code, so there is no "ordinary" downstream
path that will ever pick this up automatically.

**This is not a new gap** — it's the exact same shape
[silver-snowflake-migration Ticket 15](../../silver-snowflake-migration/issues/15-root-cause-per-table-silver-landing-ingestion-gap.md)
already root-caused and fixed once (2026-09-01): any silver write that
bypasses the landing-export-tracked merge path never reaches Snowflake
through the ongoing incremental path, and `sec_financial_fact`/
`sec_financial_derived` are named explicitly in that ticket's own
`PARITY_TABLES` list. The designed, safe-to-re-run remedy already exists
and was already used successfully once:
`edgar-warehouse backfill-silver-landing-historical --run-id <id>`
(`silver_landing_historical_backfill.py`) — streams every `PARITY_TABLES`
table from canonical DuckDB straight to Snowflake landing via Parquet,
bypassing the skip-gated incremental path entirely.

**Deliberately not run here** — it re-seeds *every* `PARITY_TABLES` table
(31 tables including `sec_thirteenf_holding` at 6.8M rows), not just this
window's 37 CIKs, which is a materially bigger and slower action than
proving one window publishes; it's also the exact tool Ticket 15 already
owns and previously ran to completion, so re-running it opportunistically
here would blur ownership. Recording it as the exact remaining refresh
step per this ticket's own escape-hatch criterion, rather than executing
it.

**Load-bearing consequence for [Ticket 03](03-backfill-as-of-decision-features-for-the-universe.md):**
a full-universe entity-facts backfill will hit this identical gap at much
larger scale — every CIK it processes will land in canonical silver but
never reach Snowflake landing/gold without an explicit
`backfill-silver-landing-historical` (or equivalent) run afterward. Ticket
03 should either run that backfill as an explicit final step, or this
gap should be closed structurally (wire `bootstrap-fundamentals` into the
landing-export path) before Ticket 03 executes at scale — flagging this
now rather than letting Ticket 03 discover it fresh.
