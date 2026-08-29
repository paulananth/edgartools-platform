# 39 — Verify gold's DOWNSTREAM refresh lag live, and build its completion barrier

**What to build:** Confirm gold's `target_lag='DOWNSTREAM'` dynamic tables
actually refresh with acceptable freshness against a real Snowflake
account (not assumed from static dbt config), then give gold the same
real completion-barrier proof Ticket 05 decided for silver landing.

**Blocked by:** 05 — Decide silver delta publication and scope-completion
semantics; 07 — Decide gold affected-DAG refresh and status semantics
(this map)

**Status:** resolved

- [x] `SHOW DYNAMIC TABLES IN SCHEMA EDGARTOOLS_GOLD` plus refresh history
  (`INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY` or equivalent)
  confirmed live against prod, proving `target_lag='DOWNSTREAM'` is
  actually refreshing gold tables with acceptable freshness — not assumed
  from the dbt config alone. If it is NOT refreshing acceptably (a leaf
  dynamic table with `DOWNSTREAM` lag and no downstream dynamic-table
  consumer may barely refresh at all), decide and apply a fix (e.g., a
  fixed `target_lag` like silver's, or an explicit trigger).
- [x] CLAUDE.md's Phased Pipeline doc (which still describes
  `SNOWFLAKE_RUN_MANIFEST_TASK` refreshing `EDGARTOOLS_GOLD` within 6
  hours) is corrected to reflect gold's actual current refresh mechanism,
  once confirmed.
- [x] A real completion-barrier check exists for gold, generalizing the
  same `ExpectedProducerSet`/`SilverFinalizer` pattern Ticket 05 decided
  for silver landing (and Ticket 35 is building) — sealed expected
  affected-table set per `cause_reference`, verified against gold's own
  Snowflake-native refresh version/timestamp per table rather than a
  fixed lag alone.
- [x] Gold's own contribution to the composite Decision Watermark
  (Snowflake's native per-table refresh version/timestamp, per Ticket
  07's Answer) is exposed somewhere Ticket 09's aggregation can actually
  read it.

## Notes

Surfaced while resolving [07 — Decide gold affected-DAG refresh and
status semantics](07-decide-gold-affected-dag-refresh.md) — see that
ticket's Answer for the full rationale. `target_lag='DOWNSTREAM'`
(`gold_model_config()` macro, `infra/snowflake/dbt/edgartools_gold/macros/`)
was found live in the dbt config but its actual refresh behavior against
real Snowflake was never verified in this grilling session — flagged as
an open risk, not asserted either way.

## Answer

Live against `EDGARTOOLS_PROD.EDGARTOOLS_GOLD` on 2026-08-29 via
`edgartools-prod`. All 21 gold dynamic tables had `target_lag=DOWNSTREAM`,
`scheduling_state=ACTIVE`, `scheduler=ENABLE`. Last `data_timestamp` values
clustered in one minute on 2026-08-28 08:23–08:24 PT.

`DYNAMIC_TABLE_REFRESH_HISTORY` for `COMPANY` and leaf `TICKER_REFERENCE`
showed `REFRESH_TRIGGER=MANUAL` only (last success 2026-08-28 via
`REFRESH_AFTER_LOAD`). Zero scheduled/DOWNSTREAM-driven refreshes. The
Ticket 07 risk is confirmed: DOWNSTREAM does not refresh gold leaves.

**Fix:** `gold_model_config()` now uses `target_lag='6 hours'`, matching
silver (silver-snowflake-migration Ticket 13 already documented this trap).
`REFRESH_AFTER_LOAD` stays as an extra explicit trigger after a run
manifest. Applying the lag in prod still needs a `dbt run` config deploy.

**Completion barrier:** `verify_gold_dynamic_table_producer` seals through
the existing `ExpectedProducerSpec` / `SilverFinalizer` path with
`producer_kind=gold_dynamic_table`. Injected `read_refresh` must return a
`GoldRefreshIdentity` whose `data_timestamp` is at or after `sealed_at`;
missing or stale timestamps fail closed, independent of the 6-hour clock.

**Watermark contribution:** `gold_refresh_identities_from_show_rows` parses
`SHOW DYNAMIC TABLES` JSON. `gold_watermark_contribution` returns
`{table_name: completion_time_iso_z}` (`refresh_end_time` if present, else
`data_timestamp`) for Ticket 41. Does not invent a gold run id (Ticket 07).
Live `dbt run` to apply the 6-hour lag in prod is still an operator deploy
step.

Tests: `test_verify_gold_dynamic_table_producer_*`,
`test_gold_watermark_contribution_exposes_per_table_data_timestamps`,
`test_gold_model_config_uses_six_hour_target_lag`.
