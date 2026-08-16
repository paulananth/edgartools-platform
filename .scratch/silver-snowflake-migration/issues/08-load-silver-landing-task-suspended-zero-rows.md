# LOAD_SILVER_LANDING_TASK Suspended Since 2026-08-13 — Landing Zone Has Zero Rows

Status: open

## Summary

Found while checking prod readiness for the mdm-ahead-of-silver map's Phase C
(task #134): the entire silver-landing zone pipeline has never actually
loaded a row in production.

- `EDGARTOOLS_PROD.EDGARTOOLS_SILVER_LANDING.LOAD_SILVER_LANDING_TASK`
  (the 5-minute scheduled `COPY INTO` task, `13_silver_landing_ingest.sql`)
  is `state: suspended`, `last_suspended_reason: SUSPENDED_DUE_TO_ERRORS`,
  suspended at `2026-08-13 20:03:34-07:00` — about 2h25m after being
  created (`2026-08-13 17:38:26-07:00`).
- `TASK_HISTORY` shows it failed every 5-minute run leading up to
  suspension with the identical error: `"NULL result in a non-nullable
  column"` at `Statement.execute, line 30 position 22`. This is the exact
  symptom `13_silver_landing_ingest.sql`'s own comments (lines 109-130)
  describe as already found-and-fixed live during Ticket 07 (`COPY INTO
  ... MATCH_BY_COLUMN_NAME` doesn't invoke a column's `DEFAULT` for a column
  absent from the source Parquet, so `parse_sequence` arrives NULL and the
  procedure must explicitly backfill it after each `COPY`). Either that fix
  never actually reached the deployed procedure, or a different
  non-nullable column hits the same gap.
- Consequence: `EDGARTOOLS_PROD.EDGARTOOLS_SILVER_LANDING.SEC_COMPANY`
  (and, by the same task, every other landing table) has **zero rows**
  (`SELECT COUNT(*) = 0`), despite `SILVER_LANDING_EXPORT_ROOT` being
  correctly wired into the live `edgartools-prod-medium` task definition
  since task #115 — so Parquet exports may well be landing in S3 (not
  checked in this pass), but nothing has been copied into Snowflake since
  the task suspended.
- Downstream consequence: `EDGARTOOLS_PROD.EDGARTOOLS_SILVER` (the schema
  the 31 generated dbt silver models materialize into) has **zero tables
  and zero views** — `dbt run` for the silver layer has apparently never
  been executed against prod at all, separately from the landing-load
  failure above.

## Found while

Checking whether the mdm-ahead-of-silver map's Phase B code (commits
`47fe8fb5`..`5aad528e`) is ready to deploy (task #134). It isn't, and not
for a reason that map's own tickets control: the new
`backfill-mdm-entity-ids` sweep reads pending rows directly from
`EDGARTOOLS_SILVER.*` dynamic tables — which don't exist yet, on top of
which the `mdm_entity_id` column itself hasn't been applied to the landing
schema either (a separate, in-scope gap — see the mdm-ahead-of-silver
map's own Phase A follow-up).

## Impact

Independent of mdm-ahead-of-silver entirely. Any consumer expecting
`EDGARTOOLS_SILVER.*` dynamic tables to reflect real data (dashboards,
future gold models built on top, this map's new sweep) will find them
missing or empty in prod today.

## Next step

Not triaged or fixed here. Needs: (1) root-cause why the documented
parse_sequence-backfill fix isn't preventing this failure in the live
procedure (check the actually-deployed `LOAD_SILVER_LANDING` procedure body
against `13_silver_landing_ingest.sql`'s source — they may have drifted),
(2) resume the task once fixed, (3) a first `dbt run` against prod for the
silver layer once landing data exists.
