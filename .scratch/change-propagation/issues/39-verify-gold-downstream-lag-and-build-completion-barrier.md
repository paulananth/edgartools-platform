# 39 — Verify gold's DOWNSTREAM refresh lag live, and build its completion barrier

**What to build:** Confirm gold's `target_lag='DOWNSTREAM'` dynamic tables
actually refresh with acceptable freshness against a real Snowflake
account (not assumed from static dbt config), then give gold the same
real completion-barrier proof Ticket 05 decided for silver landing.

**Blocked by:** 05 — Decide silver delta publication and scope-completion
semantics; 07 — Decide gold affected-DAG refresh and status semantics
(this map)

**Status:** ready-for-agent

- [ ] `SHOW DYNAMIC TABLES IN SCHEMA EDGARTOOLS_GOLD` plus refresh history
  (`INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY` or equivalent)
  confirmed live against prod, proving `target_lag='DOWNSTREAM'` is
  actually refreshing gold tables with acceptable freshness — not assumed
  from the dbt config alone. If it is NOT refreshing acceptably (a leaf
  dynamic table with `DOWNSTREAM` lag and no downstream dynamic-table
  consumer may barely refresh at all), decide and apply a fix (e.g., a
  fixed `target_lag` like silver's, or an explicit trigger).
- [ ] CLAUDE.md's Phased Pipeline doc (which still describes
  `SNOWFLAKE_RUN_MANIFEST_TASK` refreshing `EDGARTOOLS_GOLD` within 6
  hours) is corrected to reflect gold's actual current refresh mechanism,
  once confirmed.
- [ ] A real completion-barrier check exists for gold, generalizing the
  same `ExpectedProducerSet`/`SilverFinalizer` pattern Ticket 05 decided
  for silver landing (and Ticket 35 is building) — sealed expected
  affected-table set per `cause_reference`, verified against gold's own
  Snowflake-native refresh version/timestamp per table rather than a
  fixed lag alone.
- [ ] Gold's own contribution to the composite Decision Watermark
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
