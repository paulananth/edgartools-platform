# Mongo Decision Projection (v2 Atlas, Snowflake stays v1 SoE)

**Status:** accepted  
**Does not supersede** [0001-agent-decision-surface-first.md](0001-agent-decision-surface-first.md): v1 delivery remains the **Snowflake Decision Contract**. This ADR is the ADR 0001 “S3/API optional later” instance.

v2 internet agents read a **Mongo Decision Projection** of a READY Snowflake Decision Contract on Atlas Free (M0): public `mongodb+srv`, TLS, `0.0.0.0/0`, one read-only SCRAM user. Snowflake remains the Agent System of Engagement. Atlas is a serving target, not warehouse ingest.

A separate publisher runs **after** READY and writes database `edgartools_decision` (`issuer_subject_bundle` and `subject_feature_screen`, `_id` = int CIK). Each agent-grade document carries the full Decision Watermark plus `readiness_state`. On pointer / READY move the publisher fail-closes **in place** (`not_ready`, `agent_grade=false`); it does not delete. If Mongo lags or disagrees, the v2 agent abstains; Mongo never wins.

## Why

- Public-internet agents cannot assume a paid Snowflake session.
- Dual truth (parallel gold/graph writer, or a Python dump without READY) was rejected for v1 and stays rejected.
- Feature Screen as one universe document exceeds the 16 MiB BSON limit; one document per CIK does not.

## Considered options (rejected)

- Mongo as v1 SoE, beside or instead of Snowflake.
- Paid Atlas as a v2 prerequisite; private-only Atlas as the v2 agent path.
- Watermark aggregator as the Mongo writer.
- Per-edge collections or a SQL-flat mirror of Snowflake sketches.
- Product OAuth or an HTTPS gateway in front of Mongo before v2 exists.

Detail: `.scratch/mongodb-v2-agent-interface/` (map, data contract, tickets 01–08). Glossary: `CONTEXT.md` **Mongo Decision Projection**.
