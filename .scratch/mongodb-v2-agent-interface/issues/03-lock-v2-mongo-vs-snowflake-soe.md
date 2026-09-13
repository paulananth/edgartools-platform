# Lock how v2 Mongo relates to the Snowflake Decision Contract

Type: grilling
Status: resolved
Blocked by: 01, 02

## Question

Is MongoDB a **projection** of a READY Snowflake Decision Contract
(same watermark, same fail-closed rules, written after the aggregator),
a **parallel** writer from gold/graph that can diverge, or a **public
replica** of Python bundle JSON with no READY gate?

v1 stays Snowflake (ADR 0001). This ticket only locks the v2
relationship so later writer and hide-on-pointer-move tickets have a
single SoE story.

Also lock the fail-closed rule when Snowflake READY and Mongo documents
disagree (Mongo lags, extra docs, missing hide): agents abstain, Mongo
wins, or Snowflake wins.

Python bundles expose `agent_grade` and a four-field watermark identity
(no bronze hashes, no Snowflake `PUBLICATION_STATUS`). Lock whether v2
must carry the full Decision Watermark / READY row, or may copy only
that pin.

## Comments

- 2026-09-11 Q1 accepted **A**: Mongo is a **projection** of a READY
  Snowflake Decision Contract (same watermark, same fail-closed rules,
  written after the aggregator). Not a parallel writer. Not a no-READY
  Python dump. v1 SoE stays Snowflake.
- 2026-09-11 Q2 accepted **A**: Publisher fail-closed; v2 agent abstains.
  Mongo is agent-grade only while it matches current READY Snowflake.
  On lag, extra docs, or a missed hide, Mongo must not present
  agent-grade documents. Mongo never wins. Snowflake remains SoE.
- 2026-09-11 Q3 accepted **A**: Every agent-grade v2 document carries the
  full Decision Watermark required for an Agent-Grade Read (including
  bronze identity when bronze persist was used) plus an explicit READY /
  `READINESS_STATE`. The four-field Python pin is not enough.

## Answer

MongoDB v2 is a **projection** of a READY Snowflake Decision Contract:
same watermark, same fail-closed rules, written after the aggregator.
v1 Agent System of Engagement stays Snowflake. Not a parallel gold/graph
writer. Not a no-READY Python dump.

When Snowflake READY and Mongo disagree (lag, extra docs, missed hide),
the **publisher** fail-closes: Mongo must not present agent-grade
documents. The v2 agent abstains. Mongo never wins.

Every agent-grade v2 document carries the **full** Decision Watermark
required for an Agent-Grade Read (including bronze identity when bronze
persist was used) plus an explicit READY / `READINESS_STATE`. A
publication singleton may exist later but must not be the only place
bronze identity lives.
