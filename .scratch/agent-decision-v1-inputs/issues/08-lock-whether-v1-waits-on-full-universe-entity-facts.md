# Lock whether v1 waits on full-universe entity-facts

Type: grilling
Status: open
Blocked by: 07

## Question

Ticket 07 showed As-Of Decision Features exist for only 21 CIKs (Apple +
Ticket 42 sample). The rest of the Decision Subject Universe has no
companyfacts in landing/silver/gold. A `financial_factors` `--full-refresh`
does not add CIKs.

Does this map's destination require a full-universe `entity-facts`
backfill (or daily_incremental Stage 1B wiring) before v1 input is
sorted, or is the 21-CIK sample enough for contract objects while
coverage stays a section flag (`empty` for everyone else)?

Do not re-chart [Decide and execute the fundamentals pipeline
backfill](../../release-readiness/issues/42-decide-execute-fundamentals-backfill.md),
[Fix Stage1BEntityFacts's OOM on the medium Task
Profile](../../ecs-cost-sizing/issues/20-fix-stage1b-entity-facts-oom-on-medium-profile.md),
or [Bring Missing Fundamentals Artifacts Into
daily_incremental](../../fundamentals-daily-integration/map.md). Those
already own how to write more CIKs. This ticket only locks whether v1
Agent-Grade Input Facts **waits** on them.

## Comments

- 2026-09-11 [Confirm fundamentals wiring and lookback years](09-fundamentals-wiring-and-lookback-years.md):
  live load_history already has Stage 1B; live daily_incremental does not.
  entity-facts is not 5-year-capped (FY 2009–2026). Waiting is about
  publish/OOM and daily wiring, not lookback years.
